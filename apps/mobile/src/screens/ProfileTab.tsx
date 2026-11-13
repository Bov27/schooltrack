import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError, SessionExpiredError } from "../core/api";
import { api } from "../platform/services";
import { colors, radius, typography } from "./theme";
import { Banner, type IconName, PressableScale, SectionTitle, TabHeader, initials } from "./ui";
import type { AppData } from "./useAppData";

const ROLE_LABELS: Record<string, string> = {
  SCHOOL_ADMIN: "Administración",
  TEACHER: "Docente",
  STUDENT: "Estudiante",
  STAFF: "Funcionario",
  GUARDIAN: "Acudiente",
};

function Row({ icon, label, onPress, danger }: { icon: IconName; label: string; onPress: () => void; danger?: boolean }) {
  return (
    <PressableScale scaleTo={0.98} accessibilityRole="button" onPress={onPress} style={styles.row}>
      <Ionicons name={icon} size={22} color={danger ? colors.bad : colors.tinta} />
      <Text style={[styles.rowText, danger && { color: colors.bad }]}>{label}</Text>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </PressableScale>
  );
}

function PasswordForm({ onChanged }: { onChanged: () => void }) {
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
      if (e instanceof SessionExpiredError) return onChanged();
      if (e instanceof ApiError && e.status === 400) setMessage("La contraseña actual no es correcta.");
      else if (e instanceof ApiError) setMessage(e.message);
      else setMessage("Sin conexión. Intenta de nuevo cuando tengas señal.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.card}>
      {message ? <Banner tone="bad" title={message} /> : null}
      <TextInput
        style={styles.input}
        placeholder="Contraseña actual"
        placeholderTextColor={colors.muted}
        secureTextEntry
        autoCapitalize="none"
        value={current}
        onChangeText={setCurrent}
      />
      <TextInput
        style={styles.input}
        placeholder="Nueva contraseña (12 o más caracteres)"
        placeholderTextColor={colors.muted}
        secureTextEntry
        autoCapitalize="none"
        value={next}
        onChangeText={setNext}
      />
      <PressableScale
        accessibilityRole="button"
        disabled={busy || !current || !next}
        onPress={() => void submit()}
        style={[styles.button, (busy || !current || !next) && { opacity: 0.5 }]}
      >
        <Text style={styles.buttonText}>{busy ? "Guardando…" : "Cambiar contraseña"}</Text>
      </PressableScale>
      <Text style={styles.hint}>Por seguridad, después tendrás que volver a ingresar.</Text>
    </View>
  );
}

export function ProfileTab({ data, onSignedOut }: { data: AppData; onSignedOut: () => void }) {
  const [showPassword, setShowPassword] = useState(false);
  const { me, membership } = data;
  const roles = membership?.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ");

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <StatusBar style="dark" />
      <ScrollView style={{ flex: 1, backgroundColor: colors.cal }} contentContainerStyle={{ paddingBottom: 28 }}>
        <TabHeader title="Perfil" />
        <View style={styles.body}>
          <View style={styles.identity}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initials(me?.full_name ?? "")}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.name}>{me?.full_name || "Sin conexión"}</Text>
              {me?.email ? <Text style={styles.meta}>{me.email}</Text> : null}
              {roles ? <Text style={styles.meta}>{roles}</Text> : null}
            </View>
          </View>

          {me && me.memberships.length > 1 ? (
            <>
              <SectionTitle>Institución</SectionTitle>
              {me.memberships.map((m) => {
                const selected = m.institution_id === membership?.institution_id;
                return (
                  <PressableScale
                    key={m.institution_id}
                    scaleTo={0.98}
                    accessibilityRole="radio"
                    accessibilityState={{ selected }}
                    onPress={() => void data.selectInstitution(m.institution_id)}
                    style={[styles.row, selected && { borderColor: colors.tinta }]}
                  >
                    <Ionicons name="school-outline" size={22} color={colors.tinta} />
                    <Text style={styles.rowText}>{m.institution_name}</Text>
                    <Ionicons
                      name={selected ? "radio-button-on" : "radio-button-off"}
                      size={20}
                      color={selected ? colors.tinta : colors.muted}
                    />
                  </PressableScale>
                );
              })}
            </>
          ) : membership ? (
            <View style={styles.row}>
              <Ionicons name="school-outline" size={22} color={colors.tinta} />
              <Text style={styles.rowText}>{membership.institution_name}</Text>
            </View>
          ) : null}

          <SectionTitle>Cuenta</SectionTitle>
          <Row icon="lock-closed-outline" label="Cambiar contraseña" onPress={() => setShowPassword((v) => !v)} />
          {showPassword ? <PasswordForm onChanged={onSignedOut} /> : null}
          <Row icon="log-out-outline" label="Cerrar sesión" onPress={onSignedOut} danger />

          <View style={styles.privacy}>
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.muted} />
            <Text style={styles.privacyText}>
              SchoolTrack solo lee tu ubicación cuando registras asistencia. Nunca en segundo plano.
            </Text>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  body: { paddingHorizontal: 20, gap: 10 },
  identity: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    padding: 18,
    borderRadius: radius.lg,
    backgroundColor: colors.tinta,
  },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.pupitre,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 22, fontWeight: "800", color: colors.tinta },
  name: { ...typography.title, color: "#fff" },
  meta: { color: "#bcd1d6", fontSize: 14, marginTop: 2 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderRadius: radius.md,
    backgroundColor: colors.paper,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  rowText: { flex: 1, fontSize: 16, fontWeight: "700", color: colors.text },
  card: { gap: 10, padding: 16, borderRadius: radius.md, backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.border },
  input: {
    backgroundColor: colors.cal,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    padding: 14,
    fontSize: 16,
    color: colors.text,
  },
  button: { backgroundColor: colors.tinta, borderRadius: radius.sm, padding: 15, alignItems: "center" },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  hint: { color: colors.muted, fontSize: 13 },
  privacy: { flexDirection: "row", gap: 8, alignItems: "center", marginTop: 18, paddingHorizontal: 4 },
  privacyText: { flex: 1, color: colors.muted, fontSize: 13, lineHeight: 18 },
});
