# Contributing

## Language

Source code, identifiers, commit messages, technical documentation and API
messages are written in English.

## Workflow

1. Create a branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
2. Keep changes small and verifiable. Each feature ships with its tests.
3. Run the checks locally before pushing:
   ```bash
   cd backend && ruff check . && mypy app && pytest
   ```
4. Open a pull request. CI must be green before merging.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(attendance): reject invalid state transitions
fix(geolocation): use ST_Covers so boundary points count as inside
docs(adr): add ADR-003 PostGIS validation
```

## Rules that protect tenant isolation

Every new tenant-owned table must have:

- `institution_id uuid NOT NULL`
- `UNIQUE (institution_id, id)`, and composite foreign keys
  `(institution_id, x_id)` for references to other tenant tables
- `ENABLE` and `FORCE ROW LEVEL SECURITY` with the `tenant_isolation` policy
- explicit grants to `schooltrack_app`
- a tenant-isolation test

Never accept `institution_id` from a request body as the source of truth. The
tenant comes from the authenticated user's membership.

## Architecture decisions

Significant decisions are recorded in `docs/decisions/` using the template in
its README. If a pull request changes a decision, it adds a new ADR that
supersedes the old one.

## Data

Use only fictional data in fixtures, seeds and screenshots.
