# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
