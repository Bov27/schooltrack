# Week 7: Analytics, accounts and hardening

## 7a: Accounts and analytics

Gaps found while testing on a real phone (Week 6), plus the analytics module.

### Delivered

- [x] `POST /accounts`: a School Admin creates an app account with an
      initial password. The account becomes an active member with no role;
      the role comes when it is linked to a student, staff member or
      guardian. The creation is audited.
- [x] `POST /users/me/password`: change your password. Every session is
      signed out (all refresh tokens revoked). A wrong current password
      returns `400`, not `401`, so it does not look like an expired session.
- [x] `PATCH /students/{id}`:
  - rename, activate or deactivate;
  - **link an existing account** (adds the STUDENT role) or unlink it;
  - an account can belong to only one student (`409`);
  - every change is audited with before and after values.
- [x] `GET /analytics/attendance?from&to[&campus_id]` (School Admin,
      Teacher):
  - per student: days present, attendance rate, average first check-in,
    flagged, rejected and manual events;
  - per school day: students present;
  - overall rate.
- [x] `GET /analytics/attendance.csv`:
  - UTF-8 with a BOM, for Excel;
  - `Content-Disposition` with the date range;
  - cells starting with `= + - @` are neutralised (formula injection).
- [x] Dashboard:
  - Analytics page: date range, campus filter, per-day bars, per-student
    table with colour-coded rates, CSV download;
  - account creation;
  - link, unlink and activate/deactivate buttons per student.

### Definitions (documented in the API and the dashboard)

- **School day:** Monday to Friday, in the institution's timezone. There is
  no holiday calendar yet.
- **Present:** at least one accepted CHECK_IN that day (validated, or
  flagged and not rejected). Rejected attempts never count.
- **Time zones:** a check-in at 23:30 on Friday, Bogotá time, counts for
  Friday, not for Saturday in UTC. The tests check this.

## 7b: Retention, hardening and load testing

### Delivered

- [x] **Location retention (privacy):**
  - precise coordinates are purged after `LOCATION_RETENTION_DAYS` (default
    90);
  - the geofence result, the distance and the validation status are kept,
    so attendance history and reports are unaffected;
  - the job runs hourly on the worker, in bounded batches with `SKIP LOCKED`.
- [x] **Immutability still holds, enforced by the database.** Migration
      `0007` extends the event trigger with one exception: only the
      `schooltrack_worker` role may clear **all** location fields at once,
      and only once.
  - The API role and even the owner/superuser are refused, and the tests
    check this.
  - The worker has column-level `UPDATE` grants on exactly those four
    columns, and nothing else on events.
- [x] Processed outbox rows are deleted after `OUTBOX_RETENTION_DAYS`
      (default 30).
- [x] **API hardening:**
  - `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`;
  - `Cache-Control: no-store`, because responses carry personal data;
  - a strict CSP on JSON responses;
  - HSTS in staging and production;
  - request bodies over 1 MiB refused with `413` before they are read;
  - interactive docs off by default in staging and production.
- [x] **Load test** (`backend/loadtest/attendance_load.py`, run in CI
      against uvicorn with 2 workers). It simulates the school-opening
      burst:
  - 300 students check in at concurrency 50;
  - every phone retries once;
  - everyone checks out.

  It verifies correctness in the database (exactly one CHECK_IN and one
  CHECK_OUT per student, every state back to OUTSIDE, no 5xx) and reports
  p50, p95, p99 and throughput against NFR-PERF-1 in the job summary.

### Load test results (GitHub Actions runner, API with 2 uvicorn workers)

| Run | Phase | Throughput | p50 | p95 | p99 | Correctness |
|---|---|---|---|---|---|---|
| Open loop, 50 req/s (NFR) | check-in burst | 50.0 req/s | 16 ms | **63 ms** | 211 ms | 300 × 201 |
| | retries | 50.1 req/s | 9 ms | 11 ms | 13 ms | 300 × 200 (replays) |
| | check-out burst | 50.0 req/s | 15 ms | 19 ms | 24 ms | 300 × 201 |
| Closed loop, 50 in flight (saturation) | check-in burst | 103.8 req/s | 411 ms | 895 ms | 947 ms | 300 × 201 |
| | check-out burst | 90.8 req/s | 373 ms | 1348 ms | 1803 ms | 300 × 201 |

**NFR-PERF-1 (p95 < 300 ms at 50 req/s) is met:** the worst p95 was 63 ms.

**A lesson from the first attempt:** the first version only had the closed-loop
run, which reported "NFR not met" (p95 of about 800 ms). Keeping 50 requests in
flight offers 100–150 req/s, two to three times the target arrival rate, so it
measures saturation and not the NFR. The script now has an open-loop mode
(`--rate`), and CI runs both modes.

**Where the time goes at saturation:** the per-person row lock is not
contended (every request is for a different student). The cost is the
PostGIS geofence check, the movement check, and the 10-connection pool per
worker. The next levers, if a larger school needs them, are more API workers,
a larger pool, and caching the campus geofences per request.
