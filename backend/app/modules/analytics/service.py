"""Attendance analytics and CSV export."""

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.analytics.repository import AnalyticsRepository

MAX_RANGE_DAYS = 366


@dataclass(frozen=True, slots=True)
class AttendanceReport:
    start: date
    end: date
    timezone: str
    school_days: int
    students: list[dict[str, Any]]
    days: list[dict[str, Any]]

    @property
    def overall_rate(self) -> float | None:
        possible = self.school_days * len(self.students)
        if possible == 0:
            return None
        return round(sum(s["days_present"] for s in self.students) / possible, 4)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AnalyticsRepository(session)

    async def attendance(
        self, institution_id: uuid.UUID, start: date, end: date, campus_id: uuid.UUID | None
    ) -> AttendanceReport:
        if end < start:
            raise DomainError("'to' must not be before 'from'")
        if (end - start).days >= MAX_RANGE_DAYS:
            raise DomainError(f"The range may cover at most {MAX_RANGE_DAYS} days")
        tz = await self.repo.timezone(institution_id)
        students = await self.repo.per_student(institution_id, start, end, tz, campus_id)
        days = await self.repo.per_day(institution_id, start, end, tz, campus_id)
        school_days = len(days)
        for row in students:
            row["attendance_rate"] = (
                round(row["days_present"] / school_days, 4) if school_days else None
            )
        return AttendanceReport(start, end, tz, school_days, students, days)


_CSV_COLUMNS = [
    ("student_code", "student_code"),
    ("full_name", "full_name"),
    ("days_present", "days_present"),
    ("school_days", "school_days"),
    ("attendance_rate", "attendance_rate"),
    ("average_first_check_in", "average_first_check_in"),
    ("flagged_events", "flagged_events"),
    ("rejected_events", "rejected_events"),
    ("manual_events", "manual_events"),
]


def _safe_cell(value: object) -> str:
    """Neutralise spreadsheet formula injection (cells starting with = + - @ tab CR)."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def report_to_csv(report: AttendanceReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([header for header, _ in _CSV_COLUMNS])
    for row in report.students:
        writer.writerow([_safe_cell(row.get(key)) for _, key in _CSV_COLUMNS])
    return buffer.getvalue()
