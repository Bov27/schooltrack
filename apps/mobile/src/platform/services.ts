/** React Native adapters for the platform-independent core. */
import * as Crypto from "expo-crypto";
import * as Location from "expo-location";
import * as SecureStore from "expo-secure-store";

import { ApiClient, type SecureStorage } from "../core/api";
import type { Fix } from "../core/attendance";

const secureStorage: SecureStorage = {
  get: (key) => SecureStore.getItemAsync(key),
  set: (key, value) => SecureStore.setItemAsync(key, value),
  remove: (key) => SecureStore.deleteItemAsync(key),
};

/** EXPO_PUBLIC_API_URL, e.g. http://192.168.1.20:8000 when testing on a phone. */
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = new ApiClient({
  baseUrl: API_URL,
  fetch: (input, init) => fetch(input, init),
  storage: secureStorage,
});

export function newIdempotencyKey(): string {
  return Crypto.randomUUID();
}

const INSTALLATION_KEY = "schooltrack.installation_id";

export async function installationId(): Promise<string> {
  const existing = await SecureStore.getItemAsync(INSTALLATION_KEY);
  if (existing) return existing;
  const created = Crypto.randomUUID();
  await SecureStore.setItemAsync(INSTALLATION_KEY, created);
  return created;
}

export class LocationPermissionError extends Error {}

/**
 * One fresh, high-accuracy fix, requested only when the user taps an attendance action.
 * Foreground permission only: the app never tracks location in the background.
 */
export async function currentFix(): Promise<Fix> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (permission.status !== Location.PermissionStatus.GRANTED) {
    throw new LocationPermissionError(
      "Para registrar tu asistencia necesitamos tu ubicación en este momento. Puedes permitirlo en Ajustes.",
    );
  }
  const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Highest });
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: position.coords.accuracy,
    timestamp: position.timestamp,
    mocked: position.mocked,
  };
}
