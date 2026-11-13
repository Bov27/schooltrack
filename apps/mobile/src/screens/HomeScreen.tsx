import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError, SessionExpiredError } from "../core/api";
import {
  type AttendanceEvent,
  type AttendanceEventRequest,
  EVENT_LABELS,
  type EventType,
  HISTORY_LABELS,
  type Outcome,
  STATE_LABELS,
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
import { colors } from "./theme";

interface Membership {
  institution_id: string;
  institution_name: string;
  roles: string[];
}
interface Me {
  full_name: string;
  memberships: Membership[];
}
interface Campus {
  id: string;
  name: string;
}
interface GuardedStudent {
  student_id: string;
  full_name: string;
  state: SubjectState["state"];
}
interface Notification {
  id: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

const CAMPUSES_KEY = "schooltrack.offline.campuses";
const isNetworkError = (e: unknown) => e instanceof TypeError; // fetch's "Network request failed"

async function readJson<T>(key: string): Promise<T | null> {
  const raw = await secureStorage.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function HomeScreen({ onSignedOut }: { onSignedOut: () => void }) {
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
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
        api.request<Notification[]>("notifications?limit=20").catch(() => [] as Notification[]),
      ]);
      const mine = states[0] ?? null;
      const historyPath = ownHistoryPath(mine);
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

  async function record(eventType: EventType) {
    if (!campusId) return;
    setBusy(eventType);
    setOutcome(null);
    setError(null);
    let request: AttendanceEventRequest | null = null;
    try {
      const fix = await currentFix(); // location is read only now, on the user's action
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
      setOutcome(describeOutcome(data, status === 200));
      await load();
    } catch (e) {
      if (request && isNetworkError(e)) {
        try {
          await offlineQueue.enqueue(request);
          setQueued(await offlineQueue.list());
          setOffline(true);
          setOutcome({
            tone: "warn",
            title: "Sin conexión: tu registro quedó guardado",
            details: ["Se enviará automáticamente cuando vuelvas a tener señal."],
          });
        } catch (queueError) {
          handle(queueError);
        }
      } else {
        handle(e);
      }
    } finally {
      setBusy(null);
    }
  }

  async function markRead(notification: Notification) {
    if (notification.read_at) return;
    try {
      await api.request(`notifications/${notification.id}/read`, { method: "POST" });
      setNotifications((list) =>
        list.map((n) => (n.id === notification.id ? { ...n, read_at: new Date().toISOString() } : n)),
      );
    } catch (e) {
      handle(e);
    }
  }

  if (!loaded || !me) return <ActivityIndicator style={{ flex: 1 }} size="large" />;
  const membership = me.memberships.find((m) => m.institution_id === api.institutionId);
  const state = serverState ? predictState(serverState, queued) : null;
  const plural = queued.length === 1 ? "" : "s";

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={async () => {
            setRefreshing(true);
            await load();
            setRefreshing(false);
          }}
        />
      }
    >
      <View style={styles.header}>
        <View>
          <Text style={styles.hello}>Hola{me.full_name ? `, ${me.full_name.split(" ")[0]}` : ""}</Text>
          <Text style={styles.muted}>{membership?.institution_name ?? ""}</Text>
        </View>
        <Pressable onPress={onSignedOut} accessibilityRole="button">
          <Text style={styles.link}>Salir</Text>
        </Pressable>
      </View>

      {me.memberships.length > 1 && (
        <View style={styles.row}>
          {me.memberships.map((m) => (
            <Chip
              key={m.institution_id}
              label={m.institution_name}
              selected={m.institution_id === api.institutionId}
              onPress={async () => {
                await api.selectInstitution(m.institution_id);
                setCampusId(null);
                await load();
              }}
            />
          ))}
        </View>
      )}

      {(offline || queued.length > 0) && (
        <View style={[styles.banner, styles.warn]}>
          <Text style={styles.outcomeTitle}>{offline ? "Sin conexión" : "Registros pendientes"}</Text>
          {queued.length > 0 && (
            <Text>
              {queued.length} registro{plural} guardado{plural} en este celular, pendiente{plural} de envío.
            </Text>
          )}
          <Pressable onPress={() => void load()} accessibilityRole="button">
            <Text style={styles.link}>Reintentar ahora</Text>
          </Pressable>
        </View>
      )}

      {error && <Text style={[styles.banner, styles.bad]}>{error}</Text>}

      {state !== null && (
        <View style={styles.card}>
          <Text style={styles.muted}>Estado actual{queued.length > 0 ? " (incluye registros pendientes)" : ""}</Text>
          <Text style={styles.state}>{STATE_LABELS[state.state]}</Text>

          {campuses.length > 1 && (
            <View style={styles.row}>
              {campuses.map((c) => (
                <Chip key={c.id} label={c.name} selected={c.id === campusId} onPress={() => setCampusId(c.id)} />
              ))}
            </View>
          )}

          {state.allowed_events.map((eventType) => (
            <Pressable
              key={eventType}
              accessibilityRole="button"
              style={[styles.action, busy !== null && styles.disabled]}
              disabled={busy !== null || !campusId}
              onPress={() => void record(eventType)}
            >
              <Text style={styles.actionText}>
                {busy === eventType ? "Obteniendo ubicación…" : EVENT_LABELS[eventType]}
              </Text>
            </Pressable>
          ))}
          <Text style={styles.privacy}>
            Tu ubicación se consulta solo al tocar el botón. SchoolTrack no te rastrea.
          </Text>
        </View>
      )}

      {outcome && (
        <View
          style={[styles.banner, outcome.tone === "ok" ? styles.ok : outcome.tone === "warn" ? styles.warn : styles.bad]}
        >
          <Text style={styles.outcomeTitle}>{outcome.title}</Text>
          {outcome.details.map((d) => (
            <Text key={d}>• {d}</Text>
          ))}
        </View>
      )}

      {children.length > 0 && (
        <>
          <Text style={styles.section}>Mis estudiantes</Text>
          {children.map((child) => (
            <View key={child.student_id} style={styles.historyRow}>
              <Text style={styles.historyType}>{child.full_name}</Text>
              <Text style={child.state === "PRESENT" ? { color: colors.ok } : styles.muted}>
                {STATE_LABELS[child.state]}
              </Text>
            </View>
          ))}
        </>
      )}

      {notifications.length > 0 && (
        <>
          <Text style={styles.section}>Avisos</Text>
          {notifications.map((n) => (
            <Pressable
              key={n.id}
              onPress={() => void markRead(n)}
              style={styles.historyRow}
              accessibilityRole="button"
            >
              <Text style={[styles.historyType, n.read_at === null && { color: colors.accent }]}>
                {n.read_at === null ? "● " : ""}
                {n.title}
              </Text>
              <Text>{n.body}</Text>
              <Text style={styles.muted}>{new Date(n.created_at).toLocaleString("es-CO")}</Text>
            </Pressable>
          ))}
        </>
      )}

      {state === null && children.length === 0 && !offline && (
        <View style={styles.card}>
          <Text style={styles.muted}>
            Tu cuenta no está vinculada a un estudiante, funcionario o acudiente en esta institución. Pide a la
            institución que registre tu correo como cuenta de la app.
          </Text>
        </View>
      )}

      {state !== null && <Text style={styles.section}>Mis últimos registros</Text>}
      {history.map((event) => (
        <View key={event.id} style={styles.historyRow}>
          <Text style={styles.historyType}>{HISTORY_LABELS[event.event_type]}</Text>
          <Text style={styles.muted}>{new Date(event.occurred_at).toLocaleString("es-CO")}</Text>
          <Text style={statusStyle(event.validation_status)}>{statusLabel(event.validation_status)}</Text>
        </View>
      ))}
      {state !== null && history.length === 0 && !offline && <Text style={styles.muted}>Aún no tienes registros.</Text>}

      {!offline && (
        <Pressable onPress={() => setShowPassword((v) => !v)} accessibilityRole="button">
          <Text style={[styles.link, { marginTop: 12 }]}>Cambiar contraseña</Text>
        </Pressable>
      )}
      {showPassword && !offline && <PasswordForm onChanged={onSignedOut} onSessionExpired={onSignedOut} />}
    </ScrollView>
  );
}

