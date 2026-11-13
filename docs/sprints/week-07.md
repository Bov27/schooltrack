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
