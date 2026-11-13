import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { HistoryTab } from "./HistoryTab";
import { HomeTab } from "./HomeTab";
import { NoticesTab } from "./NoticesTab";
import { ProfileTab } from "./ProfileTab";
import { colors } from "./theme";
import type { IconName } from "./ui";
import { useAppData } from "./useAppData";

type Tab = "home" | "history" | "notices" | "profile";

const TABS: { key: Tab; label: string; icon: IconName; active: IconName }[] = [
  { key: "home", label: "Inicio", icon: "home-outline", active: "home" },
  { key: "history", label: "Historial", icon: "time-outline", active: "time" },
  { key: "notices", label: "Avisos", icon: "notifications-outline", active: "notifications" },
  { key: "profile", label: "Perfil", icon: "person-circle-outline", active: "person-circle" },
];

export function MainScreen({ onSignedOut }: { onSignedOut: () => void }) {
  const data = useAppData(onSignedOut);
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>("home");
  const fade = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    fade.setValue(0);
    Animated.timing(fade, { toValue: 1, duration: 180, useNativeDriver: true }).start();
  }, [tab, fade]);

  if (!data.loaded || !data.me) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color={colors.tinta} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.cal }}>
      <Animated.View style={{ flex: 1, opacity: fade }}>
        {tab === "home" && <HomeTab data={data} />}
        {tab === "history" && <HistoryTab data={data} />}
        {tab === "notices" && <NoticesTab data={data} />}
        {tab === "profile" && <ProfileTab data={data} onSignedOut={onSignedOut} />}
      </Animated.View>

      <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 10) }]} accessibilityRole="tablist">
        {TABS.map((t) => {
          const selected = t.key === tab;
          const badge = t.key === "notices" && data.unread > 0 ? data.unread : 0;
          return (
            <Pressable
              key={t.key}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              accessibilityLabel={badge ? `${t.label}, ${badge} sin leer` : t.label}
              style={styles.tab}
              onPress={() => {
                if (!selected) void Haptics.selectionAsync().catch(() => undefined);
                setTab(t.key);
              }}
            >
              <View style={[styles.pill, selected && styles.pillActive]}>
                <Ionicons name={selected ? t.active : t.icon} size={24} color={selected ? colors.tinta : colors.muted} />
                {badge ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{badge > 9 ? "9+" : badge}</Text>
                  </View>
                ) : null}
              </View>
              <Text style={[styles.label, selected && styles.labelActive]}>{t.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.cal },
  bar: {
    flexDirection: "row",
    paddingTop: 8,
    paddingHorizontal: 8,
    backgroundColor: colors.paper,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  tab: { flex: 1, alignItems: "center", gap: 3 },
  pill: { width: 60, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  pillActive: { backgroundColor: "#fdf0c8" },
  label: { fontSize: 12, fontWeight: "600", color: colors.muted },
  labelActive: { color: colors.tinta, fontWeight: "800" },
  badge: {
    position: "absolute",
    top: -2,
    right: 8,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: colors.bad,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: colors.paper,
  },
  badgeText: { color: "#fff", fontSize: 10, fontWeight: "800" },
});
