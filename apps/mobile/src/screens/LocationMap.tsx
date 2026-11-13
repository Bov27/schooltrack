import { Ionicons } from "@expo/vector-icons";
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { WebView } from "react-native-webview";

import { type MapBase, buildMapHtml, ringFromGeoJson } from "../core/mapHtml";
import { API_URL } from "../platform/services";
import { colors, radius } from "./theme";
import type { Geofence, LastFix } from "./useAppData";

const TONE_COLORS: Record<LastFix["tone"], string> = {
  ok: colors.pizarra,
  warn: colors.pupitre,
  bad: colors.bad,
  info: colors.tinta2,
};

/** Where the phone was, over the campus geofences. */
export function LocationMap({ fix, geofences, onClose }: { fix: LastFix; geofences: Geofence[]; onClose: () => void }) {
  const [base, setBase] = useState<MapBase>("satellite");
  const html = useMemo(
    () =>
      buildMapHtml({
        base,
        geofences: geofences.map((g) => ({ ring: ringFromGeoJson(g.area.coordinates), active: g.is_active })),
        point: { position: [fix.latitude, fix.longitude], accuracyM: fix.accuracy, color: TONE_COLORS[fix.tone] },
      }),
    [base, fix, geofences],
  );

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{fix.title}</Text>
          <Text style={styles.subtitle}>
            {fix.accuracy !== null ? `Precisión del GPS: ±${Math.round(fix.accuracy)} m` : "Precisión desconocida"}
          </Text>
        </View>
        <Pressable onPress={onClose} hitSlop={10} accessibilityRole="button" accessibilityLabel="Cerrar mapa">
          <Ionicons name="close" size={22} color={colors.muted} />
        </Pressable>
      </View>
      <View style={styles.mapWrap}>
        <WebView
          // The referrer tells the tile servers which app asks, as their usage policies require.
          source={{ html, baseUrl: API_URL }}
          originWhitelist={["*"]}
          scrollEnabled={false}
          // Let the map take the finger gestures instead of the page around it.
          nestedScrollEnabled
          style={styles.map}
          javaScriptEnabled
          setSupportMultipleWindows={false}
          accessibilityLabel="Mapa con tu ubicación y el área de la sede"
        />
        <View style={styles.toggle}>
          {(["satellite", "street"] as const).map((key) => (
            <Pressable
              key={key}
              onPress={() => setBase(key)}
              accessibilityRole="button"
              accessibilityState={{ selected: base === key }}
              style={[styles.toggleButton, base === key && styles.toggleActive]}
            >
              <Text style={[styles.toggleText, base === key && { color: colors.tinta }]}>
                {key === "satellite" ? "Satélite" : "Mapa"}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>
      <View style={styles.legend}>
        <View style={[styles.swatch, { backgroundColor: colors.pizarra }]} />
        <Text style={styles.legendText}>Área de la sede</Text>
        <View style={[styles.swatch, { backgroundColor: TONE_COLORS[fix.tone], borderRadius: 6 }]} />
        <Text style={styles.legendText}>Tu ubicación</Text>
      </View>
      {geofences.length === 0 ? (
        <Text style={styles.note}>No pudimos cargar el área de la sede; se muestra solo tu ubicación.</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.paper, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 },
  head: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  title: { fontSize: 16, fontWeight: "800", color: colors.text },
  subtitle: { color: colors.muted, fontSize: 13, marginTop: 2 },
  mapWrap: { height: 300, borderRadius: radius.sm, overflow: "hidden", backgroundColor: "#dfe5df" },
  map: { flex: 1, backgroundColor: "#dfe5df" },
  toggle: { position: "absolute", top: 8, right: 8, flexDirection: "row", backgroundColor: "rgba(255,255,255,0.92)", borderRadius: 999, padding: 3 },
  toggleButton: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 999 },
  toggleActive: { backgroundColor: "#fff", elevation: 1 },
  toggleText: { fontSize: 12, fontWeight: "800", color: colors.muted },
  legend: { flexDirection: "row", alignItems: "center", gap: 6 },
  swatch: { width: 12, height: 12, borderRadius: 3 },
  legendText: { color: colors.muted, fontSize: 13, marginRight: 10 },
  note: { color: colors.muted, fontSize: 13 },
});
