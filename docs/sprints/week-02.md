# Week 2: Backend and authentication

## Delivered

- [x] Migration `0002`: `users`, `refresh_tokens`, `platform_admins`,
      `institutions`, `institution_memberships`, `user_roles`, `campuses`,
      with forced RLS, membership-scoped read policies and per-role grants
- [x] Third database role, `schooltrack_platform` (BYPASSRLS, not a
      superuser), for Super-Admin operations only (ADR-002)
- [x] Argon2id password hashing, uniform login timing and errors
- [x] JWT access and refresh tokens; refresh rotation with family revocation
      on reuse; logout
- [x] `GET /users/me` with active memberships and roles
- [x] Tenant-context dependency: `X-Institution-Id` checked against active
      membership, then `SET LOCAL app.current_institution_id`
- [x] Role guard `require_roles(...)` and platform-admin guard
- [x] `GET/POST /institutions`, `GET/POST /campuses`
- [x] `python -m app.cli create-platform-admin` to bootstrap the first Super
      Admin
- [x] Tests: token and password unit tests; API tests for authentication,
      authorization and tenant isolation; database-level tests (every tenant
      table has forced RLS and a policy, the runtime role sees nothing
      without context, the context does not outlive the transaction)

## Decisions

- **Explicit commits in services.** Tenant settings are transaction-local,
  so a service commits once, at the end of the unit of work. Anything not
  committed is rolled back when the request's session closes. This avoids
  depending on when FastAPI runs the teardown of `yield` dependencies.
- **`extra="forbid"` on request bodies.** Sending `institution_id` is a
  validation error, not something the server silently ignores. Clients find
  out immediately that they cannot choose the tenant.
- **`403` for both foreign and unknown institutions.** Institution IDs
  cannot be enumerated through the header.
- **Identity does not import institution models.** `/users/me` composes the
  two services in the router, following the ADR-001 module rule.

## Verification

| Check | Where | Result |
|---|---|---|
| Migration 0002 up/down/up; platform vs runtime role privileges; the API's SQL (`INSERT … RETURNING` under RLS, membership queries, refresh-token locking) | PostgreSQL 16, authoring environment | Passed |
| ruff, mypy, migrations, pytest (unit + integration on PostGIS) | GitHub Actions | See CI run for this commit |

## Deferred, on purpose

- Login rate limiting: needs Redis (Week 6).
- User invitations and password reset: built with the admin dashboard
  (Week 5).
- Device registration: built with the mobile app (Week 5).
- Audit log entries for platform actions: the `audit_logs` table arrives with
  the attendance engine (Week 4).
