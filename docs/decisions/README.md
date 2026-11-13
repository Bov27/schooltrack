# Architecture Decision Records

Each significant decision gets a short record: context, options considered,
decision, consequences. Records are immutable once accepted. A later change is
recorded in a new ADR that supersedes the old one.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-modular-monolith.md) | Modular monolith vs microservices | Accepted |
| [002](ADR-002-shared-database-multi-tenancy.md) | Shared database multi-tenancy with RLS | Accepted |
| 003 | PostGIS geospatial validation | Planned (Week 3) |
| 004 | Attendance event state machine | Planned (Week 4) |
| 005 | Transactional outbox | Planned (Week 6) |

## Template

```markdown
# ADR-NNN: Title

- Status: Proposed | Accepted | Superseded by ADR-XXX
- Date: YYYY-MM-DD

## Context
## Options considered
## Decision
## Consequences
## How it is verified
```
