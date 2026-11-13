# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- New visual identity for the dashboard and the app, from Popayán's white colonial
  facades: lime-wash background, deep blue-green ink, chalkboard green for presence and
  school-desk yellow for temporary exits.
- Dashboard in Spanish, with a responsive sidebar (menu on small screens), new type
  (Bricolage Grotesque and Atkinson Hyperlegible) and a "Pase de lista" home page that
  shows every student's current state and refreshes every 30 seconds.
- Mobile app with bottom tabs (Inicio, Historial, Avisos, Perfil), a home header in the
  colour of the person's state, a large check-in button that pulses while locating,
  haptic feedback, a day-grouped history and an unread badge for notices.

### Added
- Campus map in the dashboard (Leaflet, OpenStreetMap and satellite imagery, no API key):
  geofences drawn over the map, the latest attendance events as coloured points, a point
  tester by clicking the map, and drawing a new geofence as a polygon or a circle.
- Records page: each event opens on the campus map with the GPS accuracy circle.
- Analytics: staff tab (teachers and other staff, School Admins only) and a per-person
  calendar of school days (attended, absent, under review, rejected attempt), backed by
  `GET /api/v1/analytics/staff` and `GET /api/v1/analytics/person`.
- Mobile app: after recording, or with "Ver dónde estoy en el mapa", the person sees
  their point and GPS accuracy over the campus geofence (satellite or street view). The
  map is a small self-contained page in a WebView; it loads no external script.
- `GET /api/v1/attendance/roster`: every active student with the current state and the
  last event, for school admins and teachers.

### Planned after the MVP
- Push notifications on phones (needs an Expo development build).
- Holiday calendar for analytics, and a map editor for geofences.
- Spanish interface for the dashboard (the mobile app is already in Spanish).
- Independent security and privacy review before any use with real data.

## [0.1.0] - 2026-11-13

First complete version (MVP), built over eight weekly iterations.

### Added
- Multi-tenant backend (FastAPI, PostgreSQL 16 + PostGIS) with tenant isolation
  enforced by Row-Level Security and four database roles.
- Authentication with Argon2id and rotating refresh tokens; roles for platform
  administrators, school administrators, teachers, students, staff and guardians.
- Campuses and geofences validated with PostGIS; GPS accuracy, location age,
  mock-location and implausible-movement checks.
- Attendance engine: state machine, idempotency keys, immutable events, review of
  flagged events and an append-only audit log.
- Transactional outbox with Celery workers: guardian notifications, delivery with
  retries, location retention (90 days) and outbox clean-up.
- Offline batch sync (72-hour window) and login rate limiting.
- Attendance analytics with CSV export.
- Next.js admin dashboard (BFF with httpOnly cookies): overview, attendance,
  campuses and geofences, people and accounts, analytics, institutions.
- Expo mobile app: on-demand location, check-in and check-out, offline queue,
  guardian view, in-app notices, password change.
- Fictional demo data (`python -m app.cli seed-demo`).
- CI for backend (lint, types, migrations, tests, load test), web and mobile; an
  end-to-end test of the whole stack; a release workflow publishing images to GHCR.

### Security
- Security headers, request size limit, API docs disabled outside local
  development, and a documented threat model.
