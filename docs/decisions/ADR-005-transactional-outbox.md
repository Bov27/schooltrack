# ADR-005: Transactional outbox

- Status: Accepted
- Date: 2026-11-13

## Context

When a student checks in, their guardians should be notified. Push delivery
goes through an external provider (Expo, which forwards to FCM or APNs).
Providers are slow, rate-limited and sometimes down. Two requirements pull
in opposite directions:

- **An attendance write must never fail or wait because of notifications**
  (NFR-REL-1).
- **A committed attendance event must eventually notify**, even if a
  process crashes right after the commit. Conversely, a rolled-back event
  must never notify.

## Options considered

1. **Send the push inside the request.** It is slow, it couples attendance
   availability to the provider, and it can notify about an event whose
   transaction later rolls back.
2. **Enqueue a Celery task directly after the commit.** If the process dies
   between the commit and the enqueue, the message is lost. If the task is
   enqueued before the commit, it may run for an event that never exists.
   This is the classic dual-write problem.
3. **Transactional outbox.** The request writes an `outbox_events` row in
   the **same transaction** as the event. A worker polls the outbox and
   performs the side effects.

## Decision

Option 3.

- `app/infrastructure/outbox.py::enqueue` inserts into `outbox_events` in
  the caller's transaction. The attendance engine enqueues
  `attendance.event_recorded` only for accepted student events (not for
  rejected attempts and not for refused transitions), which the tests check.
- **Worker**: Celery with Redis as the broker, and beat schedules for every
  5 s (dispatch) and 10 s (delivery). Its database role is
  `schooltrack_worker`:
  - `BYPASSRLS`, because it serves every tenant;
  - grants limited to the outbox, notifications and read access to the
    tables it needs, so a bug in the worker cannot alter attendance data.
- **Dispatch:**
  - Due rows are claimed with `FOR UPDATE SKIP LOCKED`, so several workers
    can run without double processing.
  - Each row is handled in a savepoint. A failing row gets `attempts + 1`,
    its error and exponential backoff (30 s to 1 h), and never blocks the
    rest of the batch.
- **At-least-once, made idempotent:** `notifications` has
  `UNIQUE (source_outbox_id, recipient_user_id)`. A redelivered message
  (after a crash before `processed_at` was set) does not notify anyone
  twice.
- **Delivery:**
  - Pending notifications are sent to the recipient's active devices that
    have a push token.
  - Without such a device, the notification is kept in-app (`SENT`; it is
    still listed by `GET /notifications`).
  - Failures back off and end as `FAILED` after `NOTIFICATION_MAX_ATTEMPTS`.
- **Push provider is pluggable:** `log` (the default, no network) or `expo`.
  Tests inject a fake sender.

## Consequences

- Notifications arrive within seconds, not instantly. That is acceptable for
  arrival and departure alerts.
- The outbox grows. Processed rows will be purged by a scheduled task with
  the data-retention work (Week 7).
- Absence and lateness alerts need schedules and run as scheduled jobs on
  the same worker (Week 7).
- Redis is now a runtime dependency of the worker. The API itself keeps
  working without Redis: login rate limiting fails open, and the outbox is
  plain PostgreSQL.

## How it is verified

`tests/test_worker_outbox.py` (real PostgreSQL, worker role):
- the event and its message are committed together;
- rejected or refused events produce no message;
- only guardians who opted in are notified;
- a redelivery does not duplicate a notification;
- a poison message is backed off without blocking others;
- delivery goes to the guardian's device, or stays in-app without a device;
- failures back off and then give up;
- guardians read and acknowledge their own notifications only.
