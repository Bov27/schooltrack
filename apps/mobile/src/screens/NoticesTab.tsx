import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { colors, radius } from "./theme";
import { EmptyState, PressableScale, TabHeader, isToday, timeOf } from "./ui";
import type { AppData } from "./useAppData";

function when(iso: string): string {
  if (isToday(iso)) return `Hoy, ${timeOf(iso)}`;
  return new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function NoticesTab({ data }: { data: AppData }) {
  const [refreshing, setRefreshing] = useState(false);
  const subtitle =
    data.unread > 0
      ? `${data.unread} ${data.unread === 1 ? "aviso sin leer" : "avisos sin leer"}`
      : "Estás al día";

  return (
    <View style={{ flex: 1, backgroundColor: colors.cal }}>
      <StatusBar style="dark" />
      <TabHeader title="Avisos" subtitle={subtitle} />
      <FlatList
        data={data.notifications}
        keyExtractor={(n) => n.id}
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 28, gap: 10 }}
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
        renderItem={({ item }) => {
          const unread = item.read_at === null;
          return (
            <PressableScale
              scaleTo={0.98}
              accessibilityRole="button"
              accessibilityHint={unread ? "Marca el aviso como leído" : undefined}
              onPress={() => void data.markRead(item)}
              style={[styles.card, unread && styles.unread]}
            >
              <View style={[styles.icon, { backgroundColor: unread ? colors.tinta : "#e7eef0" }]}>
                <Ionicons name="notifications" size={18} color={unread ? "#fff" : colors.tinta2} />
              </View>
              <View style={{ flex: 1, gap: 3 }}>
                <View style={styles.top}>
                  <Text style={[styles.title, unread && { color: colors.tinta }]} numberOfLines={2}>
                    {item.title}
                  </Text>
                  {unread ? <View style={styles.badge} /> : null}
                </View>
                <Text style={styles.body}>{item.body}</Text>
                <Text style={styles.time}>{when(item.created_at)}</Text>
              </View>
            </PressableScale>
          );
        }}
        ListEmptyComponent={
          <EmptyState
            icon="notifications-outline"
            title="Sin avisos"
            text="Aquí verás las entradas y salidas de tus estudiantes y los mensajes de la institución."
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    gap: 14,
    padding: 16,
    borderRadius: radius.md,
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: colors.border,
  },
  unread: { borderColor: "#b7cbd0", backgroundColor: "#fbfcfb" },
  icon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  top: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  title: { flex: 1, fontSize: 16, fontWeight: "800", color: colors.text },
  badge: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.pupitre, marginTop: 5 },
  body: { fontSize: 15, color: colors.text, lineHeight: 21 },
  time: { fontSize: 13, color: colors.muted, marginTop: 2 },
});
