import { describe, expect, it } from "vitest";
import { computeUptime } from "../domain/uptime";
import type { CheckResult } from "../api/types";

function check(outcome: string, latency_ms: number | null = 50): CheckResult {
  return {
    id: Math.random(),
    checked_at: new Date().toISOString(),
    outcome,
    status_code: outcome === "success" ? 200 : 500,
    latency_ms,
    error_code: null,
    error_message: null,
  };
}

describe("computeUptime", () => {
  it("returns null with no data", () => {
    const r = computeUptime([]);
    expect(r.ratio).toBeNull();
    expect(r.insufficient).toBe(true);
    expect(r.total).toBe(0);
  });

  it("computes the observed ratio over the window", () => {
    const r = computeUptime([check("success"), check("http_error"), check("success"), check("success")]);
    expect(r.ratio).toBeCloseTo(75);
    expect(r.successes).toBe(3);
    expect(r.total).toBe(4);
    expect(r.insufficient).toBe(false);
  });

  it("flags a small sample as insufficient", () => {
    const r = computeUptime([check("success")]);
    expect(r.ratio).toBe(100);
    expect(r.insufficient).toBe(true);
  });

  it("reports 0% when every check failed", () => {
    const r = computeUptime([check("timeout"), check("connection_error")]);
    expect(r.ratio).toBe(0);
    expect(r.successes).toBe(0);
    expect(r.total).toBe(2);
    expect(r.insufficient).toBe(true);
  });
});
