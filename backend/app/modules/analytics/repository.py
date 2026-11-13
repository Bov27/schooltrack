"""Attendance aggregates computed from the immutable event log.

A student is "present" on a school day when they have an accepted CHECK_IN (validated,
or flagged and not rejected by a reviewer) on that local date. Days are calendar days in
the institution's timezone; school days are Monday to Friday (no holiday calendar yet).
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ACCEPTED = "('VALIDATED', 'FLAGGED_FOR_REVIEW')"

_PER_STUDENT = f"""
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
),
check_ins AS (
    SELECT e.student_id,
           (e.occurred_at AT TIME ZONE :tz)::date AS day,
           min((e.occurred_at AT TIME ZONE :tz)::time) AS first_in
    FROM attendance_events e
    WHERE e.institution_id = :inst AND e.student_id IS NOT NULL
      AND e.event_type = 'CHECK_IN' AND e.validation_status IN {_ACCEPTED}
      AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
      AND e.occurred_at >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
      AND e.occurred_at < ((CAST(:end AS date) + 1)::timestamp AT TIME ZONE :tz)
    GROUP BY 1, 2
),
review AS (
    SELECT e.student_id,
           count(*) FILTER (WHERE e.validation_status = 'FLAGGED_FOR_REVIEW') AS flagged,
           count(*) FILTER (WHERE e.validation_status = 'REJECTED') AS rejected,
           count(*) FILTER (WHERE e.source = 'MANUAL') AS manual
    FROM attendance_events e
    WHERE e.institution_id = :inst AND e.student_id IS NOT NULL
      AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
      AND e.occurred_at >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
      AND e.occurred_at < ((CAST(:end AS date) + 1)::timestamp AT TIME ZONE :tz)
    GROUP BY 1
)
SELECT s.id AS student_id, s.student_code, s.full_name,
       count(c.day) AS days_present,
       (SELECT count(*) FROM days) AS school_days,
       to_char(avg(c.first_in - time '00:00'), 'HH24:MI') AS average_first_check_in,
       coalesce(max(r.flagged), 0) AS flagged_events,
       coalesce(max(r.rejected), 0) AS rejected_events,
       coalesce(max(r.manual), 0) AS manual_events
FROM students s
LEFT JOIN check_ins c ON c.student_id = s.id AND c.day IN (SELECT day FROM days)
LEFT JOIN review r ON r.student_id = s.id
WHERE s.institution_id = :inst AND s.is_active
GROUP BY s.id, s.student_code, s.full_name
ORDER BY s.full_name
"""

_PER_DAY = f"""
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
)
SELECT d.day,
       count(DISTINCT e.student_id) AS students_present
FROM days d
LEFT JOIN attendance_events e
  ON e.institution_id = :inst AND e.student_id IS NOT NULL
 AND e.event_type = 'CHECK_IN' AND e.validation_status IN {_ACCEPTED}
 AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
 AND (e.occurred_at AT TIME ZONE :tz)::date = d.day
GROUP BY d.day
ORDER BY d.day
"""

_PER_STAFF = f"""
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
),
daily AS (
    SELECT e.staff_id,
           (e.occurred_at AT TIME ZONE :tz)::date AS day,
           min((e.occurred_at AT TIME ZONE :tz)::time)
               FILTER (WHERE e.event_type = 'CHECK_IN') AS first_in,
           max((e.occurred_at AT TIME ZONE :tz)::time)
               FILTER (WHERE e.event_type = 'CHECK_OUT') AS last_out
    FROM attendance_events e
    WHERE e.institution_id = :inst AND e.staff_id IS NOT NULL
      AND e.event_type IN ('CHECK_IN', 'CHECK_OUT') AND e.validation_status IN {_ACCEPTED}
      AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
      AND e.occurred_at >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
      AND e.occurred_at < ((CAST(:end AS date) + 1)::timestamp AT TIME ZONE :tz)
    GROUP BY 1, 2
),
review AS (
    SELECT e.staff_id,
           count(*) FILTER (WHERE e.validation_status = 'FLAGGED_FOR_REVIEW') AS flagged,
           count(*) FILTER (WHERE e.validation_status = 'REJECTED') AS rejected,
           count(*) FILTER (WHERE e.source = 'MANUAL') AS manual
    FROM attendance_events e
    WHERE e.institution_id = :inst AND e.staff_id IS NOT NULL
      AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
      AND e.occurred_at >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
      AND e.occurred_at < ((CAST(:end AS date) + 1)::timestamp AT TIME ZONE :tz)
    GROUP BY 1
)
SELECT st.id AS staff_id, st.employee_code, st.staff_type::text AS staff_type, u.full_name,
       count(dl.day) FILTER (WHERE dl.first_in IS NOT NULL) AS days_present,
       (SELECT count(*) FROM days) AS school_days,
       to_char(avg(dl.first_in - time '00:00'), 'HH24:MI') AS average_first_check_in,
       to_char(avg(dl.last_out - time '00:00'), 'HH24:MI') AS average_last_check_out,
       coalesce(max(r.flagged), 0) AS flagged_events,
       coalesce(max(r.rejected), 0) AS rejected_events,
       coalesce(max(r.manual), 0) AS manual_events
