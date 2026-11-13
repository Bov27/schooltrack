# Week 6: Asynchronous processing, notifications, offline sync

## Delivered

- [x] Migration `0005`:
  - `guardians` and `student_guardians` (authorization recorded and
    audited);
  - `outbox_events`;
  - `notifications`, with an idempotency constraint;
  - `devices.push_token`;
  - forced RLS on all of them.
- [x] Fourth database role, `schooltrack_worker`: `BYPASSRLS`, with grants
      limited to background processing.
- [x] Transactional outbox for accepted student events (ADR-005).
- [x] Celery worker and beat (Redis broker):
  - dispatch fans out notifications to the guardians who opted in;
  - delivery sends them to Expo push, with backoff and a final `FAILED`
    state.
- [x] `GET /notifications` and `POST /notifications/{id}/read`.
- [x] Guardian management (`POST/GET /guardians`,
      `POST /guardians/{id}/students`) and the guardian view
      (`GET /attendance/guardian/students`). The attendance history is
      readable by authorized guardians, without coordinates.
- [x] Offline synchronization: `POST /attendance/events/sync`.
  - Up to 50 events per batch, applied oldest first, each in its own
    transaction, with one result per event.
  - The window is 72 h.
  - Location rules are evaluated at the time of the event.
  - An event older than the person's last one is refused.
  - Retrying a batch is safe.
- [x] Login rate limiting in Redis:
  - counts failed attempts per account and per client address;
  - email and IP are hashed before being used as Redis keys;
  - answers `429` with `Retry-After`;
  - fails open if Redis is down.
- [x] Compose: `redis`, `worker` and `beat` services. CI: Redis service and
      the worker role.

## Decisions

- **Offline events are not flagged automatically.** They go through the
  same location rules, evaluated at the moment they happened. Ordering is
  enforced, and the event keeps `source = OFFLINE_SYNC`, so reports and
  reviewers can tell them apart. Flagging every offline event would flood
  the review queue in schools with poor coverage.
- **Rate limiting fails open.** Locking every user out because Redis is down
  would be worse than briefly losing brute-force protection. The event is
  logged.

## Deferred

- The mobile app's offline queue and push-token registration (next step on
  the client).
- Absence and lateness alerts (they need schedules; Week 7).
- Purging processed outbox rows (data-retention task; Week 7).
