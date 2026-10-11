import { describe, expect, it } from "vitest";
import { fmtDuration, fmtInterval, fmtMs, fmtPercent } from "../domain/format";

describe("fmtDuration", () => {
  it("formats sub-second, seconds, minutes and hours", () => {
    expect(fmtDuration(420)).toBe("420ms");
    expect(fmtDuration(4500)).toBe("4.50s");
    expect(fmtDuration(65_000)).toBe("1m 5s");
    expect(fmtDuration(3_900_000)).toBe("1h 5m");
  });
});

describe("fmtInterval", () => {
  it("formats intervals compactly", () => {
    expect(fmtInterval(60)).toBe("1m");
    expect(fmtInterval(3600)).toBe("1h");
    expect(fmtInterval(86400)).toBe("1d");
  });
});

describe("fmtMs", () => {
  it("shows an em dash for missing latency", () => {
    expect(fmtMs(null)).toBe("—");
    expect(fmtMs(42)).toBe("42 ms");
  });
});

describe("fmtPercent", () => {
  it("shows an em dash for missing values and precision otherwise", () => {
    expect(fmtPercent(null)).toBe("—");
    expect(fmtPercent(100)).toBe("100.00%");
    expect(fmtPercent(99.5)).toBe("99.5%");
  });
});
