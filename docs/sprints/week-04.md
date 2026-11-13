# Week 4: Attendance engine

## Delivered

- [x] Migration `0004`: `devices`, `students`, `staff`, `attendance_events`,
      `attendance_subject_states`, `audit_logs`, with forced RLS, an
      immutability trigger on events and an append-only trigger on audit logs
- [x] State machine as a pure module; ADR-004
- [x] `POST /attendance/events`: idempotency, request age, device
      ownership, per-person row lock, transition check, location verdict
      (ADR-003) and movement plausibility
- [x] `GET /attendance/events` (role-scoped; coordinates only for admins),
      `GET /attendance/state`
- [x] `POST /attendance/manual-events` (School Admin, reason required,
      audited)
- [x] `POST /attendance/events/{id}/review` (School Admin, audited; only the
      validation status changes)
- [x] People: `POST/GET /students`, `POST/GET /staff` (linking an existing
      account adds the membership and role)
- [x] Devices: `POST/GET /devices` (idempotent per installation)
- [x] Tests: state machine (unit), attendance API, people API, concurrency
      (simultaneous check-ins and simultaneous retries)

## Notes

- **The geolocation module was not duplicated:** attendance calls
  `GeolocationService.evaluate`, the same function behind
  `POST /geofences/check`.
- **Rejected attempts are stored on purpose** (ADR-004). They are evidence,
  and they never move the state.
- **Deferred:**
  - daily `attendance_records` and `GET /attendance/records` (computed
    summaries; Week 7 with analytics);
  - teacher manual entries (need classrooms);
  - guardians (Week 5);
  - offline sync (Week 6).