function PasswordForm({ onChanged, onSessionExpired }: { onChanged: () => void; onSessionExpired: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (next.length < 12) return setMessage("La nueva contraseña debe tener al menos 12 caracteres.");
    setBusy(true);
    setMessage(null);
    try {
      await api.request("users/me/password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      onChanged(); // the server signed out every session; log in again with the new password
    } catch (e) {
      if (e instanceof SessionExpiredError) return onSessionExpired();
      if (e instanceof ApiError && e.status === 400) setMessage("La contraseña actual no es correcta.");
      else if (e instanceof ApiError) setMessage(e.message);
      else setMessage("Sin conexión. Intenta de nuevo cuando tengas señal.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.card}>
      {message && <Text style={{ color: colors.bad }}>{message}</Text>}
      <TextInput
        style={styles.input}
        placeholder="Contraseña actual"
        secureTextEntry
        autoCapitalize="none"
        value={current}
        onChangeText={setCurrent}
      />
      <TextInput
        style={styles.input}
        placeholder="Nueva contraseña (12 o más caracteres)"
        secureTextEntry
        autoCapitalize="none"
        value={next}
        onChangeText={setNext}
      />
      <Pressable style={[styles.action, busy && styles.disabled]} disabled={busy} onPress={() => void submit()}>
        <Text style={styles.actionText}>{busy ? "Guardando…" : "Guardar y volver a ingresar"}</Text>
      </Pressable>
    </View>
  );
}

function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, selected && styles.chipSelected]} accessibilityRole="button">
      <Text style={selected ? styles.chipTextSelected : undefined}>{label}</Text>
    </Pressable>
  );
}

