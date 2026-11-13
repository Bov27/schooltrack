"use client";

import "leaflet/dist/leaflet.css";

import type * as Leaflet from "leaflet";
import { useEffect, useRef, useState } from "react";

import type { Geofence } from "@/lib/types";

export type LatLng = [number, number];
export type MapMode = "view" | "test" | "polygon" | "circle";

export interface MapPoint {
  id: string;
  position: LatLng;
  tone: "ok" | "warn" | "bad";
  label: string;
}

export interface Draft {
  polygon: LatLng[];
  circle: { center: LatLng | null; radius: number };
}

const TONE_COLORS = { ok: "#1e6b52", warn: "#f2b318", bad: "#b3261e" } as const;
const ACTIVE = "#1e6b52";
const INACTIVE = "#8a948c";
const DRAFT = "#f2b318";
const DEFAULT_CENTER: LatLng = [2.4419, -76.6063]; // Popayán

/** Free tiles that need no key. Fine for a demo or a pilot; see docs/operations/maps.md. */
const BASE_LAYERS = {
  street: {
    label: "Mapa",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxNativeZoom: 19,
  },
  satellite: {
    label: "Satélite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imágenes &copy; Esri, Maxar, Earthstar Geographics",
    maxNativeZoom: 18,
  },
} as const;
type BaseLayer = keyof typeof BASE_LAYERS;

type LeafletModule = typeof Leaflet;

async function loadLeaflet(): Promise<LeafletModule> {
  const mod = await import("leaflet");
  return (mod as unknown as { default?: LeafletModule }).default ?? mod;
}

/** GeoJSON stores [lng, lat]; Leaflet wants [lat, lng]. */
function ring(geofence: Geofence): LatLng[] {
  return (geofence.area.coordinates[0] ?? []).map(([lng, lat]) => [lat ?? 0, lng ?? 0]);
}

