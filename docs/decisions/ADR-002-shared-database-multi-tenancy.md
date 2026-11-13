# ADR-002: Shared database multi-tenancy with Row-Level Security

- Status: Accepted
- Date: 2026-11-12

## Context

Every school is a tenant. The data includes minors' personal data and
location, so a cross-tenant leak is the worst failure the system can have.
The expected scale is tens to low hundreds of institutions, each with up to
a few thousand people. Operational capacity is that of a small team.

## Options considered

1. **Database per tenant**
   - + Strongest isolation; per-tenant backup and restore.
   - − N migrations, N connection pools, N backups. Provisioning a school
     becomes an infrastructure operation. Cross-tenant platform reporting
     needs federation.
2. **Schema per tenant**
   - + Good isolation with one database.
   - − Migrations run N times. Catalog bloat with many schemas. The
     connection `search_path` must be switched per request, and an error
     there leaks data silently.
3. **Shared tables with `institution_id`, filtered only in application
   code**
   - + Simplest.
   - − One forgotten `WHERE institution_id = …` leaks data. Nothing in the
     database catches it.
4. **Shared tables with `institution_id` + PostgreSQL Row-Level Security
   + composite foreign keys**
   - + One schema and one migration path.
   - + The database enforces isolation even when application code has a
     bug.
   - − RLS has subtle traps: superusers and table owners bypass it, and
     foreign-key checks ignore it. Policies add a small planning cost.

## Decision

Option 4, built in layers (details in `docs/database/schema.md`):

1. The tenant is resolved from the authenticated user's **active
   membership**. A client-provided institution ID is only a hint; it is used
   after a membership check and never on its own.
2. Each request transaction sets `app.current_institution_id` and
   `app.current_user_id` with `SET LOCAL`, so the values cannot leak between
   pooled connections.
3. All tenant tables have `ENABLE` and `FORCE ROW LEVEL SECURITY` with
   `USING` and `WITH CHECK` on `institution_id`. A missing context returns
   no rows.
4. Composite foreign keys `(institution_id, x_id)` prevent cross-tenant
   references, because FK checks bypass RLS.
5. **Three database roles**:
   - `schooltrack` (owner): runs migrations; never used by the API.
   - `schooltrack_app`: the API runtime role. `NOSUPERUSER NOBYPASSRLS`,
     owns nothing.
   - `schooltrack_platform` (Week 2): `BYPASSRLS`, used only by
     Super-Admin endpoints behind a separate dependency, and audited.

## Consequences

- Every new tenant table must get `institution_id`, a composite unique key,
  an RLS policy and grants. A test enforces this, so forgetting one fails CI.
- Repositories still filter by `institution_id` explicitly. The SQL stays
  readable, indexes are used, and RLS acts as a second line of defence.
- Background jobs must set the tenant context per institution they process.
  A worker running without context sees nothing, which is safe but must be
  handled.
- Per-tenant export or deletion is a set of filtered queries, not a database
  drop.

## How it is verified

- Week 1: the reference schema was loaded into PostgreSQL 16 and an SQL
  smoke test confirmed isolation, `WITH CHECK` rejection, composite-FK
  rejection and fail-closed behaviour (see `docs/database/schema.md`).
- Week 2 onward: pytest tenant-isolation suite against PostGIS in CI, at both
  the API level (user of tenant A calling endpoints with tenant B IDs) and
  the database level (every tenant table has RLS forced and a policy).
