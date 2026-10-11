import { describe, expect, it } from "vitest";
import { monitorName, hostnameOf, redactUrl } from "../domain/status";

describe("monitorName", () => {
  it("derives a readable name from the hostname", () => {
    expect(monitorName({ id: 1, url: "https://api.example.com/health" })).toBe(
      "api.example.com",
    );
  });

  it("falls back to an id label when the URL is unparseable", () => {
    expect(monitorName({ id: 7, url: "not a url" })).toBe("Monitor 7");
  });
});

describe("hostnameOf", () => {
  it("extracts the hostname", () => {
    expect(hostnameOf("https://example.com:8443/x")).toBe("example.com");
  });
});

describe("redactUrl", () => {
  it("masks query-string values that could carry tokens", () => {
    expect(redactUrl("https://example.com/p?token=secret&x=1")).toBe(
      "https://example.com/p?token=***&x=***",
    );
  });

  it("leaves URLs without a query string untouched", () => {
    expect(redactUrl("https://example.com/health")).toBe("https://example.com/health");
  });
});
