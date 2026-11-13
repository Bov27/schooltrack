/**
 * Offline queue (pure; storage injected).
 *
 * When an attendance action cannot reach the server, the complete request (with its
 * idempotency key, the moment of the tap and the GPS fix taken then) is stored in the
 * OS keystore, one entry per event (keystore values are small), plus an index. It is sent
 * later through POST /attendance/events/sync; the server applies the location rules at the
 * time of the event and refuses events older than 72 h.
 */

import type { SecureStorage } from "./api";
import type { AttendanceEventRequest, AttendanceState, EventType, SubjectState } from "./attendance";

export const QUEUE_INDEX_KEY = "schooltrack.offline.index";
export const LAST_STATE_KEY = "schooltrack.offline.last_state";
const ITEM_PREFIX = "schooltrack.offline.item.";
/** The server accepts at most 50 events per batch; keep a margin. */
export const MAX_QUEUE = 40;

export class QueueFullError extends Error {
  constructor() {
    super("Hay demasiados registros pendientes sin enviar. Conéctate para sincronizarlos.");
  }
}

export class OfflineQueue {
  constructor(private readonly storage: SecureStorage) {}

  async keys(): Promise<string[]> {
    const raw = await this.storage.get(QUEUE_INDEX_KEY);
    if (!raw) return [];
    try {
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter((k): k is string => typeof k === "string") : [];
    } catch {
      return [];
    }
  }

  async enqueue(request: AttendanceEventRequest): Promise<void> {
    const keys = await this.keys();
    if (keys.includes(request.idempotency_key)) return;
    if (keys.length >= MAX_QUEUE) throw new QueueFullError();
    // Write the item before the index, so a crash never leaves an index entry without data.
    await this.storage.set(ITEM_PREFIX + request.idempotency_key, JSON.stringify(request));
    await this.storage.set(QUEUE_INDEX_KEY, JSON.stringify([...keys, request.idempotency_key]));
  }

  async list(): Promise<AttendanceEventRequest[]> {
    const items: AttendanceEventRequest[] = [];
    for (const key of await this.keys()) {
      const raw = await this.storage.get(ITEM_PREFIX + key);
      if (raw) items.push(JSON.parse(raw) as AttendanceEventRequest);
    }
    return items.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
  }

  async remove(idempotencyKeys: string[]): Promise<void> {
    const drop = new Set(idempotencyKeys);
    const keys = await this.keys();
    await this.storage.set(QUEUE_INDEX_KEY, JSON.stringify(keys.filter((k) => !drop.has(k))));
    for (const key of idempotencyKeys) await this.storage.remove(ITEM_PREFIX + key);
  }
}

const TRANSITIONS: Record<AttendanceState, Partial<Record<EventType, AttendanceState>>> = {
  OUTSIDE: { CHECK_IN: "PRESENT" },
  PRESENT: { TEMPORARY_CHECK_OUT: "TEMPORARY_EXIT", CHECK_OUT: "OUTSIDE" },
  TEMPORARY_EXIT: { RETURN: "PRESENT" },
};

/**
 * The state the person will be in once the queued events are applied, so the app can
 * offer the right next action while offline. The server remains the authority: on sync
 * it may still refuse an event (and the app then shows why).
 */
export function predictState(server: SubjectState, queued: AttendanceEventRequest[]): SubjectState {
  let state = server.state;
  for (const event of queued) {
    const next = TRANSITIONS[state][event.event_type];
    if (next === undefined) break; // the server will refuse it; stop predicting here
    state = next;
  }
  const allowed = Object.keys(TRANSITIONS[state]) as EventType[];
  return { ...server, state, allowed_events: allowed };
}

export interface SyncItemResult {
  idempotency_key: string;
  outcome: "created" | "replayed" | "error";
  status_code: number;
  error?: string | null;
}

/** Which queued events can leave the queue after a sync: everything the server answered
 * definitively (stored, replayed, or refused with a 4xx that retrying cannot fix). */
export function settledKeys(results: SyncItemResult[]): string[] {
  return results
    .filter((r) => r.outcome !== "error" || (r.status_code >= 400 && r.status_code < 500))
    .map((r) => r.idempotency_key);
}

export function refusedMessages(results: SyncItemResult[]): string[] {
  return results
    .filter((r) => r.outcome === "error")
    .map((r) => r.error ?? `Error ${r.status_code}`);
}
