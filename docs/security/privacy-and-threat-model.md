# Privacy and threat model (initial)

This is a living document. It is not a legal opinion. Any real deployment in
Colombia needs review by a qualified professional under Law 1581 of 2012,
Decree 1377 of 2013 (incorporated into Decree 1074 of 2015) and the rules on
processing children's and adolescents' data.

## Personal data handled

| Data | Subjects | Sensitivity | Minimization |
|---|---|---|---|
| Name, email, student/employee code | All users | Personal | Required for the service |
| Date of birth | Students | Personal (minors) | Optional field |
| Guardian–student relationship | Guardians, students | Personal (minors) | Explicit authorization recorded |
| Location at attendance time | Students, staff | High (location of minors) | Captured only on user action; retention limit |
| Device identifiers, push token | Users | Personal | Revocable |
| Attendance history | Students, staff | Personal | Role-scoped access |

## Principles applied in the design

- **No continuous tracking**: the mobile app requests location only when
  the user taps an attendance action. No background location permission is
  requested.
- **Purpose limitation**: location is used only to validate the attendance
  event.
- **Retention**: precise coordinates are kept for a limited period (90 days by
  default, `LOCATION_RETENTION_DAYS`). After that, an hourly worker job clears
  them and keeps only the validation result (`geofence_result`, distance,
  status). The database only allows the worker role to do this, and only
  that (implemented in Week 7b).
- **Access control**: guardians see only linked students; teachers see only
  assigned classrooms; tenant isolation is enforced in the database (ADR-002).
- **Demonstration data is fictional**: the repository never contains real
  people's data.

## Threats (STRIDE, initial)

| Threat | Example | Mitigation (planned week) |
|---|---|---|
| Spoofing | Student shares credentials with a friend; GPS spoofing app | Device registration and binding (W2), mock-location flags (W5), movement plausibility (W3/W7), review queue. Residual risk accepted and documented |
| Tampering | Replaying a captured check-in request | Idempotency key, request-age window, TLS (W4) |
| Repudiation | "I never checked in" / admin edits attendance | Immutable events, actor recorded, append-only audit log (W4) |
| Information disclosure | Tenant A reads tenant B's students | RLS + membership-derived tenant + tests (W2) |
| Denial of service | Burst of check-ins at 7:00 | Rate limiting in Redis, load testing (W6/W7) |
| Elevation of privilege | Student calls admin endpoints | Role-based dependencies per endpoint; authorization tests (W2) |

## Known limitations (to state publicly)

GPS cannot guarantee a person's physical identity or presence, and
determined spoofing cannot be fully prevented on rooted or jailbroken
devices. SchoolTrack raises the cost of cheating and makes it auditable; it
does not make it impossible.
