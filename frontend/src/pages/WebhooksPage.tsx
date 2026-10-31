import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { WebhookDelivery, WebhookEndpoint, WebhookEventType } from "../api/types";
import { Button } from "../components/Button";
import { Card, CardHeader, PageHeader } from "../components/Card";
import { EmptyState, ErrorBanner, Skeleton } from "../components/Feedback";
import { usePolledResource } from "../hooks/usePolledResource";

const EVENT_TYPES: WebhookEventType[] = ["incident.opened", "incident.resolved"];

function eventLabel(eventType: WebhookEventType) {
  return eventType === "incident.opened" ? "Incident opened" : "Incident resolved";
}

function deliveryStatusClass(status: WebhookDelivery["status"]) {
  if (status === "delivered") return "text-up";
  if (status === "failed") return "text-down";
  if (status === "delivering") return "text-accent";
  return "text-degraded";
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function WebhooksPage() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [eventTypes, setEventTypes] = useState<WebhookEventType[]>(EVENT_TYPES);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const {
    data: endpoints,
    loading,
    error,
    reload: reloadEndpoints,
  } = usePolledResource<WebhookEndpoint[]>(() => api.webhooks(), 10000);

  const {
    data: deliveries,
    loading: deliveriesLoading,
    error: deliveriesError,
    reload: reloadDeliveries,
  } = usePolledResource<WebhookDelivery[]>(
    () => (selectedId == null ? Promise.resolve([]) : api.webhookDeliveries(selectedId)),
    10000,
  );

  useEffect(() => {
    if (!endpoints?.length) {
      setSelectedId(null);
      return;
    }
    if (selectedId == null || !endpoints.some((endpoint) => endpoint.id === selectedId)) {
      setSelectedId(endpoints[0].id);
    }
  }, [endpoints, selectedId]);

  useEffect(() => {
    if (selectedId != null) reloadDeliveries();
  }, [selectedId, reloadDeliveries]);

  function toggleEvent(eventType: WebhookEventType) {
    setEventTypes((current) =>
      current.includes(eventType)
        ? current.filter((item) => item !== eventType)
        : [...current, eventType],
    );
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setCreatedSecret(null);
    setSaving(true);
    try {
      const created = await api.createWebhook({
        name: name.trim(),
        url: url.trim(),
        event_types: eventTypes,
      });
      setCreatedSecret(created.secret);
      setName("");
      setUrl("");
      setEventTypes(EVENT_TYPES);
      setSelectedId(created.id);
      await reloadEndpoints();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not create webhook.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDisable(endpoint: WebhookEndpoint) {
    setActionError(null);
    try {
      await api.disableWebhook(endpoint.id);
      await reloadEndpoints();
      if (selectedId === endpoint.id) setSelectedId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not disable webhook.");
    }
  }

  async function handleEnable(endpoint: WebhookEndpoint) {
    setActionError(null);
    try {
      await api.updateWebhook(endpoint.id, { enabled: true });
      await reloadEndpoints();
      setSelectedId(endpoint.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not enable webhook.");
    }
  }

  async function copySecret() {
    if (!createdSecret) return;
    try {
      await navigator.clipboard.writeText(createdSecret);
    } catch {
      setActionError("Clipboard access was unavailable. Select and copy the secret manually.");
    }
  }

  const endpointList = endpoints ?? [];
  const selected = endpointList.find((endpoint) => endpoint.id === selectedId) ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Webhooks"
        description="Deliver signed notifications when monitored services open or resolve incidents."
      />

      {error && <ErrorBanner message={error} />}
      {actionError && <ErrorBanner message={actionError} />}

      {createdSecret && (
        <div className="rounded-lg border border-accent/40 bg-accent/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-ink">Save this signing secret</p>
            <Button type="button" onClick={copySecret}>Copy secret</Button>
          </div>
          <p className="mt-1 text-xs text-ink-dim">
            Pulse only returns this secret once. Store it in the receiving service before closing this notice.
          </p>
          <code className="mt-3 block select-all break-all rounded bg-app p-3 text-xs text-ink">
            {createdSecret}
          </code>
          <button
            type="button"
            className="mt-2 text-xs text-ink-dim underline hover:text-ink"
            onClick={() => setCreatedSecret(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <Card>
        <CardHeader
          title="Add webhook endpoint"
          description="Production endpoints must use HTTPS. Pulse signs every event with HMAC-SHA256."
        />
        <form onSubmit={handleCreate} className="grid gap-4 p-4 md:grid-cols-2">
          <label className="grid gap-1.5 text-sm text-ink-dim">
            Endpoint name
            <input
              required
              minLength={1}
              maxLength={80}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Operations receiver"
              className="rounded-md border border-line bg-app px-3 py-2 text-sm text-ink"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-ink-dim">
            Destination URL
            <input
              required
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://hooks.example.com/pulse"
              className="rounded-md border border-line bg-app px-3 py-2 text-sm text-ink"
            />
          </label>
          <fieldset className="grid gap-2 md:col-span-2">
            <legend className="text-sm text-ink-dim">Subscribe to events</legend>
            <div className="flex flex-wrap gap-4">
              {EVENT_TYPES.map((eventType) => (
                <label key={eventType} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={eventTypes.includes(eventType)}
                    onChange={() => toggleEvent(eventType)}
                    className="accent-[var(--color-accent)]"
                  />
                  {eventLabel(eventType)}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="md:col-span-2">
            <Button type="submit" variant="primary" disabled={saving || eventTypes.length === 0}>
              {saving ? "Creating…" : "Create webhook"}
            </Button>
          </div>
        </form>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <Card>
          <CardHeader
            title="Configured endpoints"
            description={endpointList.length + " endpoint" + (endpointList.length === 1 ? "" : "s")}
          />
          <div className="p-3">
            {loading && !endpoints ? (
              <Skeleton className="h-24 w-full" />
            ) : endpointList.length === 0 ? (
              <EmptyState
                title="No webhook endpoints"
                description="Add an endpoint to receive incident notifications."
              />
            ) : (
              <ul className="space-y-2">
                {endpointList.map((endpoint) => {
                  const selectedClass = selectedId === endpoint.id
                    ? "border-accent/60 bg-raised"
                    : "border-line bg-app";
                  return (
                    <li key={endpoint.id}>
                      <div className={"rounded-lg border p-3 " + selectedClass}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(endpoint.id)}
                          className="w-full text-left"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-sm font-medium text-ink">
                              {endpoint.name}
                            </span>
                            <span
                              className={"shrink-0 text-xs " + (
                                endpoint.enabled ? "text-up" : "text-ink-faint"
                              )}
                            >
                              {endpoint.enabled ? "Enabled" : "Disabled"}
                            </span>
                          </div>
                          <p className="mt-1 truncate text-xs text-ink-dim">{endpoint.url}</p>
                          <p className="mt-2 text-xs text-ink-faint">
                            {endpoint.event_types.map(eventLabel).join(" · ")}
                          </p>
                        </button>
                        <div className="mt-3 flex justify-end">
                          {endpoint.enabled ? (
                            <Button
                              type="button"
                              variant="danger"
                              className="px-2 py-1 text-xs"
                              onClick={() => handleDisable(endpoint)}
                            >
                              Disable
                            </Button>
                          ) : (
                            <Button
                              type="button"
                              className="px-2 py-1 text-xs"
                              onClick={() => handleEnable(endpoint)}
                            >
                              Enable
                            </Button>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title={selected ? "Recent deliveries — " + selected.name : "Delivery history"}
            description="Attempts and outcomes for this endpoint."
          />
          <div className="p-4">
            {!selected ? (
              <EmptyState
                title="Select an endpoint"
                description="Choose a configured endpoint to inspect its recent delivery history."
              />
            ) : deliveriesLoading && !deliveries ? (
              <Skeleton className="h-24 w-full" />
            ) : deliveriesError ? (
              <ErrorBanner message={deliveriesError} />
            ) : !deliveries?.length ? (
              <EmptyState
                title="No deliveries yet"
                description="A delivery appears here when an incident opens or resolves."
              />
            ) : (
              <div className="space-y-3">
                {deliveries.map((delivery) => (
                  <DeliveryRow key={delivery.id} delivery={delivery} />
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function DeliveryRow({ delivery }: { delivery: WebhookDelivery }) {
  return (
    <div className="rounded-lg border border-line-soft bg-app p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-ink">
          {eventLabel(delivery.event_type)}
        </span>
        <span className={"text-xs font-medium capitalize " + deliveryStatusClass(delivery.status)}>
          {delivery.status}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-dim">
        <span>Incident #{delivery.incident_id}</span>
        <span>{delivery.attempt_count} attempt{delivery.attempt_count === 1 ? "" : "s"}</span>
        <span>Created {formatDate(delivery.created_at)}</span>
        {delivery.delivered_at && <span>Delivered {formatDate(delivery.delivered_at)}</span>}
        {delivery.last_status_code && <span>HTTP {delivery.last_status_code}</span>}
      </div>
      {delivery.last_error_message && (
        <p className="mt-2 text-xs text-down">{delivery.last_error_message}</p>
      )}
      {delivery.attempts.length > 0 && (
        <div className="mt-3 border-t border-line-soft pt-2">
          <p className="text-xs font-medium text-ink-dim">Attempt history</p>
          <ul className="mt-1 space-y-1">
            {delivery.attempts.map((attempt) => (
              <li key={attempt.id} className="flex flex-wrap justify-between gap-2 text-xs text-ink-faint">
                <span>
                  #{attempt.attempt_number} · {attempt.outcome}
                  {attempt.response_status ? " · HTTP " + attempt.response_status : ""}
                </span>
                <span>{formatDate(attempt.attempted_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
