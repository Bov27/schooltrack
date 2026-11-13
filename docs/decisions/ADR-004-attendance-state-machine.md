# ADR-004: Attendance event state machine

- Status: Accepted
- Date: 2026-11-13

## Context

People check in and out several times a day: arrival, temporary exits (a
medical appointment, lunch at home) and departure. Phones retry requests on
flaky mobile networks, and the same person can trigger two requests at once
(a double tap, or the app retrying while the first request is still in
flight). The history must be trustworthy: corrections are made through
auditable actions, never by overwriting records.

## Options considered

1. **Mutable attendance record per day** (`check_in_at`, `check_out_at`
   columns, updated in place)
   - Simple to query.
   - Loses history: a correction erases the original. It cannot represent
     several temporary exits, and concurrent updates overwrite each other.
2. **Event log only, state derived by replaying events on every request**
   - Perfect history.
   - Each new event needs a read of the whole day. Concurrent requests can
     both derive "OUTSIDE" and both check in, unless something serializes them.
3. **Immutable event log + a current-state row per person, locked on write**
   - History is complete, and the current state is read in O(1).
   - `SELECT … FOR UPDATE` on the person's state row serializes that
     person's events and nobody else's.

## Decision

Option 3.

- **States and transitions:** four allowed transitions (`state_machine.py`,
  pure and exhaustively tested). Everything else, including a second
  CHECK_IN, is refused with **409** and nothing is stored. The error message
  lists the actions allowed next.
- **Validation status is a separate dimension** (VALIDATED, FLAGGED,
  REJECTED, PENDING), stored on the event:
  - VALIDATED and FLAGGED events advance the state. A flagged person is
    probably there, and blocking them at the gate would be worse than a
    later review.
  - REJECTED attempts are **stored, with the state unchanged**. A rejected
    attempt is evidence (who tried to check in from 300 m away, and when),
    and it feeds the review queue and future anomaly detection.
- **Idempotency:** every action carries a client-generated UUID, unique per
  `(institution, actor, key)`:
  - A retry returns the original event with **200**, even if the state has
    moved on since or the request is old.
  - Reusing a key for a different action is a 409.
  - The key is checked again *after* taking the lock, because a concurrent
    retry may have committed while this request waited.
- **Order of checks:**
  1. idempotency;
  2. request age (15 s, plus 5 s of clock-skew tolerance);
  3. device ownership;
  4. **lock**;
  5. idempotency again;
  6. transition;
  7. location verdict (ADR-003) plus movement plausibility;
  8. insert the event and update the state;
  9. commit.

  Cheap refusals happen before the lock, so they never queue behind other
  requests.
- **Movement plausibility:** if the speed implied by the previous located,
  non-rejected event and the new one exceeds 40 m/s (144 km/h), the event is
  flagged `IMPLAUSIBLE_MOVEMENT` (FR-GEO-5).
- **Immutability is enforced by the database,** not by convention:
  - a trigger rejects any change to an event except its validation fields,
    and rejects every delete, even from the owner role;
  - `audit_logs` is append-only through another trigger.
- **Corrections:**
  - A School Admin reviews a flagged or pending event. Only its validation
    status changes, and the decision and note are written to the audit log.
  - Manual events (no phone, no GPS) require a reason and are audited too.

## Consequences

- **Reviewing does not rewrite the state.** Rejecting a flagged CHECK_IN
  after the fact does not move the person back to OUTSIDE. The state is
  operational ("what can this person do next?"). Attendance reports (Week 7)
  are computed from events and exclude rejected ones, so they stay correct.
- **Offline synchronization (Week 6)** will submit events with
  `source = OFFLINE_SYNC`. They need their own request-age rule and ordering
  by `occurred_at`; the idempotency design already supports safe re-upload.
- **Teachers cannot record manual events yet.** That requires classroom
  assignments, so that a teacher can only mark their own students.

## How it is verified

- `tests/test_state_machine.py`: all 12 state/event combinations.
- `tests/test_attendance_api.py`, against PostGIS:
  - the full school day;
  - a duplicate check-in returns 409 and stores nothing;
  - retries return 200 with the same event, including a late retry;
  - key reuse is refused;
  - an attempt from outside is stored but the state does not change;
  - boundary, mock-location and implausible-movement cases are flagged;
  - stale and future requests are refused;
  - device ownership is checked;
  - the history is role-scoped and tenant-isolated;
  - reviews and manual events are written to the audit log;
  - events cannot be updated or deleted, even by the owner role.
- `tests/test_attendance_concurrency.py`:
  - 8 simultaneous check-ins with different keys produce exactly one event
    (the other 7 get 409);
  - 6 simultaneous retries with one key store it once and all receive the
    same event.
