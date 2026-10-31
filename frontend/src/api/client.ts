import type {
  CheckResult,
  CreatedWebhookEndpoint,
  Incident,
  Monitor,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEventType,
} from "./types";

const BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let message = "Request failed: " + res.status;
    try {
      const body = await res.json();
      if (body?.error?.message) message = body.error.message;
      else if (body?.detail?.error?.message) message = body.detail.error.message;
    } catch {
      // response had no JSON body
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listMonitors: () => request<Monitor[]>("/monitors"),

  getMonitor: (id: number) => request<Monitor>("/monitors/" + id),

  createMonitor: (url: string, interval_seconds = 60) =>
    request<Monitor>("/monitors", {
      method: "POST",
      body: JSON.stringify({ url, interval_seconds }),
    }),

  updateMonitor: (
    id: number,
    patch: { interval_seconds?: number; enabled?: boolean },
  ) =>
    request<Monitor>("/monitors/" + id, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteMonitor: (id: number) =>
    request<void>("/monitors/" + id, { method: "DELETE" }),

  checkHistory: (id: number, limit = 100) =>
    request<CheckResult[]>("/monitors/" + id + "/checks?limit=" + limit),

  incidentHistory: (id: number) =>
    request<Incident[]>("/monitors/" + id + "/incidents"),

  incidents: (state: "open" | "resolved" | "all" = "all") =>
    request<Incident[]>("/incidents?state=" + state),

  webhooks: () => request<WebhookEndpoint[]>("/webhooks"),

  createWebhook: (payload: {
    name: string;
    url: string;
    event_types: WebhookEventType[];
  }) =>
    request<CreatedWebhookEndpoint>("/webhooks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateWebhook: (
    id: number,
    patch: {
      name?: string;
      url?: string;
      event_types?: WebhookEventType[];
      enabled?: boolean;
    },
  ) =>
    request<WebhookEndpoint>("/webhooks/" + id, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  disableWebhook: (id: number) =>
    request<void>("/webhooks/" + id, { method: "DELETE" }),

  webhookDeliveries: (id: number, limit = 50) =>
    request<WebhookDelivery[]>("/webhooks/" + id + "/deliveries?limit=" + limit),
};