export function CampusMap({
  geofences,
  points = [],
  mode,
  draft,
  probe,
  onMapClick,
  height = 420,
}: {
  geofences: Geofence[];
  points?: MapPoint[];
  mode: MapMode;
  draft: Draft;
  probe: MapPoint | null;
  onMapClick: (position: LatLng) => void;
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const leaflet = useRef<LeafletModule | null>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const tiles = useRef<Leaflet.TileLayer | null>(null);
  const layers = useRef<Record<"geofences" | "points" | "draft" | "probe", Leaflet.LayerGroup> | null>(null);
  const fitted = useRef(false);
  const clickHandler = useRef(onMapClick);
  const [ready, setReady] = useState(false);
  const [base, setBase] = useState<BaseLayer>("satellite");

  clickHandler.current = onMapClick;

  // Create the map once, on the client only (Leaflet needs `window`).
  useEffect(() => {
    let cancelled = false;
    void loadLeaflet().then((L) => {
      if (cancelled || !container.current || map.current) return;
      leaflet.current = L;
      const instance = L.map(container.current, { zoomControl: true, scrollWheelZoom: false }).setView(
        DEFAULT_CENTER,
        16,
      );
      instance.on("click", (event: Leaflet.LeafletMouseEvent) =>
        clickHandler.current([event.latlng.lat, event.latlng.lng]),
      );
      // Scroll-zoom only after the person interacts with the map, so the page scrolls normally.
      instance.on("focus", () => instance.scrollWheelZoom.enable());
      instance.on("blur", () => instance.scrollWheelZoom.disable());
      layers.current = {
        geofences: L.layerGroup().addTo(instance),
        points: L.layerGroup().addTo(instance),
        draft: L.layerGroup().addTo(instance),
        probe: L.layerGroup().addTo(instance),
      };
      map.current = instance;
      setReady(true);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      tiles.current = null;
      layers.current = null;
      fitted.current = false;
    };
  }, []);

  // Base layer.
  useEffect(() => {
    const L = leaflet.current;
    if (!ready || !L || !map.current) return;
    tiles.current?.remove();
    const spec = BASE_LAYERS[base];
    tiles.current = L.tileLayer(spec.url, {
      attribution: spec.attribution,
      maxZoom: 20,
      maxNativeZoom: spec.maxNativeZoom,
    }).addTo(map.current);
  }, [ready, base]);

  // Geofences; the view fits them the first time they arrive.
  useEffect(() => {
    const L = leaflet.current;
    if (!ready || !L || !layers.current || !map.current) return;
    const group = layers.current.geofences;
    group.clearLayers();
    for (const g of geofences) {
      const color = g.is_active ? ACTIVE : INACTIVE;
      L.polygon(ring(g), {
        color,
        weight: 3,
        fillColor: color,
        fillOpacity: g.is_active ? 0.18 : 0.06,
        dashArray: g.is_active ? undefined : "6 6",
        interactive: false,
      })
        .bindTooltip(`${g.name}${g.is_active ? "" : " (inactiva)"}`, { sticky: true })
        .addTo(group);
    }
    if (!fitted.current && geofences.length > 0) {
      const bounds = L.latLngBounds(geofences.flatMap(ring));
      if (bounds.isValid()) {
        map.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 18 });
        fitted.current = true;
      }
    }
  }, [ready, geofences]);

  // Recent attendance events.
  useEffect(() => {
    const L = leaflet.current;
    if (!ready || !L || !layers.current) return;
    const group = layers.current.points;
    group.clearLayers();
    for (const p of points) {
      L.circleMarker(p.position, {
        radius: 6,
        color: "#ffffff",
        weight: 2,
        fillColor: TONE_COLORS[p.tone],
        fillOpacity: 1,
      })
        .bindTooltip(p.label)
        .addTo(group);
    }
  }, [ready, points]);

  // What is being drawn.
  useEffect(() => {
    const L = leaflet.current;
    if (!ready || !L || !layers.current) return;
    const group = layers.current.draft;
    group.clearLayers();
    const style = { color: DRAFT, weight: 3, fillColor: DRAFT, fillOpacity: 0.2, interactive: false };
    if (mode === "polygon" && draft.polygon.length > 0) {
      const shape = draft.polygon.length >= 3 ? L.polygon(draft.polygon, style) : L.polyline(draft.polygon, style);
      shape.addTo(group);
      draft.polygon.forEach((vertex, index) =>
        L.circleMarker(vertex, {
          radius: index === 0 ? 7 : 5,
          color: "#123a47",
          weight: 2,
          fillColor: "#ffffff",
          fillOpacity: 1,
          interactive: false,
        }).addTo(group),
      );
    }
    if (mode === "circle" && draft.circle.center) {
      L.circle(draft.circle.center, { ...style, radius: draft.circle.radius }).addTo(group);
      L.circleMarker(draft.circle.center, { radius: 5, color: "#123a47", fillColor: "#fff", fillOpacity: 1 }).addTo(
        group,
      );
    }
  }, [ready, mode, draft]);

  // The point being tested.
  useEffect(() => {
    const L = leaflet.current;
    if (!ready || !L || !layers.current) return;
    const group = layers.current.probe;
    group.clearLayers();
    if (probe) {
      L.circleMarker(probe.position, {
        radius: 10,
        color: "#ffffff",
        weight: 3,
        fillColor: TONE_COLORS[probe.tone],
        fillOpacity: 1,
      })
        .bindTooltip(probe.label, { permanent: true, direction: "top", offset: [0, -10] })
        .addTo(group);
    }
  }, [ready, probe]);

  // Crosshair while the next click does something.
  useEffect(() => {
    if (container.current) container.current.style.cursor = mode === "view" ? "" : "crosshair";
  }, [mode]);

  return (
    <div className="map-frame">
      <div ref={container} className="map" style={{ height }} role="application" aria-label="Mapa de la sede" />
      <div className="map-layers segmented" role="group" aria-label="Tipo de mapa">
        {(Object.keys(BASE_LAYERS) as BaseLayer[]).map((key) => (
          <button key={key} type="button" aria-pressed={base === key} onClick={() => setBase(key)}>
            {BASE_LAYERS[key].label}
          </button>
        ))}
      </div>
    </div>
  );
}
