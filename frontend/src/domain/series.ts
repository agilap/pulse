import type { CheckResult } from "../api/types";

export interface LatencyPoint {
  checked_at: string;
  latency_ms: number;
}

/**
 * Extract latency series from successful checks only, oldest → newest.
 * Failed checks have no meaningful latency and are intentionally excluded —
 * they are shown in the check history, not plotted as zero.
 */
export function latencySeries(checks: CheckResult[]): LatencyPoint[] {
  return checks
    .filter((c): c is CheckResult & { latency_ms: number } => c.latency_ms != null)
    .map((c) => ({ checked_at: c.checked_at, latency_ms: c.latency_ms }))
    .sort((a, b) => a.checked_at.localeCompare(b.checked_at));
}
