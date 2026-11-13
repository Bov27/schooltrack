/** Attendance domain logic for the app (pure). */

export type EventType = "CHECK_IN" | "TEMPORARY_CHECK_OUT" | "RETURN" | "CHECK_OUT";
export type AttendanceState = "OUTSIDE" | "PRESENT" | "TEMPORARY_EXIT";

/** The subset of a location fix the app sends (from expo-location). */
export interface Fix {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  timestamp: number; // ms since epoch, when the OS obtained the fix
  mocked?: boolean; // Android only
}

export interface AttendanceEventRequest {
  idempotency_key: string;
  event_type: EventType;
  campus_id: string;
  occurred_at: string;
  latitude: number;
  longitude: number;
  accuracy_m: number;
  location_captured_at: string;
  is_mock?: boolean;
}

export interface AttendanceEvent {
  id: string;
  event_type: EventType;
  state_after: AttendanceState;
  validation_status: "PENDING" | "VALIDATED" | "REJECTED" | "FLAGGED_FOR_REVIEW";
  validation_reasons: string[];
  occurred_at: string;
  campus_id: string;
}

export interface SubjectState {
  subject: "STUDENT" | "STAFF";
  subject_id: string;
  state: AttendanceState;
  allowed_events: EventType[];
}

/** An accuracy we cannot know is treated as very poor, so the server rejects it
 * instead of the app pretending it was precise. */
const UNKNOWN_ACCURACY_M = 9_999;

export function buildEventRequest(params: {
  eventType: EventType;
  campusId: string;
  fix: Fix;
  idempotencyKey: string;
  occurredAt: Date;
}): AttendanceEventRequest {
  const { fix } = params;
  const request: AttendanceEventRequest = {
    idempotency_key: params.idempotencyKey,
    event_type: params.eventType,
    campus_id: params.campusId,
    occurred_at: params.occurredAt.toISOString(),
    latitude: fix.latitude,
    longitude: fix.longitude,
    accuracy_m: fix.accuracy ?? UNKNOWN_ACCURACY_M,
    location_captured_at: new Date(fix.timestamp).toISOString(),
  };
  if (fix.mocked !== undefined) request.is_mock = fix.mocked;
  return request;
}

export const EVENT_LABELS: Record<EventType, string> = {
  CHECK_IN: "Registrar entrada",
  TEMPORARY_CHECK_OUT: "Salida temporal",
  RETURN: "Registrar regreso",
  CHECK_OUT: "Registrar salida",
};

/** Confirmation shown after a validated event. */
export const DONE_LABELS: Record<EventType, string> = {
  CHECK_IN: "Entrada registrada",
  TEMPORARY_CHECK_OUT: "Salida temporal registrada",
  RETURN: "Regreso registrado",
  CHECK_OUT: "Salida registrada",
};

/** Short names for the history list. */
export const HISTORY_LABELS: Record<EventType, string> = {
  CHECK_IN: "Entrada",
  TEMPORARY_CHECK_OUT: "Salida temporal",
  RETURN: "Regreso",
  CHECK_OUT: "Salida",
};

/** History query for the person using the app. Admin accounts can read every event of
 * the institution, so the app always asks explicitly for its own subject's events. */
export function ownHistoryPath(state: SubjectState | null, limit = 15): string | null {
  if (state === null) return null;
  const key = state.subject === "STUDENT" ? "student_id" : "staff_id";
  return `attendance/events?limit=${limit}&${key}=${encodeURIComponent(state.subject_id)}`;
}

export const STATE_LABELS: Record<AttendanceState, string> = {
  OUTSIDE: "Fuera del colegio",
  PRESENT: "En el colegio",
  TEMPORARY_EXIT: "Salida temporal",
};

const REASON_LABELS: Record<string, string> = {
  OUTSIDE_GEOFENCE: "Estás fuera del área de la sede.",
  BOUNDARY_UNCERTAIN: "Estás cerca del límite; un administrador lo revisará.",
  GPS_ACCURACY_TOO_LOW: "La señal GPS no es precisa. Sal a un lugar abierto e intenta de nuevo.",
  LOCATION_TOO_OLD: "La ubicación estaba desactualizada. Intenta de nuevo.",
  LOCATION_IN_FUTURE: "La hora de tu celular está adelantada. Revisa la configuración de fecha y hora.",
  NO_ACTIVE_GEOFENCE: "La sede no tiene un área configurada. Avísale a la institución.",
  MOCK_LOCATION_REPORTED: "Tu celular reporta una ubicación simulada; quedará en revisión.",
  IMPLAUSIBLE_MOVEMENT: "El desplazamiento desde tu último registro es inusual; quedará en revisión.",
};

export function reasonMessage(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export type Outcome = { tone: "ok" | "warn" | "bad"; title: string; details: string[] };

/** What to tell the user after the server answered. */
export function describeOutcome(event: AttendanceEvent, replay: boolean): Outcome {
  const details = event.validation_reasons.map(reasonMessage);
  if (replay) details.unshift("Este registro ya se había enviado; no se duplicó.");
  switch (event.validation_status) {
    case "VALIDATED":
      return { tone: "ok", title: DONE_LABELS[event.event_type], details };
    case "FLAGGED_FOR_REVIEW":
    case "PENDING":
      return { tone: "warn", title: "Registrado, pendiente de revisión", details };
    case "REJECTED":
      return { tone: "bad", title: "No se pudo validar tu ubicación", details };
  }
}

/** Network failures are retried with the SAME idempotency key, so a request that did
 * reach the server is never recorded twice. */
export async function withRetries<T>(
  action: () => Promise<T>,
  isRetryable: (error: unknown) => boolean,
  attempts = 3,
  delay = (attempt: number) => new Promise<void>((r) => setTimeout(r, 500 * 2 ** attempt)),
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await action();
    } catch (error) {
      if (attempt + 1 >= attempts || !isRetryable(error)) throw error;
      await delay(attempt);
    }
  }
}

const ACTION_PRIORITY: EventType[] = ["CHECK_IN", "RETURN", "CHECK_OUT", "TEMPORARY_CHECK_OUT"];

/** The big button gets the most common next action; the rest are smaller buttons. */
export function splitActions(allowed: EventType[]): { primary: EventType | null; secondary: EventType[] } {
  const ordered = ACTION_PRIORITY.filter((event) => allowed.includes(event));
  return { primary: ordered[0] ?? null, secondary: ordered.slice(1) };
}
