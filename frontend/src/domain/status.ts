import type { Monitor } from "../api/types";

export const STATUS_ORDER = [
  "up",
  "degraded",
  "down",
  "stale",
  "pending",
] as const;

export interface StatusMeta {
  label: string;
  dot: string;
  text: string;
  /** Short explanation surfaced in tooltips / detail views. */
  hint: string;
}

export const STATUS_META: Record<Monitor["status"], StatusMeta> = {
  up: {
    label: "Up",
    dot: "bg-up",
    text: "text-up",
    hint: "Latest check succeeded and no incident is open.",
  },
  degraded: {
    label: "Degraded",
    dot: "bg-degraded",
    text: "text-degraded",
    hint: "Recent checks are failing, but below the incident threshold.",
  },
  down: {
    label: "Down",
    dot: "bg-down",
    text: "text-down",
    hint: "An incident is open and results are still fresh.",
  },
  stale: {
    label: "Stale",
    dot: "bg-ink-faint",
    text: "text-ink-dim",
    hint: "No recent results — Pulse cannot confirm current state.",
  },
  pending: {
    label: "Pending",
    dot: "bg-ink-faint",
    text: "text-ink-dim",
    hint: "Waiting for the first completed check.",
  },
};

export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function monitorName(m: Pick<Monitor, "id" | "url">): string {
  // No name column exists in the schema; derive a readable label from the host.
  const host = hostnameOf(m.url);
  // A parsed URL with no dot (e.g. bare "localhost" or a failed parse) is not
  // a useful label — fall back to the monitor id.
  if (!host || !host.includes(".")) return `Monitor ${m.id}`;
  return host;
}

export function redactUrl(url: string): string {
  try {
    const u = new URL(url);
    if ([...u.searchParams.keys()].length === 0) return url;
    const masked = new URL(u.origin + u.pathname);
    for (const key of [...u.searchParams.keys()]) {
      masked.searchParams.set(key, "***");
    }
    return masked.toString();
  } catch {
    return url;
  }
}
