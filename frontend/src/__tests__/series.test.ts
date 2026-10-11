import { describe, expect, it } from "vitest";
import { latencySeries } from "../domain/series";
import type { CheckResult } from "../api/types";

function c(checked_at: string, outcome: string, latency_ms: number | null): CheckResult {
  return {
    id: Math.random(),
    checked_at,
    outcome,
    status_code: outcome === "success" ? 200 : null,
    latency_ms,
    error_code: null,
    error_message: null,
  };
}

describe("latencySeries", () => {
  it("includes only checks with a latency value, sorted oldest→newest", () => {
    const series = latencySeries([
      c("2026-01-02T00:00:00Z", "success", 30),
      c("2026-01-01T00:00:00Z", "success", 10),
      c("2026-01-03T00:00:00Z", "timeout", null), // no latency → excluded
      c("2026-01-04T00:00:00Z", "success", 20),
    ]);
    expect(series.map((p) => p.latency_ms)).toEqual([10, 30, 20]);
  });

  it("never represents a failed check as zero latency", () => {
    const series = latencySeries([c("2026-01-01T00:00:00Z", "http_error", null)]);
    expect(series).toHaveLength(0);
  });

  it("returns empty for no checks", () => {
    expect(latencySeries([])).toEqual([]);
  });
});
