import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, Easing, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { EVENT_LABELS, type EventType, STATE_LABELS, splitActions } from "../core/attendance";
import { colors, radius, stateTheme, typography } from "./theme";
import { Banner, type IconName, PressableScale, SectionTitle, initials, isToday, timeOf } from "./ui";
import type { AppData } from "./useAppData";

const ACTION_ICONS: Record<EventType, IconName> = {
  CHECK_IN: "enter-outline",
  TEMPORARY_CHECK_OUT: "walk-outline",
  RETURN: "return-down-back-outline",
  CHECK_OUT: "exit-outline",
};

const BUTTON = 184;

/** The big round button: it breathes while the phone looks for its location. */
function BellButton({
  eventType,
  busy,
  disabled,
  ring,
  onPress,
}: {
  eventType: EventType;
  busy: boolean;
  disabled: boolean;
  ring: string;
  onPress: () => void;
}) {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!busy) {
      pulse.stopAnimation();
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.timing(pulse, { toValue: 1, duration: 1300, easing: Easing.out(Easing.quad), useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [busy, pulse]);

  return (
    <View style={styles.bellWrap}>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.pulse,
          { borderColor: ring },
          {
            opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.7, 0] }),
            transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.35] }) }],
          },
        ]}
      />
      <PressableScale
        accessibilityRole="button"
        accessibilityLabel={EVENT_LABELS[eventType]}
        accessibilityState={{ disabled, busy }}
        disabled={disabled}
        onPress={onPress}
        scaleTo={0.93}
        style={[styles.bell, { borderColor: ring }, disabled && !busy && { opacity: 0.6 }]}
      >
        {busy ? (
          <ActivityIndicator size="large" color={colors.tinta} />
        ) : (
          <Ionicons name={ACTION_ICONS[eventType]} size={46} color={colors.tinta} />
        )}
        <Text style={styles.bellLabel}>{busy ? "Buscando tu ubicación…" : EVENT_LABELS[eventType]}</Text>
      </PressableScale>
    </View>
  );
}