function statusLabel(status: AttendanceEvent["validation_status"]): string {
  return { VALIDATED: "Válido", FLAGGED_FOR_REVIEW: "En revisión", PENDING: "Pendiente", REJECTED: "Rechazado" }[
    status
  ];
}

function statusStyle(status: AttendanceEvent["validation_status"]) {
  if (status === "VALIDATED") return { color: colors.ok };
  if (status === "REJECTED") return { color: colors.bad };
  return { color: colors.warn };
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 14 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  hello: { fontSize: 24, fontWeight: "700", color: colors.text },
  muted: { color: colors.muted },
  link: { color: colors.accent, fontSize: 16 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 18,
    gap: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  state: { fontSize: 22, fontWeight: "700", color: colors.text },
  action: { backgroundColor: colors.accent, borderRadius: 12, padding: 16, alignItems: "center" },
  actionText: { color: "#fff", fontSize: 17, fontWeight: "600" },
  disabled: { opacity: 0.5 },
  privacy: { color: colors.muted, fontSize: 12 },
  banner: { padding: 14, borderRadius: 10, gap: 4 },
  ok: { backgroundColor: colors.okBg },
  warn: { backgroundColor: colors.warnBg },
  bad: { backgroundColor: colors.badBg, color: colors.bad },
  outcomeTitle: { fontWeight: "700", fontSize: 16 },
  section: { fontSize: 16, fontWeight: "600", marginTop: 8, color: colors.text },
  historyRow: {
    backgroundColor: "#fff",
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 2,
  },
  historyType: { fontWeight: "600", color: colors.text },
  input: { backgroundColor: "#fff", borderColor: colors.border, borderWidth: 1, borderRadius: 10, padding: 12 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#fff",
  },
  chipSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipTextSelected: { color: "#fff" },
});
