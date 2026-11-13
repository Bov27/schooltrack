# SchoolTrack

Geolocation-based, multi-tenant school attendance platform.

Students and staff register attendance from a mobile app. The backend
validates each event against the campus geofence with PostGIS, applies an
attendance state machine, and keeps an immutable, auditable history.
Guardians and school administrators follow attendance from the web dashboard
and through notifications.

> **Status: MVP (v0.1.0), Week 8 of 8.** This is a portfolio project. It is not
> production-ready and must not be used with real personal data until its
> security, privacy and operations have been independently validated.

## Highlights

- **Tenant isolation enforced by the database**: PostgreSQL Row-Level
  Security, composite foreign keys, and an API role that cannot bypass RLS
  ([ADR-002](docs/decisions/ADR-002-shared-database-multi-tenancy.md)).
- **Server-side geospatial validation** with PostGIS `GEOGRAPHY` and GiST
  indexes. GPS accuracy, location age and request age are checked against
  configurable thresholds.
- **Immutable attendance events**, with idempotency keys, an explicit state
  machine (`OUTSIDE → PRESENT ⇄ TEMPORARY_EXIT → OUTSIDE`) and validation
  status kept separate from attendance state.
- **Modular monolith**: FastAPI, SQLAlchemy 2.0 and Alembic, with clear
  module boundaries ([ADR-001](docs/decisions/ADR-001-modular-monolith.md)).
- **Offline-first mobile app**: events recorded without signal are kept in
  the OS keystore and synced later, with the location rules evaluated at the
  time the event happened.
- **Transactional outbox** feeding Celery workers that notify guardians
  ([ADR-005](docs/decisions/ADR-005-transactional-outbox.md)), and analytics
  with CSV export.
- **Measured**: a load test in CI checks the attendance endpoint against its
  latency target (p95 63 ms at 50 requests/s), and an end-to-end test drives
  the whole stack.
- **Privacy by design**: location is captured only on user action, never
  tracked continuously. The design takes into account Colombian data
  protection law (Law 1581 of 2012) and the rules for minors' data.

## Tech stack

| Layer | Technology |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async, psycopg 3), Alembic |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Async | Redis, Celery |
| Mobile | React Native, Expo SDK 54, TypeScript |
| Web | Next.js 15 (BFF), TypeScript |
| Tooling | Docker Compose, GitHub Actions, pytest, ruff, mypy |

## Quick start

Requirements: Docker with the Compose plugin.

```bash
git clone https://github.com/Bov27/schooltrack.git
cd schooltrack
docker compose up --build
```

This starts PostGIS and Redis, runs the migrations with the owner role, and
starts the API (restricted runtime role), the Celery worker and scheduler, and
the dashboard.

- Admin dashboard: <http://localhost:3000>
- API docs: <http://localhost:8000/api/v1/docs>
- Readiness: <http://localhost:8000/api/v1/health/ready>. It reports the
  database, the PostGIS version, and whether RLS is enforced for the API's
  role.

To change ports or passwords, copy `.env.example` to `.env`.

### Try it with demo data

Load the fictional demo institution (names, codes and e-mails are invented; the
`.test` domain never receives mail). You choose the shared password (12+
characters):

```bash
docker compose exec api python -m app.cli seed-demo
# Geofence around your own position, to test check-ins with your phone:
docker compose exec api python -m app.cli seed-demo --lat 2.4448 --lng -76.6147
```

| Account | Use it in | What it shows |
|---|---|---|
| `rectoria@demo.schooltrack.test` | Dashboard | Two weeks of attendance, analytics, people, geofence |
| `docente@demo.schooltrack.test` | Mobile app | Staff attendance |
| `estudiante@demo.schooltrack.test` | Mobile app | Student check-in, offline queue, history |
| `acudiente@demo.schooltrack.test` | Mobile app | Guardian view and notices |

The command refuses to run twice. Start over with `docker compose down -v`.

### Platform administrator

Create the first Super Admin, who creates institutions and assigns their admins
from the dashboard:

```bash
docker compose exec api python -m app.cli create-platform-admin \
    --email admin@example.test --name "Platform Admin"
```

If you started the stack before Week 6, recreate the database volume once with
`docker compose down -v`, so the newer database roles (`schooltrack_platform`,
`schooltrack_worker`) are created.
Authentication and tenant selection are described in
[docs/api/authentication.md](docs/api/authentication.md).

## Backend development without Docker

```bash
docker compose up -d db                 # only the database
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env                 # points to localhost:5432
alembic upgrade head
uvicorn app.main:app_factory --factory --reload
```

Checks (the same ones CI runs):

```bash
ruff check .
mypy app
pytest --cov                            # integration tests run when DATABASE_URL is set
```

## Repository layout

```
apps/mobile/             Expo app for students and staff (see apps/mobile/README.md)
apps/web/                Next.js admin dashboard (BFF: tokens stay in httpOnly cookies)
backend/                 FastAPI application, Alembic migrations, tests
infrastructure/docker/   database initialisation (runtime role)
scripts/                 end-to-end smoke test
docs/
  requirements.md        functional and non-functional requirements
  architecture/          system overview, module rules, risks
  database/              schema design (schema.sql) and rationale
  decisions/             Architecture Decision Records
  security/              privacy notes and threat model
  operations/            deployment and release guide
  sprints/               weekly plans and verification notes
.github/workflows/       CI (backend, web, mobile, e2e) and release
```

`apps/web` is the Next.js admin dashboard (`cd apps/web && npm install && npm run dev`, with
the API on port 8000). `apps/mobile` is the Expo app; see [its README](apps/mobile/README.md)
to run it on a phone with Expo Go. Business modules under
`backend/app/modules/` are added when they get their first feature.

## Roadmap

| Week | Focus | Status |
|---|---|---|
| 1 | Architecture, schema design, Docker, backend skeleton, CI | ✅ |
| 2 | Authentication, roles, institutions, tenant isolation tests | ✅ |
| 3 | Geofences and PostGIS validation | ✅ |
| 4 | Attendance engine: state machine, idempotency, audit | ✅ |
| 5 | Mobile app and admin dashboard | ✅ |
| 6 | Redis, Celery, notifications, offline sync | ✅ |
| 7 | Analytics, security hardening, load testing | ✅ |
| 8 | CI/CD, documentation, demo data, MVP release | ✅ |

What is next after the MVP is listed in the [changelog](CHANGELOG.md).

## Engineering approach

AI coding assistants are used as collaborators. Generated code is reviewed,
tested and measured, and significant decisions are recorded as ADRs with the
alternatives that were considered. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
