import * as Haptics from "expo-haptics";
import { useCallback, useEffect, useState } from "react";

import { ApiError, SessionExpiredError } from "../core/api";
import {
  type AttendanceEvent,
  type AttendanceEventRequest,
  type EventType,
  type Outcome,
  type SubjectState,
  buildEventRequest,
  describeOutcome,
  ownHistoryPath,
  withRetries,
} from "../core/attendance";
import {
  LAST_STATE_KEY,
  QueueFullError,
  type SyncItemResult,
  predictState,
  refusedMessages,
  settledKeys,
} from "../core/offline";
import {
  LocationPermissionError,
  api,
  currentFix,
  newIdempotencyKey,
  offlineQueue,
  secureStorage,
} from "../platform/services";

export interface Membership {
  institution_id: string;
  institution_name: string;
  roles: string[];
}
export interface Me {
  full_name: string;
  email?: string;
  memberships: Membership[];
}
export interface Campus {
  id: string;
  name: string;
}
export interface GuardedStudent {
  student_id: string;
  full_name: string;
  state: SubjectState["state"];
}
export interface Geofence {
  id: string;
  name: string;
  is_active: boolean;
  area: { type: "Polygon"; coordinates: number[][][] };
}
/** The last location read on this phone, kept in memory only to show it on a map. */
export interface LastFix {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  title: string;
  tone: "ok" | "warn" | "bad" | "info";
}
export interface Notification {
  id: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

const CAMPUSES_KEY = "schooltrack.offline.campuses";
export const isNetworkError = (e: unknown) => e instanceof TypeError; // fetch's "Network request failed"

async function readJson<T>(key: string): Promise<T | null> {
  const raw = await secureStorage.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

const HAPTIC: Record<Outcome["tone"], Haptics.NotificationFeedbackType> = {
  ok: Haptics.NotificationFeedbackType.Success,
  warn: Haptics.NotificationFeedbackType.Warning,
  bad: Haptics.NotificationFeedbackType.Error,
};

function feel(outcome: Outcome) {
  void Haptics.notificationAsync(HAPTIC[outcome.tone]).catch(() => undefined);
}

/** Everything the signed-in screens show, and the actions that change it. */
export function useAppData(onSignedOut: () => void) {
  const [me, setMe] = useState<Me | null>(null);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState<string | null>(null);
  const [serverState, setServerState] = useState<SubjectState | null>(null);
  const [queued, setQueued] = useState<AttendanceEventRequest[]>([]);
  const [offline, setOffline] = useState(false);
  const [history, setHistory] = useState<AttendanceEvent[]>([]);
  const [children, setChildren] = useState<GuardedStudent[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<EventType | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [lastFix, setLastFix] = useState<LastFix | null>(null);
  const [locating, setLocating] = useState(false);

  const handle = useCallback(
    (e: unknown) => {
      if (e instanceof SessionExpiredError) return onSignedOut();
      if (e instanceof LocationPermissionError || e instanceof ApiError || e instanceof QueueFullError) {
        return setError(e.message);
      }
      setError(isNetworkError(e) ? "Sin conexión. Intenta de nuevo cuando tengas señal." : String(e));
    },
    [onSignedOut],
  );

  /** Send events saved while offline; returns a user-facing outcome when there were any. */
  const syncQueue = useCallback(async (): Promise<Outcome | null> => {
    const pending = await offlineQueue.list();
    if (pending.length === 0) return null;
    const { results } = await api.request<{ results: SyncItemResult[] }>("attendance/events/sync", {
      method: "POST",
      body: { events: pending },
    });
    await offlineQueue.remove(settledKeys(results));
    const refused = refusedMessages(results);
    const sent = results.filter((r) => r.outcome !== "error").length;
    return refused.length
      ? { tone: "warn", title: `Se enviaron ${sent} de ${pending.length} registros guardados`, details: refused }
      : { tone: "ok", title: `Se enviaron ${sent} registros guardados sin conexión`, details: [] };
  }, []);

  const load = useCallback(async () => {
    try {
      const profile = await api.request<Me>("users/me");
      setMe(profile);
      if (!profile.memberships.some((m) => m.institution_id === api.institutionId) && profile.memberships[0]) {
        await api.selectInstitution(profile.memberships[0].institution_id);
      }
      const synced = await syncQueue();
      if (synced) setOutcome(synced);

      const [campusList, states, guarded, inbox] = await Promise.all([
        api.request<Campus[]>("campuses"),
        api.request<SubjectState[]>("attendance/state"),
        api.request<GuardedStudent[]>("attendance/guardian/students").catch(() => [] as GuardedStudent[]),
        api.request<Notification[]>("notifications?limit=30").catch(() => [] as Notification[]),
      ]);
      const mine = states[0] ?? null;
      const historyPath = ownHistoryPath(mine, 30);
      setCampuses(campusList);
      setCampusId((current) => current ?? campusList[0]?.id ?? null);
      setServerState(mine);
      setChildren(guarded);
      setNotifications(inbox);
      setHistory(historyPath ? await api.request<AttendanceEvent[]>(historyPath) : []);
      // Keep enough to go on working if the next start has no signal.
      await secureStorage.set(LAST_STATE_KEY, JSON.stringify(mine));
      await secureStorage.set(CAMPUSES_KEY, JSON.stringify(campusList));
      setOffline(false);
      setError(null);
    } catch (e) {
      if (isNetworkError(e)) {
        setOffline(true);
        const [lastState, lastCampuses] = await Promise.all([
          readJson<SubjectState>(LAST_STATE_KEY),
          readJson<Campus[]>(CAMPUSES_KEY),
        ]);
        if (lastState) setServerState((current) => current ?? lastState);
        if (lastCampuses) {
          setCampuses((current) => (current.length ? current : lastCampuses));
          setCampusId((current) => current ?? lastCampuses[0]?.id ?? null);
        }
        setMe((current) => current ?? { full_name: "", memberships: [] });
      } else {
        handle(e);
      }
    } finally {
      setQueued(await offlineQueue.list());
      setLoaded(true);
    }
  }, [handle, syncQueue]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!campusId) return;
    let cancelled = false;
    api
      .request<Geofence[]>(`geofences?campus_id=${encodeURIComponent(campusId)}`)
      .then((list) => !cancelled && setGeofences(list))
      .catch(() => !cancelled && setGeofences([]));
    return () => {
      cancelled = true;
    };
  }, [campusId]);

  /** Show where the phone is now, without recording anything. */
  const locateMe = useCallback(async () => {
    setLocating(true);
    setError(null);
    try {
      const fix = await currentFix();
      setLastFix({
        latitude: fix.latitude,
        longitude: fix.longitude,
        accuracy: fix.accuracy,
        title: "Tu ubicación ahora",
        tone: "info",
      });
    } catch (e) {
      handle(e);
    } finally {
      setLocating(false);
    }
  }, [handle]);

  const record = useCallback(
    async (eventType: EventType) => {
      if (!campusId) return;
      setBusy(eventType);
      setOutcome(null);
      setError(null);
      let request: AttendanceEventRequest | null = null;
      try {
        const fix = await currentFix(); // location is read only now, on the user's action
        const where = {
          latitude: fix.latitude,
          longitude: fix.longitude,
          accuracy: fix.accuracy,
          title: "Aquí registraste",
        };
        setLastFix({ ...where, tone: "info" });
        request = buildEventRequest({
          eventType,
          campusId,
          fix,
          idempotencyKey: newIdempotencyKey(), // reused by every retry and by the offline queue
          occurredAt: new Date(),
        });
        const body = request;
        const { status, data } = await withRetries(
          () => api.requestWithStatus<AttendanceEvent>("attendance/events", { method: "POST", body }),
          isNetworkError,
        );
        const result = describeOutcome(data, status === 200);
        setLastFix({ ...where, tone: result.tone });
        feel(result);
        setOutcome(result);
        await load();
      } catch (e) {
        if (request && isNetworkError(e)) {
          try {
            await offlineQueue.enqueue(request);
            setQueued(await offlineQueue.list());
            setOffline(true);
            const saved: Outcome = {
              tone: "warn",
              title: "Sin conexión: tu registro quedó guardado",
              details: ["Se enviará automáticamente cuando vuelvas a tener señal."],
            };
            feel(saved);
            setOutcome(saved);
          } catch (queueError) {
            handle(queueError);
          }
        } else {
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => undefined);
          handle(e);
        }
      } finally {
        setBusy(null);
      }
    },
    [campusId, handle, load],
  );

