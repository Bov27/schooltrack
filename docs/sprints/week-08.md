# Week 8: CI/CD, documentation, demo data and MVP release

## Goal

Make the MVP easy to try, verified end to end, and releasable with one tag.

## Done

- [x] **Demo data** (`python -m app.cli seed-demo`, `backend/app/demo.py`):
  - one fictional institution, a campus and a square geofence (optionally centred
    on given coordinates, so a phone can check in from where it is);
  - an admin, a teacher, eight students (one with an app account) and a guardian
    of two of them, all sharing a password chosen at run time;
  - ten school days of check-ins and check-outs with absences and a few flagged
    events, so the analytics have something to show;
  - refuses to run twice; covered by `tests/test_demo_data.py`, including a live
    check-in inside the generated geofence through the real validator.
- [x] **End-to-end test** (`scripts/e2e_smoke.py`, workflow `e2e`): builds the
  whole stack with docker compose, loads the demo data and checks the dashboard
  login and proxy, a live check-in and its idempotent retry, the worker notifying
  the guardian within 60 s, and the admin seeing the event.
- [x] **Release workflow**: a `v*.*.*` tag builds and publishes the API and
  dashboard images to GHCR and creates the GitHub release from `CHANGELOG.md`.
- [x] Dependabot for Actions, pip, npm and the backend Dockerfile.
- [x] Documentation: README (status, demo accounts), `CHANGELOG.md`,
  `docs/operations/deployment.md`.

## Release

`v0.1.0` is tagged after this week's PR is merged and CI is green on `main`.

## Known limitations of the MVP

- No push notifications on phones yet (notices are in-app); see the mobile README.
- No holiday calendar: analytics count every Monday to Friday.
- The dashboard is in English; the mobile app is in Spanish.
- Not reviewed by an independent security or privacy assessor.
