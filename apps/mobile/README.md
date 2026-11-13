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
- **Screens.** Four tabs: *Inicio* (state, the check-in button, students for guardians), *Historial*,
  *Avisos* and *Perfil* (institution, password, sign out). `src/screens/useAppData.ts` holds the data and
  actions they share. Icons come from `@expo/vector-icons`, insets from `react-native-safe-area-context`
  and tap feedback from `expo-haptics`, all included in Expo Go.
- **Map.** `src/core/mapHtml.ts` builds a self-contained page (tiles plus an SVG overlay, no external script)
  shown in `react-native-webview`. The location shown is the one the phone just read; it is kept in memory
  only. The server still never echoes coordinates to students or guardians.
- `src/core` is platform-independent and unit-tested with vitest; `src/platform` adapts it to Expo APIs.
- **Offline queue.** If an event cannot reach the server after the retries, it is saved in the OS keystore
  (one entry per event, at most 40) with its original time, location and idempotency key. The screen shows
  the predicted state and a pending count. The queue is sent to `POST /attendance/events/sync` on the
  next load or pull-to-refresh. Accepted, replayed and refused (4xx) events leave the queue; server
  errors (5xx) stay for the next attempt. The server applies the location rules at the time the event
  happened and refuses events older than 72 hours.
- **Guardians and notices.** A guardian account sees its students' current state and the in-app notices
  (`GET /notifications`); tapping a notice marks it as read.
- **Password change.** `POST /users/me/password` signs out every session, so the app returns to login.

## Push notifications

Push tokens are not registered yet. Expo Go no longer supports remote push on Android (SDK 53+), so
registering an Expo push token needs a development build (`npx expo run:android` or an EAS build) and
an EAS project id. The backend side is ready (`POST /devices` accepts a `push_token`; the worker has an Expo sender).
Until then, notices are shown inside the app.