FROM staff st
JOIN users u ON u.id = st.user_id
LEFT JOIN daily dl ON dl.staff_id = st.id AND dl.day IN (SELECT day FROM days)
LEFT JOIN review r ON r.staff_id = st.id
WHERE st.institution_id = :inst AND st.is_active
GROUP BY st.id, st.employee_code, st.staff_type, u.full_name
ORDER BY u.full_name
"""

_STAFF_PER_DAY = f"""
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
)
SELECT d.day,
       count(DISTINCT e.staff_id) AS present
FROM days d
LEFT JOIN attendance_events e
  ON e.institution_id = :inst AND e.staff_id IS NOT NULL
 AND e.event_type = 'CHECK_IN' AND e.validation_status IN {_ACCEPTED}
 AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
 AND (e.occurred_at AT TIME ZONE :tz)::date = d.day
GROUP BY d.day
ORDER BY d.day
"""

# {column} is student_id or staff_id, from a fixed mapping (never from input).
_PERSON_DAYS = f"""
WITH days AS (
    SELECT d::date AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
),
ev AS (
    SELECT (e.occurred_at AT TIME ZONE :tz)::date AS day,
           (e.occurred_at AT TIME ZONE :tz)::time AS at,
           e.event_type, e.validation_status
    FROM attendance_events e
    WHERE e.institution_id = :inst AND e.{{column}} = :subject
      AND (CAST(:campus AS uuid) IS NULL OR e.campus_id = :campus)
      AND e.occurred_at >= (CAST(:start AS date)::timestamp AT TIME ZONE :tz)
      AND e.occurred_at < ((CAST(:end AS date) + 1)::timestamp AT TIME ZONE :tz)
)
SELECT d.day,
       coalesce(bool_or(ev.event_type = 'CHECK_IN' AND ev.validation_status IN {_ACCEPTED}), false)
           AS present,
       to_char(min(ev.at) FILTER (WHERE ev.event_type = 'CHECK_IN'
                                    AND ev.validation_status IN {_ACCEPTED}), 'HH24:MI')
           AS first_check_in,
       to_char(max(ev.at) FILTER (WHERE ev.event_type = 'CHECK_OUT'
                                    AND ev.validation_status IN {_ACCEPTED}), 'HH24:MI')
           AS last_check_out,
       count(ev.day) FILTER (WHERE ev.validation_status = 'FLAGGED_FOR_REVIEW') AS flagged_events,
       count(ev.day) FILTER (WHERE ev.validation_status = 'REJECTED') AS rejected_events,
       count(ev.day) AS events
FROM days d
LEFT JOIN ev ON ev.day = d.day
GROUP BY d.day
ORDER BY d.day
"""

_PERSON = {
    "student": "SELECT full_name, student_code AS code FROM students "
    "WHERE institution_id = :inst AND id = :subject",
    "staff": "SELECT u.full_name, st.employee_code AS code FROM staff st "
    "JOIN users u ON u.id = st.user_id WHERE st.institution_id = :inst AND st.id = :subject",
}
_PERSON_COLUMN = {"student": "student_id", "staff": "staff_id"}


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def timezone(self, institution_id: uuid.UUID) -> str:
        tz = await self.session.scalar(
            text("SELECT timezone FROM institutions WHERE id = :inst"), {"inst": institution_id}
        )
        return str(tz or "America/Bogota")

    async def per_student(
        self, institution_id: uuid.UUID, start: date, end: date, tz: str, campus: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            text(_PER_STUDENT),
            {"inst": institution_id, "start": start, "end": end, "tz": tz, "campus": campus},
        )
        return [dict(r._mapping) for r in rows.all()]

    async def per_day(
        self, institution_id: uuid.UUID, start: date, end: date, tz: str, campus: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            text(_PER_DAY),
            {"inst": institution_id, "start": start, "end": end, "tz": tz, "campus": campus},
        )
        return [dict(r._mapping) for r in rows.all()]

    async def per_staff(
        self, institution_id: uuid.UUID, start: date, end: date, tz: str, campus: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            text(_PER_STAFF),
            {"inst": institution_id, "start": start, "end": end, "tz": tz, "campus": campus},
        )
        return [dict(r._mapping) for r in rows.all()]

    async def staff_per_day(
        self, institution_id: uuid.UUID, start: date, end: date, tz: str, campus: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            text(_STAFF_PER_DAY),
            {"inst": institution_id, "start": start, "end": end, "tz": tz, "campus": campus},
        )
        return [dict(r._mapping) for r in rows.all()]

    async def person(
        self, institution_id: uuid.UUID, kind: str, subject: uuid.UUID
    ) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                text(_PERSON[kind]), {"inst": institution_id, "subject": subject}
            )
        ).one_or_none()
        return None if row is None else dict(row._mapping)

    async def person_days(
        self,
        institution_id: uuid.UUID,
        kind: str,
        subject: uuid.UUID,
        start: date,
        end: date,
        tz: str,
        campus: uuid.UUID | None,
    ) -> list[dict[str, Any]]:
        sql = _PERSON_DAYS.format(column=_PERSON_COLUMN[kind])
        rows = await self.session.execute(
            text(sql),
            {
                "inst": institution_id,
                "subject": subject,
                "start": start,
                "end": end,
                "tz": tz,
                "campus": campus,
            },
        )
        return [dict(r._mapping) for r in rows.all()]
