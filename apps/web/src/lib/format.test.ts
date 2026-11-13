import { describe, expect, it } from "vitest";

import { defaultRange, formatArea, formatRate, parseLatLng, reasonLabel, statusTone } from "./format";

describe("format helpers", () => {
  it("labels known reasons and passes unknown ones through", () => {
    expect(reasonLabel("OUTSIDE_GEOFENCE")).toBe("Outside the campus area");
    expect(reasonLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });

  it.each([
    [850, "850 m²"],
    [31_416, "3.14 ha"],
    [2_500_000, "2.50 km²"],
  ])("formats %d m²", (m2, expected) => {
    expect(formatArea(m2)).toBe(expected);
  });

  it("maps statuses to tones", () => {
    expect(statusTone("VALIDATED")).toBe("ok");
    expect(statusTone("FLAGGED_FOR_REVIEW")).toBe("warn");
    expect(statusTone("REJECTED")).toBe("bad");
  });

  it.each([
    ["2.4419, -76.6063", { latitude: 2.4419, longitude: -76.6063 }],
    ["2.4419 -76.6063", { latitude: 2.4419, longitude: -76.6063 }],
    ["2.4419;-76.6063", { latitude: 2.4419, longitude: -76.6063 }],
  ])("parses %s", (text, expected) => {
    expect(parseLatLng(text)).toEqual(expected);
  });

  it.each(["", "abc", "95, 10", "2.44, 200", "2.44"])("rejects %j", (text) => {
    expect(parseLatLng(text)).toBeNull();
  });
});

describe("analytics helpers", () => {
  it("formats rates", () => {
    expect(formatRate(null)).toBe("–");
    expect(formatRate(0.6)).toBe("60%");
    expect(formatRate(0.8333)).toBe("83.3%");
  });

  it("defaults to Monday of the current week until today", () => {
    expect(defaultRange(new Date(2026, 10, 13))).toEqual({ from: "2026-11-09", to: "2026-11-13" });
    expect(defaultRange(new Date(2026, 10, 9))).toEqual({ from: "2026-11-09", to: "2026-11-09" });
    expect(defaultRange(new Date(2026, 10, 15))).toEqual({ from: "2026-11-09", to: "2026-11-15" });
  });
});
