import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { api, installationId } from "./src/platform/services";
import { LoginScreen } from "./src/screens/LoginScreen";
import { MainScreen } from "./src/screens/MainScreen";
import { colors } from "./src/screens/theme";

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
        app_version: "0.2.0",
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
    <SafeAreaProvider>
      <View style={styles.root}>
        {phase === "starting" && (
          <View style={styles.splash}>
            <StatusBar style="light" />
            <ActivityIndicator size="large" color={colors.pupitre} />
          </View>
        )}
        {phase === "signed-out" && (
          <LoginScreen
            onSignedIn={() => {
              void registerDevice();
              setPhase("signed-in");
            }}
          />
        )}
        {phase === "signed-in" && (
          <MainScreen
            onSignedOut={() => {
              void api.logout();
              setPhase("signed-out");
            }}
          />
        )}
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.cal },
  splash: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.tinta },
});
