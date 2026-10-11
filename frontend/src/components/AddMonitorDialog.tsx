import { useState } from "react";
import { api } from "../api/client";
import { Button } from "./Button";
import { Modal } from "./Modal";

const INTERVALS = [60, 300, 600, 1800, 3600, 21600, 86400];

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

function validateUrlClient(raw: string): string | null {
  const url = raw.trim();
  if (!url) return "URL is required.";
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return "Enter an absolute URL, e.g. https://example.com.";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http and https URLs are supported.";
  }
  return null;
}

export function AddMonitorDialog({ open, onClose, onCreated }: Props) {
  const [url, setUrl] = useState("");
  const [interval, setInterval] = useState(60);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setUrl("");
    setInterval(60);
    setUrlError(null);
    setApiError(null);
    setSubmitting(false);
  }

  function close() {
    reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setApiError(null);
    const err = validateUrlClient(url);
    setUrlError(err);
    if (err || submitting) return;

    setSubmitting(true);
    try {
      await api.createMonitor(url.trim(), interval);
      onCreated();
      close();
    } catch (ex) {
      // Preserve input; surface the API's structured message without internals.
      setApiError(ex instanceof Error ? ex.message : "Failed to create monitor.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Add monitor"
      onClose={close}
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="add-monitor-form"
            disabled={submitting}
          >
            {submitting ? "Adding…" : "Add monitor"}
          </Button>
        </>
      }
    >
      <form id="add-monitor-form" onSubmit={submit} noValidate>
        <div className="space-y-4">
          <div>
            <label htmlFor="url" className="block text-sm font-medium text-ink">
              Endpoint URL
            </label>
            <p className="mt-0.5 text-xs text-ink-dim">
              A public HTTP or HTTPS URL that Pulse will check on a schedule.
            </p>
            <input
              id="url"
              type="url"
              inputMode="url"
              autoComplete="off"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (urlError) setUrlError(null);
              }}
              placeholder="https://example.com"
              aria-invalid={urlError ? true : undefined}
              aria-describedby={urlError ? "url-error" : undefined}
              className={`mt-1.5 w-full rounded-md border bg-app px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent ${
                urlError ? "border-down" : "border-line"
              }`}
            />
            {urlError && (
              <p id="url-error" className="mt-1 text-xs text-down">
                {urlError}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="interval"
              className="block text-sm font-medium text-ink"
            >
              Check interval
            </label>
            <p className="mt-0.5 text-xs text-ink-dim">
              How often Pulse should check this endpoint.
            </p>
            <select
              id="interval"
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
              className="mt-1.5 w-full rounded-md border border-line bg-app px-3 py-2 text-sm text-ink focus:border-accent"
            >
              {INTERVALS.map((s) => (
                <option key={s} value={s}>
                  Every {formatIntervalOption(s)}
                </option>
              ))}
            </select>
          </div>

          {apiError && (
            <p role="alert" className="rounded-md border border-down/40 bg-down/10 px-3 py-2 text-sm text-down">
              {apiError}
            </p>
          )}
        </div>
      </form>
    </Modal>
  );
}

function formatIntervalOption(s: number): string {
  if (s < 60) return `${s} seconds`;
  const m = s / 60;
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"}`;
  const h = m / 60;
  return `${h} hour${h === 1 ? "" : "s"}`;
}
