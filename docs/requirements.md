# Requirements

Status: draft for the MVP (v0.1). IDs are referenced from tests, ADRs and
issues.

## Functional requirements

### Identity and access (IAM)
- **FR-IAM-1**: Users authenticate with email and password and receive a
  short-lived JWT access token plus a rotating refresh token.
- **FR-IAM-2**: A user can hold several roles (School Admin, Teacher,
  Student, Staff, Guardian) in one or more institutions. Super Admin is a
  platform role.
- **FR-IAM-3**: Every request that touches tenant data is authorized against
  the user's active membership and role in the institution resolved by the
  backend.
- **FR-IAM-4**: Mobile devices are registered per user and can be revoked.
  Attendance events record the device that produced them.

### Institution management
- **FR-INS-1**: The Super Admin creates, suspends and lists institutions.
- **FR-INS-2**: The School Admin manages campuses, classrooms, schedules,
  students, staff, guardians and enrollments in their institution.
- **FR-INS-3**: The School Admin links guardians to students. Each link
  records who authorized it and when.

### Geolocation
- **FR-GEO-1**: The School Admin defines one or more geofence polygons per
  campus.
- **FR-GEO-2**: The backend decides whether a reported location is inside an
  active geofence of the campus. The client's own decision is never trusted.
- **FR-GEO-3**: Events are rejected or flagged when GPS accuracy, location
  age or request age exceed configurable thresholds. Initial values: 30 m,
  30 s and 15 s; geofence radius 100 m.
- **FR-GEO-4**: Mock-location and device-integrity signals reported by the
  OS are stored and taken into account where available.
- **FR-GEO-5**: Physically implausible sequences (for example two events far
  apart within seconds) are flagged for review.

### Attendance
- **FR-ATT-1**: Students and staff register CHECK_IN, TEMPORARY_CHECK_OUT,
  RETURN and CHECK_OUT.
- **FR-ATT-2**: Only the transitions of the state machine (see the project
  brief, section 6) are accepted. Invalid transitions are rejected with an
  explicit error.
- **FR-ATT-3**: Each event carries an idempotency key. Retries never create
  duplicates.
- **FR-ATT-4**: Events are immutable. Corrections and manual entries are new,
  audited records with a mandatory reason.
- **FR-ATT-5**: Each event has a validation status (PENDING, VALIDATED,
  REJECTED, FLAGGED_FOR_REVIEW) that is independent of the attendance state.
- **FR-ATT-6**: Users, teachers, admins and guardians see attendance history
  within the scope their role allows.
- **FR-ATT-7**: Guardians and teachers can submit excuses, and the School
  Admin approves or rejects them.

### Notifications, analytics, audit (after the MVP core)
- **FR-NOT-1**: Guardians receive absence and lateness alerts, with retries.
- **FR-ANA-1**: Attendance percentages per student and per classroom; CSV
  export.
- **FR-AUD-1**: Administrative actions and validation changes are written to
  an append-only audit log.

## Non-functional requirements

| ID | Category | Requirement | How it is verified |
|---|---|---|---|
| NFR-SEC-1 | Security | No cross-tenant read or write is possible through the API or the database role. | Automated tenant-isolation tests (Week 2 onward) |
| NFR-SEC-2 | Security | Passwords are hashed with Argon2id; JWT secrets come from the environment; tokens are short-lived. | Unit tests, configuration review |
| NFR-SEC-3 | Security | HTTPS only outside local development; CORS restricted to known origins. | Deployment checklist |
| NFR-PRV-1 | Privacy | Location is captured only when the user performs an attendance action. There is no background tracking. | Mobile code review, ADR |
| NFR-PRV-2 | Privacy | Precise coordinates have a retention limit (proposed 90 days) and are then reduced to the validation result. | Scheduled job + test |
| NFR-PRV-3 | Privacy | Minors' data is processed only with guardian authorization, following Law 1581 of 2012 and Decree 1377 of 2013. | Legal review before any real deployment |
| NFR-PERF-1 | Performance | `POST /attendance/events` p95 < 300 ms at 50 requests/s on the reference Docker setup (school opening peak). | Load test (Week 7) |
| NFR-REL-1 | Reliability | Attendance writes are transactional; notifications never block attendance (outbox + worker). | Integration tests, ADR-005 |
| NFR-OBS-1 | Observability | Structured JSON logs with a request ID; health endpoints for liveness and readiness. | Tests, manual check |
| NFR-QA-1 | Quality | ≥ 80 % line coverage in critical modules (auth, tenancy, geolocation, attendance); CI runs lint, type check and tests on every push. | GitHub Actions |
| NFR-PORT-1 | Portability | The full stack runs locally with `docker compose up`. | README instructions, CI |

## Explicit non-goals for the MVP

- Proving physical identity. GPS cannot do this, and the system does not
  claim it.
- Machine-learning anomaly detection. Deterministic rules come first.
- Microservices, multi-region deployment, or a database per tenant.
- Production readiness. That requires independent security, privacy and
  operations validation.

## Assumptions to confirm

1. A school day has one CHECK_IN and one CHECK_OUT per campus, plus any
   number of temporary exits.
2. Students of all ages may use the app, but young students usually rely on
   the teacher's manual entry.
3. Institutions operate in a single timezone per campus.
4. Guardians do not register attendance; they only view it and receive
   notifications.
