/** Presentation helpers (pure, unit-tested). */

const REASON_LABELS: Record<string, string> = {
  OUTSIDE_GEOFENCE: "Outside the campus area",
  BOUNDARY_UNCERTAIN: "Near the edge, within GPS error",
  GPS_ACCURACY_TOO_LOW: "GPS accuracy too low",
  LOCATION_TOO_OLD: "Location reading too old",
  LOCATION_IN_FUTURE: "Device clock ahead",
  NO_ACTIVE_GEOFENCE: "Campus has no active geofence",
  MOCK_LOCATION_REPORTED: "Mock location reported by the device",
  IMPLAUSIBLE_MOVEMENT: "Implausible movement since the previous event",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export function formatArea(m2: number): string {
  if (m2 >= 1_000_000) return `${(m2 / 1_000_000).toFixed(2)} km²`;
  if (m2 >= 10_000) return `${(m2 / 10_000).toFixed(2)} ha`;
  return `${Math.round(m2).toLocaleString("en-US")} m²`;
}

export function formatDateTime(iso: string, timeZone = "America/Bogota"): string {
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone,
  }).format(new Date(iso));
}

export function statusTone(status: string): "ok" | "warn" | "bad" | "neutral" {
  if (status === "VALIDATED") return "ok";
  if (status === "FLAGGED_FOR_REVIEW" || status === "PENDING") return "warn";
  if (status === "REJECTED") return "bad";
  return "neutral";
}

/** Parses "lat, lng" as typed or pasted from a map app. */
export function parseLatLng(text: string): { latitude: number; longitude: number } | null {
  const match = text.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const latitude = Number(match[1]);
  const longitude = Number(match[2]);
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null;
  return { latitude, longitude };
}

export function formatRate(rate: number | null): string {
  return rate === null ? "–" : `${Math.round(rate * 1000) / 10}%`;
}

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Default analytics range: Monday of the current week until today (local dates). */
export function defaultRange(today: Date): { from: string; to: string } {
  const monday = new Date(today);
  const offset = (today.getDay() + 6) % 7; // 0 = Monday
  monday.setDate(today.getDate() - offset);
  return { from: isoDate(monday), to: isoDate(today) };
}
