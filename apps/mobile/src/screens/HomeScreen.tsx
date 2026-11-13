import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, SessionExpiredError } from "../core/api";
import {
  type AttendanceEvent,
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
import { LocationPermissionError, api, currentFix, newIdempotencyKey } from "../platform/services";
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

const isNetworkError = (e: unknown) => e instanceof TypeError; // fetch's "Network request failed"

export function HomeScreen({ onSignedOut }: { onSignedOut: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState<string | null>(null);
  const [state, setState] = useState<SubjectState | null>(null);
  const [history, setHistory] = useState<AttendanceEvent[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const handle = useCallback(
    (e: unknown) => {
      if (e instanceof SessionExpiredError) return onSignedOut();
      if (e instanceof LocationPermissionError || e instanceof ApiError) return setError(e.message);
      setError(isNetworkError(e) ? "Sin conexión. Intenta de nuevo cuando tengas señal." : String(e));
    },
    [onSignedOut],
  );

  const load = useCallback(async () => {
    try {
      const profile = await api.request<Me>("users/me");
      setMe(profile);
      const memberships = profile.memberships;
      if (!memberships.some((m) => m.institution_id === api.institutionId) && memberships[0]) {
        await api.selectInstitution(memberships[0].institution_id);
      }
      const [campusList, states] = await Promise.all([
        api.request<Campus[]>("campuses"),
        api.request<SubjectState[]>("attendance/state"),
      ]);
      const mine = states[0] ?? null;
      const historyPath = ownHistoryPath(mine);
      setCampuses(campusList);
      setCampusId((current) => current ?? campusList[0]?.id ?? null);
      setState(mine);
      setHistory(historyPath ? await api.request<AttendanceEvent[]>(historyPath) : []);
      setError(null);
      setLoaded(true);
    } catch (e) {
      handle(e);
    }
  }, [handle]);

  useEffect(() => {
    void load();
  }, [load]);

  async function record(eventType: EventType) {
    if (!campusId) return;
    setBusy(eventType);
    setOutcome(null);
    setError(null);
    try {
      const fix = await currentFix(); // location is read only now, on the user's action
      const request = buildEventRequest({
        eventType,
        campusId,
        fix,
        idempotencyKey: newIdempotencyKey(), // reused by every retry of this action
        occurredAt: new Date(),
      });
      const { status, data } = await withRetries(
        () => api.requestWithStatus<AttendanceEvent>("attendance/events", { method: "POST", body: request }),
        isNetworkError,
      );
      setOutcome(describeOutcome(data, status === 200));
      await load();
    } catch (e) {
      handle(e);
    } finally {
      setBusy(null);
    }
  }

  if (!me || (!loaded && !error)) return <ActivityIndicator style={{ flex: 1 }} size="large" />;
  const membership = me.memberships.find((m) => m.institution_id === api.institutionId);

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
          <Text style={styles.hello}>Hola, {me.full_name.split(" ")[0]}</Text>
          <Text style={styles.muted}>{membership?.institution_name ?? "Sin institución"}</Text>
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

      {error && <Text style={[styles.banner, styles.bad]}>{error}</Text>}

      {state === null ? (
        <View style={styles.card}>
          <Text style={styles.muted}>
            Tu cuenta no está vinculada a un estudiante o funcionario en esta institución. Pide a la
            institución que registre tu correo como cuenta de la app.
          </Text>
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.muted}>Estado actual</Text>
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
        <View style={[styles.banner, outcome.tone === "ok" ? styles.ok : outcome.tone === "warn" ? styles.warn : styles.bad]}>
          <Text style={styles.outcomeTitle}>{outcome.title}</Text>
          {outcome.details.map((d) => (
            <Text key={d}>• {d}</Text>
          ))}
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
      {state !== null && history.length === 0 && <Text style={styles.muted}>Aún no tienes registros.</Text>}
    </ScrollView>
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
  return { VALIDATED: "Válido", FLAGGED_FOR_REVIEW: "En revisión", PENDING: "Pendiente", REJECTED: "Rechazado" }[status];
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
  card: { backgroundColor: "#fff", borderRadius: 14, padding: 18, gap: 12, borderWidth: 1, borderColor: colors.border },
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
  historyRow: { backgroundColor: "#fff", borderRadius: 10, padding: 12, borderWidth: 1, borderColor: colors.border },
  historyType: { fontWeight: "600", color: colors.text },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: "#fff" },
  chipSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipTextSelected: { color: "#fff" },
});
