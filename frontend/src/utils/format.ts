export function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export function fmtLatency(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function fmtInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function redactUrl(url: string): string {
  // Mask query-string values that could carry sensitive tokens (PRD §9).
  try {
    const u = new URL(url);
    if ([...u.searchParams.keys()].length === 0) return url;
    const masked = new URL(u.origin + u.pathname);
    for (const key of [...u.searchParams.keys()]) {
      masked.searchParams.set(key, "•••");
    }
    return masked.toString();
  } catch {
    return url;
  }
}
