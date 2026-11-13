import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { RefreshControl, SectionList, StyleSheet, Text, View } from "react-native";

import { type AttendanceEvent, HISTORY_LABELS, reasonMessage } from "../core/attendance";
import { colors, radius } from "./theme";
import { EmptyState, type IconName, TabHeader, timeOf } from "./ui";
import type { AppData } from "./useAppData";

const STATUS: Record<AttendanceEvent["validation_status"], { label: string; color: string; icon: IconName }> = {
  VALIDATED: { label: "Válido", color: colors.ok, icon: "checkmark-circle" },
  FLAGGED_FOR_REVIEW: { label: "En revisión", color: colors.warn, icon: "time" },
  PENDING: { label: "Pendiente", color: colors.warn, icon: "time" },
  REJECTED: { label: "Rechazado", color: colors.bad, icon: "close-circle" },
};

function dayTitle(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Hoy";
  if (date.toDateString() === yesterday.toDateString()) return "Ayer";
  const text = date.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function groupByDay(events: AttendanceEvent[]) {
  const sections: { title: string; data: AttendanceEvent[] }[] = [];
  for (const event of events) {
    const title = dayTitle(event.occurred_at);
    const current = sections[sections.length - 1];
    if (current?.title === title) current.data.push(event);
    else sections.push({ title, data: [event] });
  }
  return sections;
}

export function HistoryTab({ data }: { data: AppData }) {
  const [refreshing, setRefreshing] = useState(false);
  const sections = groupByDay(data.history);

  return (
    <View style={{ flex: 1, backgroundColor: colors.cal }}>
      <StatusBar style="dark" />
      <TabHeader title="Historial" subtitle="Tus últimos registros de asistencia" />
      <SectionList
        sections={sections}
        keyExtractor={(event) => event.id}
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 28 }}
        stickySectionHeadersEnabled={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await data.load();
              setRefreshing(false);
            }}
          />
        }
        renderSectionHeader={({ section }) => <Text style={styles.day}>{section.title}</Text>}
        renderItem={({ item, index, section }) => {
          const status = STATUS[item.validation_status];
          const lastInDay = index === section.data.length - 1;
          return (
            <View style={styles.row}>
              <View style={styles.rail}>
                <View style={[styles.dot, { backgroundColor: status.color }]} />
                {!lastInDay ? <View style={styles.line} /> : null}
              </View>
              <View style={styles.card}>
                <View style={styles.cardTop}>
                  <Text style={styles.type}>{HISTORY_LABELS[item.event_type]}</Text>
                  <Text style={styles.time}>{timeOf(item.occurred_at)}</Text>
                </View>
                <View style={styles.status}>
                  <Ionicons name={status.icon} size={16} color={status.color} />
                  <Text style={[styles.statusText, { color: status.color }]}>{status.label}</Text>
                </View>
                {item.validation_reasons.map((reason) => (
                  <Text key={reason} style={styles.reason}>
                    {reasonMessage(reason)}
                  </Text>
                ))}
              </View>
            </View>
          );
        }}
        ListEmptyComponent={
          <EmptyState
            icon="time-outline"
            title="Aún no tienes registros"
            text={
              data.state
                ? "Cuando registres tu entrada en Inicio, aparecerá aquí."
                : "El historial es para estudiantes y funcionarios con cuenta vinculada."
            }
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  day: { fontSize: 15, fontWeight: "800", color: colors.tinta, marginTop: 18, marginBottom: 10 },
  row: { flexDirection: "row", gap: 12 },
  rail: { width: 14, alignItems: "center" },
  dot: { width: 12, height: 12, borderRadius: 6, marginTop: 20 },
  line: { flex: 1, width: 2, backgroundColor: colors.border, marginTop: 4 },
  card: {
    flex: 1,
    backgroundColor: colors.paper,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
    marginBottom: 10,
    gap: 4,
  },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  type: { fontSize: 17, fontWeight: "800", color: colors.text },
  time: { fontSize: 15, fontWeight: "700", color: colors.muted, fontVariant: ["tabular-nums"] },
  status: { flexDirection: "row", alignItems: "center", gap: 6 },
  statusText: { fontWeight: "700", fontSize: 14 },
  reason: { color: colors.muted, fontSize: 13, lineHeight: 18 },
});
