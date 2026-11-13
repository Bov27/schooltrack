# ADR-001: Modular monolith vs microservices

- Status: Accepted
- Date: 2026-11-12

## Context

SchoolTrack has eight functional areas: identity, institutions, geolocation,
attendance, notifications, analytics, audit and background processing. The
team is a single developer working on an 8-week roadmap. The heaviest
operation, an attendance write, needs data from identity, institutions,
geolocation and attendance inside **one** transaction: membership check,
geofence lookup, state lock, event insert and outbox row.

## Options considered

1. **Microservices** (one service per area, communicating over HTTP or a
   broker)
   - + Independent deployment and scaling per area.
   - − The attendance write becomes a distributed transaction (saga),
     because idempotency and the state machine span services.
   - − Tenant isolation must be enforced in every service and every
     database.
   - − It multiplies infrastructure, CI pipelines and observability needs.
     That effort is spent on plumbing rather than on the domain.
2. **Traditional layered monolith** (global `models/`, `services/`,
   `routers/` folders)
   - + Simplest to start.
   - − No boundaries between areas. Coupling grows silently, and a later
     split becomes expensive.
3. **Modular monolith**: one deployable unit, with explicit modules that own
   their tables and expose a service interface.
   - + Single ACID transaction for the attendance write.
   - + One RLS setup and one place to test tenant isolation.
   - + Boundaries are visible, and a module can be extracted later if
     measurements justify it.
   - − Discipline is needed to respect boundaries, because the language does
     not enforce them.

## Decision

Option 3. One FastAPI application and one Celery worker process, built from
the same codebase and image. Module rules are listed in
`docs/architecture/overview.md`.

## Consequences

- Scaling is horizontal for the whole API. That is enough for the expected
  load (one burst per school at opening time).
- Notifications and other side effects stay asynchronous through the outbox
  (ADR-005), so the core path never depends on external providers. This is
  the main benefit microservices would have given, obtained without
  distribution.
- Extracting a module later (most likely notifications) requires its outbox
  consumer and tables to be separable. Keeping cross-module calls behind
  services preserves that option.

## How it is verified

- From Week 2, an import-linter rule (or an equivalent pytest check) forbids
  imports between modules except through `service` modules.
- The Week 7 load test validates that one deployable unit meets NFR-PERF-1.
