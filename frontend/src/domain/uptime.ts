import type { CheckResult } from "../api/types";

export interface UptimeResult {
  /** Observed success ratio over the fetched window, or null if no data. */
  ratio: number | null;
  successes: number;
  total: number;
  /** True when total < 3 — the sample is too small to report honestly. */
  insufficient: boolean;
}

/**
 * Observed check-success ratio over the provided checks.
 *
 * This is NOT a guaranteed uptime percentage — it is the ratio of successful
 * checks in the fetched window (currently bounded to the most recent checks
 * returned by the API). Returns null when there is no data and flags
 * `insufficient` when the sample is too small to report.
 */
export function computeUptime(checks: CheckResult[]): UptimeResult {
  const total = checks.length;
  if (total === 0) {
    return { ratio: null, successes: 0, total: 0, insufficient: true };
  }
  const successes = checks.filter((c) => c.outcome === "success").length;
  return {
    ratio: (successes / total) * 100,
    successes,
    total,
    insufficient: total < 3,
  };
}
