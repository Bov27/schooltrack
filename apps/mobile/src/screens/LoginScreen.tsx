import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "../core/api";
import { api } from "../platform/services";
import { colors } from "./theme";

export function LoginScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
      onSignedIn();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? "Correo o contraseña incorrectos."
          : "No pudimos conectarnos. Revisa tu conexión e intenta de nuevo.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>SchoolTrack</Text>
      <Text style={styles.subtitle}>Registro de asistencia</Text>
      {error && <Text style={styles.error}>{error}</Text>}
      <TextInput
        style={styles.input}
        placeholder="Correo institucional"
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Contraseña"
        secureTextEntry
        autoComplete="password"
        value={password}
        onChangeText={setPassword}
        onSubmitEditing={() => void submit()}
      />
      <Pressable
        accessibilityRole="button"
        style={[styles.button, (busy || !email || !password) && styles.disabled]}
        disabled={busy || !email || !password}
        onPress={() => void submit()}
      >
        <Text style={styles.buttonText}>{busy ? "Ingresando…" : "Ingresar"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: 28, gap: 12 },
  title: { fontSize: 30, fontWeight: "700", color: colors.text },
  subtitle: { fontSize: 16, color: colors.muted, marginBottom: 12 },
  input: {
    backgroundColor: "#fff",
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
  },
  button: { backgroundColor: colors.accent, borderRadius: 10, padding: 15, alignItems: "center" },
  disabled: { opacity: 0.5 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  error: { backgroundColor: colors.badBg, color: colors.bad, padding: 12, borderRadius: 8 },
});
