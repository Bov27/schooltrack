/** Small building blocks shared by the signed-in screens. */
import { Ionicons } from "@expo/vector-icons";
import { type ReactNode, useEffect, useRef } from "react";
import {
  Animated,
  Pressable,
  type PressableProps,
  type StyleProp,
  StyleSheet,
  Text,
  View,
  type ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Outcome } from "../core/attendance";
import { colors, radius, typography } from "./theme";

export type IconName = keyof typeof Ionicons.glyphMap;

/** A pressable that shrinks slightly under the finger, so every tap has feedback. */
export function PressableScale({
  style,
  children,
  scaleTo = 0.96,
  ...props
}: Omit<PressableProps, "style" | "children"> & {
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
  scaleTo?: number;
}) {
  const scale = useRef(new Animated.Value(1)).current;
  const to = (value: number) =>
    Animated.spring(scale, { toValue: value, useNativeDriver: true, speed: 40, bounciness: 6 }).start();
  return (
    <Pressable {...props} onPressIn={() => to(scaleTo)} onPressOut={() => to(1)}>
      <Animated.View style={[style, { transform: [{ scale }] }]}>{children}</Animated.View>
    </Pressable>
  );
}

/** Plain header for the secondary tabs. */
export function TabHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.header, { paddingTop: insets.top + 18 }]}>
      <Text style={styles.headerTitle}>{title}</Text>
      {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

const TONES: Record<Outcome["tone"] | "info", { bg: string; fg: string; icon: IconName }> = {
  ok: { bg: colors.okBg, fg: colors.ok, icon: "checkmark-circle" },
  warn: { bg: colors.warnBg, fg: colors.warn, icon: "alert-circle" },
  bad: { bg: colors.badBg, fg: colors.bad, icon: "close-circle" },
  info: { bg: "#e7eef0", fg: colors.tinta, icon: "information-circle" },
};

/** A message that slides in when it appears. */
export function Banner({
  tone,
  title,
  details = [],
  icon,
  action,
  onClose,
}: {
  tone: Outcome["tone"] | "info";
  title: string;
  details?: string[];
  icon?: IconName;
  action?: { label: string; onPress: () => void };
  onClose?: () => void;
}) {
  const appear = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    appear.setValue(0);
    Animated.spring(appear, { toValue: 1, useNativeDriver: true, speed: 14, bounciness: 5 }).start();
  }, [appear, title]);
  const t = TONES[tone];
  return (
    <Animated.View
      accessibilityRole="alert"
      style={[
        styles.banner,
        { backgroundColor: t.bg },
        {
          opacity: appear,
          transform: [{ translateY: appear.interpolate({ inputRange: [0, 1], outputRange: [12, 0] }) }],
        },
      ]}
    >
      <Ionicons name={icon ?? t.icon} size={24} color={t.fg} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={[styles.bannerTitle, { color: t.fg }]}>{title}</Text>
        {details.map((d) => (
          <Text key={d} style={styles.bannerText}>
            {d}
          </Text>
        ))}
        {action ? (
          <Pressable onPress={action.onPress} accessibilityRole="button" hitSlop={8}>
            <Text style={[styles.bannerAction, { color: t.fg }]}>{action.label}</Text>
          </Pressable>
        ) : null}
      </View>
      {onClose ? (
        <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Cerrar" hitSlop={10}>
          <Ionicons name="close" size={20} color={colors.muted} />
        </Pressable>
      ) : null}
    </Animated.View>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.section}>{children}</Text>;
}

export function EmptyState({ icon, title, text }: { icon: IconName; title: string; text: string }) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIcon}>
        <Ionicons name={icon} size={30} color={colors.tinta2} />
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" });
}

export function isToday(iso: string): boolean {
  return new Date(iso).toDateString() === new Date().toDateString();
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: 22, paddingBottom: 14, backgroundColor: colors.cal },
  headerTitle: { ...typography.hero, color: colors.tinta },
  headerSubtitle: { color: colors.muted, fontSize: 15, marginTop: 4 },
  banner: { flexDirection: "row", gap: 12, padding: 16, borderRadius: radius.md, alignItems: "flex-start" },
  bannerTitle: { fontSize: 16, fontWeight: "800" },
  bannerText: { color: colors.text, fontSize: 14, lineHeight: 20 },
  bannerAction: { fontWeight: "800", marginTop: 4 },
  section: { ...typography.heading, color: colors.tinta, marginTop: 10 },
  empty: { alignItems: "center", paddingVertical: 48, paddingHorizontal: 28, gap: 8 },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: "#e7eef0",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 6,
  },
  emptyTitle: { ...typography.heading, color: colors.text },
  emptyText: { color: colors.muted, textAlign: "center", fontSize: 15, lineHeight: 21 },
});
