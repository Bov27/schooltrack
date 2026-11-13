# SchoolTrack mobile (Expo)

The app students and staff use to record attendance.

## Run on your phone

1. Start the backend: `docker compose up` from the repository root.
2. Find your computer's LAN IP (e.g. `192.168.1.20`). The phone and the computer must be on the same network.
3. Install dependencies and start Expo:
   ```bash
   cd apps/mobile
   npm ci
   EXPO_PUBLIC_API_URL=http://192.168.1.20:8000 npx expo start
   ```
4. Scan the QR code with **Expo Go** (Android/iOS).

Sign in with an account that is linked to a student or staff record (register one from the dashboard,
"Students & staff", using the account's email).

## Design notes

- **Location only on demand.** The app requests *foreground* permission and reads one high-accuracy fix
  when the user taps an action. Background location is explicitly blocked in `app.json`.
- **Tokens.** The access token is held in memory only; the refresh token is stored in the OS keystore
  (`expo-secure-store`). Refreshes are single-flight, because two parallel refreshes with the same token
  would trigger the server's token-reuse protection and log the user out.
- **Idempotency.** Each tap gets a UUID; network retries reuse it, so a request that reached the server
  is never recorded twice (the server answers 200 with the original event).
- **Plain-language results.** Rejection and review reasons are explained in Spanish, with what to do next.
- `src/core` is platform-independent and unit-tested with vitest; `src/platform` adapts it to Expo APIs.
