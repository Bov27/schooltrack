/** Presentation helpers (pure, unit-tested). */

const REASON_LABELS: Record<string, string> = {
  OUTSIDE_GEOFENCE: "Fuera del área de la sede",
  BOUNDARY_UNCERTAIN: "En el borde, dentro del margen del GPS",
  GPS_ACCURACY_TOO_LOW: "Precisión del GPS insuficiente",
  LOCATION_TOO_OLD: "Ubicación demasiado antigua",
  LOCATION_IN_FUTURE: "El reloj del celular está adelantado",
  NO_ACTIVE_GEOFENCE: "La sede no tiene geocerca activa",
  MOCK_LOCATION_REPORTED: "El celular reportó una ubicación simulada",
  IMPLAUSIBLE_MOVEMENT: "Movimiento imposible desde el registro anterior",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export function formatArea(m2: number): string {
  if (m2 >= 1_000_000) return `${(m2 / 1_000_000).toFixed(2)} km²`;
  if (m2 >= 10_000) return `${(m2 / 10_000).toFixed(2)} ha`;
  return `${Math.round(m2).toLocaleString("es-CO")} m²`;
}

export function formatDateTime(iso: string, timeZone = "America/Bogota"): string {
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone,
  }).format(new Date(iso));
}

const STATUS_LABELS: Record<string, string> = {
  VALIDATED: "Válido",
  FLAGGED_FOR_REVIEW: "Por revisar",
  PENDING: "Pendiente",
  REJECTED: "Rechazado",
  INSIDE: "Dentro",
  OUTSIDE: "Fuera",
  NOT_EVALUATED: "Sin evaluar",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export const EVENT_LABELS: Record<string, string> = {
  CHECK_IN: "Entrada",
  TEMPORARY_CHECK_OUT: "Salida temporal",
  RETURN: "Regreso",
  CHECK_OUT: "Salida",
};

export const SOURCE_LABELS: Record<string, string> = {
  MOBILE_GPS: "App con GPS",
  MANUAL: "Manual",
  OFFLINE_SYNC: "Sin conexión",
};

export const STATE_LABELS: Record<string, string> = {
  PRESENT: "En el colegio",
  TEMPORARY_EXIT: "Salida temporal",
  OUTSIDE: "Fuera",
};

const ROLE_LABELS: Record<string, string> = {
  SCHOOL_ADMIN: "Administración",
  TEACHER: "Docente",
  STUDENT: "Estudiante",
  STAFF: "Funcionario",
  GUARDIAN: "Acudiente",
};

/** The most relevant role first: an admin who also teaches is shown as an admin. */
export function roleLabel(roles: string[]): string {
  const first = Object.keys(ROLE_LABELS).find((r) => roles.includes(r));
  return first ? ROLE_LABELS[first] : "Miembro";
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function formatTime(iso: string, timeZone = "America/Bogota"): string {
  return new Intl.DateTimeFormat("es-CO", { timeStyle: "short", timeZone }).format(new Date(iso));
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