  const markRead = useCallback(
    async (notification: Notification) => {
      if (notification.read_at) return;
      try {
        await api.request(`notifications/${notification.id}/read`, { method: "POST" });
        setNotifications((list) =>
          list.map((n) => (n.id === notification.id ? { ...n, read_at: new Date().toISOString() } : n)),
        );
      } catch (e) {
        handle(e);
      }
    },
    [handle],
  );

  const selectInstitution = useCallback(
    async (institutionId: string) => {
      await api.selectInstitution(institutionId);
      setCampusId(null);
      setOutcome(null);
      await load();
    },
    [load],
  );

  return {
    me,
    membership: me?.memberships.find((m) => m.institution_id === api.institutionId) ?? null,
    campuses,
    campusId,
    setCampusId,
    state: serverState ? predictState(serverState, queued) : null,
    queued,
    offline,
    history,
    children,
    notifications,
    unread: notifications.filter((n) => n.read_at === null).length,
    outcome,
    dismissOutcome: () => setOutcome(null),
    error,
    dismissError: () => setError(null),
    busy,
    loaded,
    geofences,
    lastFix,
    clearFix: () => setLastFix(null),
    locating,
    locateMe,
    load,
    record,
    markRead,
    selectInstitution,
  };
}

export type AppData = ReturnType<typeof useAppData>;