export function HomeTab({ data }: { data: AppData }) {
  const insets = useSafeAreaInsets();
  const [refreshing, setRefreshing] = useState(false);
  const { me, membership, state, campuses, campusId, history, children, queued, offline, busy } = data;
  const firstName = me?.full_name.split(" ")[0] ?? "";
  const theme = stateTheme[state?.state ?? "OUTSIDE"];
  const { primary, secondary } = splitActions(state?.allowed_events ?? []);
  const last = history[0];
  const since = state && last && isToday(last.occurred_at) && last.state_after === state.state && queued.length === 0
    ? `desde las ${timeOf(last.occurred_at)}`
    : null;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.cal }}
      contentContainerStyle={{ paddingBottom: 28 }}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          tintColor={theme.fg}
          progressViewOffset={insets.top}
          onRefresh={async () => {
            setRefreshing(true);
            await data.load();
            setRefreshing(false);
          }}
        />
      }
    >
      <StatusBar style={state?.state === "TEMPORARY_EXIT" ? "dark" : "light"} />
      <View style={[styles.hero, { backgroundColor: theme.bg, paddingTop: insets.top + 20 }]}>
        <View style={styles.heroTop}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.hello, { color: theme.soft }]}>
              Hola{firstName ? `, ${firstName}` : ""}
            </Text>
            <Text style={[styles.school, { color: theme.fg }]} numberOfLines={1}>
              {membership?.institution_name ?? (offline ? "Sin conexión" : "")}
            </Text>
          </View>
          {offline ? <Ionicons name="cloud-offline-outline" size={24} color={theme.fg} /> : null}
        </View>

        {state ? (
          <View style={styles.stateBlock}>
            <Text style={[styles.stateCaption, { color: theme.soft }]}>
              {queued.length > 0 ? "Estado con tus registros pendientes" : "Ahora estás"}
            </Text>
            <Text style={[styles.state, { color: theme.fg }]}>{STATE_LABELS[state.state]}</Text>
            {since ? <Text style={[styles.since, { color: theme.soft }]}>{since}</Text> : null}
          </View>
        ) : children.length > 0 ? (
          <View style={styles.stateBlock}>
            <Text style={[styles.state, { color: theme.fg }]}>Tus estudiantes</Text>
            <Text style={[styles.since, { color: theme.soft }]}>Dónde están en este momento</Text>
          </View>
        ) : (
          <View style={{ height: 30 }} />
        )}

        {state && campuses.length > 1 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
            {campuses.map((c) => {
              const selected = c.id === campusId;
              return (
                <PressableScale
                  key={c.id}
                  onPress={() => data.setCampusId(c.id)}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  style={[styles.chip, selected && { backgroundColor: theme.fg }]}
                >
                  <Text style={[styles.chipText, { color: selected ? theme.bg : theme.fg }]}>{c.name}</Text>
                </PressableScale>
              );
            })}
          </ScrollView>
        ) : null}
        {state && primary ? <View style={{ height: BUTTON / 2 }} /> : null}
      </View>

      <View style={styles.body}>
        {state && primary ? (
          <>
            <View style={{ marginTop: -BUTTON / 2 - 10, alignItems: "center" }}>
              <BellButton
                eventType={primary}
                busy={busy === primary}
                disabled={busy !== null || !campusId}
                ring={theme.bg}
                onPress={() => void data.record(primary)}
              />
            </View>
            {secondary.length > 0 ? (
              <View style={styles.secondaryRow}>
                {secondary.map((eventType) => (
                  <PressableScale
                    key={eventType}
                    accessibilityRole="button"
                    disabled={busy !== null || !campusId}
                    onPress={() => void data.record(eventType)}
                    style={[styles.secondary, busy !== null && { opacity: 0.5 }]}
                  >
                    {busy === eventType ? (
                      <ActivityIndicator color={colors.tinta} />
                    ) : (
                      <Ionicons name={ACTION_ICONS[eventType]} size={20} color={colors.tinta} />
                    )}
                    <Text style={styles.secondaryText}>{EVENT_LABELS[eventType]}</Text>
                  </PressableScale>
                ))}
              </View>
            ) : null}
            <View style={styles.privacy}>
              <Ionicons name="location-outline" size={16} color={colors.muted} />
              <Text style={styles.privacyText}>
                Tu ubicación se consulta solo al tocar el botón. SchoolTrack no te rastrea.
              </Text>
            </View>
          </>
        ) : null}

        {data.outcome ? (
          <Banner
            tone={data.outcome.tone}
            title={data.outcome.title}
            details={data.outcome.details}
            onClose={data.dismissOutcome}
          />
        ) : null}
        {data.error ? <Banner tone="bad" title={data.error} onClose={data.dismissError} /> : null}
        {queued.length > 0 ? (
          <Banner
            tone="info"
            icon="cloud-upload-outline"
            title={`${queued.length} ${queued.length === 1 ? "registro pendiente" : "registros pendientes"} de envío`}
            details={["Están guardados en este celular y se envían solos cuando haya señal."]}
            action={{ label: "Enviar ahora", onPress: () => void data.load() }}
          />
        ) : null}

        {children.length > 0 ? (
          <>
            {state ? <SectionTitle>Tus estudiantes</SectionTitle> : null}
            {children.map((child) => {
              const t = stateTheme[child.state];
              return (
                <View key={child.student_id} style={styles.child}>
                  <View style={[styles.avatar, { backgroundColor: t.bg }]}>
                    <Text style={[styles.avatarText, { color: t.fg }]}>{initials(child.full_name)}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.childName}>{child.full_name}</Text>
                    <Text style={styles.childState}>{STATE_LABELS[child.state]}</Text>
                  </View>
                  <View style={[styles.dot, { backgroundColor: child.state === "OUTSIDE" ? "#c9cec6" : t.bg }]} />
                </View>
              );
            })}
          </>
        ) : null}

        {!state && children.length === 0 && !offline ? (
          <Banner
            tone="info"
            title="Tu cuenta aún no está vinculada"
            details={[
              "Pide a la institución que vincule tu correo a un estudiante, funcionario o acudiente.",
            ]}
          />
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: 24, paddingBottom: 34, borderBottomLeftRadius: 32, borderBottomRightRadius: 32 },
  heroTop: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  hello: { fontSize: 16, fontWeight: "600" },
  school: { fontSize: 18, fontWeight: "800", marginTop: 2 },
  stateBlock: { marginTop: 30 },
  stateCaption: { fontSize: 14, fontWeight: "600" },
  state: { ...typography.hero, fontSize: 40, lineHeight: 46, marginTop: 2 },
  since: { fontSize: 16, fontWeight: "600", marginTop: 4 },
  chips: { gap: 8, paddingTop: 18 },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.45)",
  },
  chipText: { fontWeight: "700" },
  body: { paddingHorizontal: 20, gap: 14 },
  bellWrap: { width: BUTTON, height: BUTTON, alignItems: "center", justifyContent: "center" },
  pulse: { position: "absolute", width: BUTTON, height: BUTTON, borderRadius: BUTTON / 2, borderWidth: 10 },
  bell: {
    width: BUTTON,
    height: BUTTON,
    borderRadius: BUTTON / 2,
    borderWidth: 10,
    backgroundColor: colors.paper,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingHorizontal: 18,
    elevation: 8,
    shadowColor: colors.tinta,
    shadowOpacity: 0.22,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
  bellLabel: { color: colors.tinta, fontWeight: "800", fontSize: 16, textAlign: "center" },
  secondaryRow: { flexDirection: "row", justifyContent: "center", gap: 10, flexWrap: "wrap" },
  secondary: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 12,
    paddingHorizontal: 18,
    borderRadius: 999,
    backgroundColor: colors.paper,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  secondaryText: { color: colors.tinta, fontWeight: "800", fontSize: 15 },
  privacy: { flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", paddingHorizontal: 12 },
  privacyText: { color: colors.muted, fontSize: 13, flexShrink: 1, textAlign: "center" },
  child: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    padding: 14,
    borderRadius: radius.md,
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: colors.border,
  },
  avatar: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  avatarText: { fontWeight: "800", fontSize: 16 },
  childName: { ...typography.heading, color: colors.text },
  childState: { color: colors.muted, fontSize: 14, marginTop: 2 },
  dot: { width: 12, height: 12, borderRadius: 6 },
});
