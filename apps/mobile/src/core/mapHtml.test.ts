import { describe, expect, it } from "vitest";

import { buildMapHtml, ringFromGeoJson, scriptJson } from "./mapHtml";

describe("map page", () => {
  it("turns GeoJSON [lng, lat] positions into [lat, lng]", () => {
    expect(ringFromGeoJson([[[-76.6, 2.44], [-76.5, 2.45]]])).toEqual([
      [2.44, -76.6],
      [2.45, -76.5],
    ]);
    expect(ringFromGeoJson([])).toEqual([]);
  });

  it("cannot break out of the script element", () => {
    const json = scriptJson({ name: "</script><script>alert(1)</script>" });
    expect(json).not.toContain("<");
    expect(JSON.parse(json)).toEqual({ name: "</script><script>alert(1)</script>" });
  });

  it("embeds the data and the chosen tiles, and loads no external script", () => {
    const html = buildMapHtml({
      geofences: [{ ring: [[2.44, -76.6], [2.45, -76.6], [2.45, -76.5]], active: true }],
      point: { position: [2.445, -76.55], accuracyM: 12, color: "#1e6b52" },
      base: "street",
    });
    expect(html).toContain("tile.openstreetmap.org");
    expect(html).toContain("2.445");
    expect(html).not.toMatch(/<script[^>]+src=/);
    expect(html).toContain("Acercar"); // zoom controls
    expect(html).toContain("pointermove"); // pan and pinch
  });
});
