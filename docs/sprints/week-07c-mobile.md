# Week 7c: mobile app (offline, guardians, password)

- [x] Offline queue (`src/core/offline.ts`), unit-tested with vitest:
  - events that could not be sent are kept in the OS keystore, one entry per event, capped at 40;
  - the predicted state includes queued events, so the right buttons show while offline;
  - the last known state and campuses are cached, so the app works when it starts offline;
  - sync on load and on pull-to-refresh; 4xx results leave the queue with a message, 5xx stay.
- [x] Guardian view: students in the guardian's care with their current state.
- [x] In-app notices with "mark as read".
- [x] Password change (every session is signed out afterwards).
- [ ] Push token registration: needs a development build (Expo Go dropped Android push in SDK 53).
  Documented in `apps/mobile/README.md`.
