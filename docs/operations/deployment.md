# Deployment and release guide

SchoolTrack is an MVP for demonstration. This guide describes how its pieces fit
in a real deployment, but **do not use it with real personal data** until an
independent security and privacy review has been done.

## Services

| Service | Image | Database role | Notes |
|---|---|---|---|
| Migrations | `schooltrack-api` running `alembic upgrade head` | `schooltrack` (owner) | Run once per release, before the API starts. |
| API | `schooltrack-api` | `schooltrack_app` (RLS enforced) + `schooltrack_platform` for Super Admin endpoints | Stateless; scale horizontally. |
| Worker | `schooltrack-api` running `celery … worker` | `schooltrack_worker` (limited grants) | Outbox, notifications, retention. |
| Scheduler | `schooltrack-api` running `celery … beat` | same as worker | Exactly one instance. |
| Dashboard | `schooltrack-web` | none (talks to the API) | Set `SCHOOLTRACK_API_URL`. |
| PostgreSQL 16 + PostGIS 3.4 | managed service | | Create the three non-owner roles with `infrastructure/docker/postgres/initdb/20-create-app-role.sh`. |
| Redis 7 | managed service | | Celery broker and login rate limiting; no persistence needed. |

`docker-compose.yml` shows every variable each service needs.

## Settings that must change outside local development

- `ENVIRONMENT=staging` or `production`: this disables the API docs (unless
  `EXPOSE_DOCS=true`) and enables HSTS.
- `JWT_SECRET`: a long random value, stored as a secret.
- Every database password, and `CORS_ORIGINS` for the real dashboard origin.
- `PUSH_PROVIDER=expo` only once the mobile app is a development or store build.
- TLS in front of the API and the dashboard (the dashboard's production build marks
  its session cookies `Secure`).

## Releasing a version

1. Move the `Unreleased` items to a new section in `CHANGELOG.md`, for example
   `## [0.2.0] - YYYY-MM-DD`, and merge that change.
2. Tag the merge commit and push the tag:

   ```bash
   git tag -a v0.2.0 -m "SchoolTrack 0.2.0"
   git push origin v0.2.0
   ```

3. The `release` workflow builds `ghcr.io/<owner>/schooltrack-api` and
   `ghcr.io/<owner>/schooltrack-web`, tagged `0.2.0` and `0.2`, and creates the
   GitHub release with the changelog section as its notes.

The images are private by default in GHCR; change their visibility in the
package settings if you want them public.

## Checks that protect `main`

| Workflow | What it runs |
|---|---|
| `backend-ci` | ruff, mypy (strict), migrations up/down/up, pytest with PostGIS and Redis, load test |
| `web-ci` | type check, unit tests, production build |
| `mobile-ci` | type check, unit tests |
| `e2e` | the whole stack with docker compose, demo data, `scripts/e2e_smoke.py` |

Branch protection that requires these checks is configured in the repository
settings by its owner.
