import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, SafeAreaView, StyleSheet } from "react-native";

import { api, installationId } from "./src/platform/services";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";

type Phase = "starting" | "signed-out" | "signed-in";

async function registerDevice(): Promise<void> {
  // Best effort: attendance works without it, it only links events to this phone.
  await api
    .request("devices", {
      method: "POST",
      body: {
        installation_id: await installationId(),
        platform: Platform.OS === "ios" ? "IOS" : "ANDROID",
        model: String((Platform.constants as { Model?: string }).Model ?? Platform.OS).slice(0, 100),
        app_version: "0.1.0",
      },
    })
    .catch(() => undefined);
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("starting");

  useEffect(() => {
    api
      .resume()
      .then((resumed) => setPhase(resumed ? "signed-in" : "signed-out"))
      .catch(() => setPhase("signed-out"));
  }, []);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="dark" />
      {phase === "starting" && <ActivityIndicator style={styles.center} size="large" />}
      {phase === "signed-out" && (
        <LoginScreen
          onSignedIn={() => {
            void registerDevice();
            setPhase("signed-in");
          }}
        />
      )}
      {phase === "signed-in" && (
        <HomeScreen
          onSignedOut={() => {
            void api.logout();
            setPhase("signed-out");
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#f6f7f9" },
  center: { flex: 1 },
});
