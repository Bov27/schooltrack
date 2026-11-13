import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useEffect, useRef, useState } from "react";
import {
  Animated,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../core/api";
import { api } from "../platform/services";
import { colors, radius } from "./theme";
import { Banner, PressableScale } from "./ui";

// Arched windows of a white colonial facade; some are lit, like classrooms in use.
const WINDOWS = [false, true, false, false, false, true, false, false];

function Facade() {
  const glow = useRef(new Animated.Value(0.55)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 1, duration: 1600, useNativeDriver: true }),
        Animated.timing(glow, { toValue: 0.55, duration: 1600, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [glow]);
  return (
    <View style={styles.facade} pointerEvents="none">
      {WINDOWS.map((lit, i) =>
        lit ? (
          <Animated.View key={i} style={[styles.window, styles.lit, { opacity: glow }]} />
        ) : (
          <View key={i} style={[styles.window, i % 3 === 2 && styles.pale]} />
        ),
      )}
    </View>
  );
}

export function LoginScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const passwordRef = useRef<TextInput>(null);

  async function submit() {
    if (!email || !password) return;
    setBusy(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
      onSignedIn();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? "El correo o la contraseña no son correctos."
          : "No pudimos conectarnos. Revisa tu conexión e intenta de nuevo.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.cal }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <View style={[styles.hero, { paddingTop: insets.top + 28 }]}>
          <View style={styles.brand}>
            <View style={styles.mark}>
              <Ionicons name="notifications" size={20} color={colors.tinta} />
            </View>
            <Text style={styles.brandName}>SchoolTrack</Text>
          </View>
          <Text style={styles.title}>Registra tu asistencia con un toque.</Text>
          <Facade />
        </View>

        <View style={[styles.form, { paddingBottom: insets.bottom + 24 }]}>
          {error ? <Banner tone="bad" title={error} /> : null}
          <Text style={styles.label}>Correo</Text>
          <TextInput
            style={styles.input}
            placeholder="tu.correo@colegio.edu.co"
            placeholderTextColor="#9aa39a"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            returnKeyType="next"
            value={email}
            onChangeText={setEmail}
            onSubmitEditing={() => passwordRef.current?.focus()}
          />
          <Text style={styles.label}>Contraseña</Text>
          <View>
            <TextInput
              ref={passwordRef}
              style={[styles.input, { paddingRight: 52 }]}
              secureTextEntry={!visible}
              autoComplete="password"
              returnKeyType="go"
              value={password}
              onChangeText={setPassword}
              onSubmitEditing={() => void submit()}
            />
            <PressableScale
              accessibilityRole="button"
              accessibilityLabel={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
              onPress={() => setVisible((v) => !v)}
              style={styles.eye}
            >
              <Ionicons name={visible ? "eye-off-outline" : "eye-outline"} size={22} color={colors.muted} />
            </PressableScale>
          </View>
          <PressableScale
            accessibilityRole="button"
            disabled={busy || !email || !password}
            onPress={() => void submit()}
            style={[styles.button, (busy || !email || !password) && { opacity: 0.5 }]}
          >
            <Text style={styles.buttonText}>{busy ? "Ingresando…" : "Ingresar"}</Text>
          </PressableScale>
          <Text style={styles.note}>Usa la cuenta que te entregó tu institución.</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: colors.tinta,
    paddingHorizontal: 26,
    paddingBottom: 120,
    overflow: "hidden",
    borderBottomLeftRadius: 32,
    borderBottomRightRadius: 32,
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 10 },
  mark: { width: 36, height: 36, borderRadius: 11, backgroundColor: colors.pupitre, alignItems: "center", justifyContent: "center" },
  brandName: { color: "#fff", fontSize: 21, fontWeight: "800", letterSpacing: -0.4 },
  title: { color: "#fff", fontSize: 36, lineHeight: 40, fontWeight: "800", letterSpacing: -0.8, marginTop: 40, maxWidth: 300 },
  facade: { position: "absolute", right: -18, bottom: -26, flexDirection: "row", flexWrap: "wrap", width: 228, gap: 12 },
  window: { width: 45, height: 66, borderTopLeftRadius: 24, borderTopRightRadius: 24, borderRadius: 5, backgroundColor: colors.tinta2 },
  pale: { backgroundColor: "rgba(255,255,255,0.1)" },
  lit: { backgroundColor: colors.pupitre },
  form: { padding: 24, gap: 8 },
  label: { fontWeight: "800", color: colors.text, marginTop: 8 },
  input: {
    backgroundColor: colors.paper,
    borderColor: "#c9cec6",
    borderWidth: 1.5,
    borderRadius: radius.sm,
    padding: 14,
    fontSize: 16,
    color: colors.text,
  },
  eye: { position: "absolute", right: 6, top: 6, padding: 8 },
  button: { marginTop: 18, backgroundColor: colors.tinta, borderRadius: radius.sm, paddingVertical: 17, alignItems: "center" },
  buttonText: { color: "#fff", fontSize: 17, fontWeight: "800" },
  note: { color: colors.muted, textAlign: "center", marginTop: 10, fontSize: 14 },
});
