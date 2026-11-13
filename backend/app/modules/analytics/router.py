import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.api.deps import SessionDep, TenantDep
from app.api.errors import error_responses
from app.core.errors import DomainError, PermissionDeniedError
from app.modules.analytics.service import (
    AnalyticsService,
    AttendanceReport,
    PersonReport,
    StaffReport,
    report_to_csv,
)
from app.modules.institutions.models import InstitutionRole

router = APIRouter(prefix="/analytics", tags=["analytics"])


class StudentAttendance(BaseModel):
    student_id: uuid.UUID
    student_code: str
    full_name: str
    days_present: int
    school_days: int
    attendance_rate: float | None
    average_first_check_in: str | None
    flagged_events: int
    rejected_events: int
    manual_events: int


class DayAttendance(BaseModel):
    day: date
    students_present: int


class AttendanceAnalytics(BaseModel):
    start: date
    end: date
    timezone: str
    school_days: int
    overall_rate: float | None
    students: list[StudentAttendance]
    days: list[DayAttendance]


class StaffAttendance(BaseModel):
    staff_id: uuid.UUID
    employee_code: str
    staff_type: str
    full_name: str
    days_present: int
    school_days: int
    attendance_rate: float | None
    average_first_check_in: str | None
    average_last_check_out: str | None
    flagged_events: int
    rejected_events: int
    manual_events: int


class StaffDay(BaseModel):
    day: date
    present: int


class StaffAnalytics(BaseModel):
    start: date
    end: date
    timezone: str
    school_days: int
    overall_rate: float | None
    staff: list[StaffAttendance]
    days: list[StaffDay]


class PersonDay(BaseModel):
    day: date
    present: bool
    first_check_in: str | None
    last_check_out: str | None
    flagged_events: int
    rejected_events: int
    events: int


class PersonAnalytics(BaseModel):
    kind: str
    full_name: str
    code: str
    start: date
    end: date
    timezone: str
    school_days: int
    days_present: int
    attendance_rate: float | None
    days: list[PersonDay]


Start = Annotated[date, Query(alias="from")]
End = Annotated[date, Query(alias="to")]
CampusFilter = Annotated[uuid.UUID | None, Query()]


async def _report(
    tenant: TenantDep, session: SessionDep, start: date, end: date, campus_id: uuid.UUID | None
) -> AttendanceReport:
    if not tenant.has_any(InstitutionRole.SCHOOL_ADMIN, InstitutionRole.TEACHER):
        raise PermissionDeniedError("Only school admins and teachers can see analytics")
    return await AnalyticsService(session).attendance(tenant.institution_id, start, end, campus_id)


def _as_dict(report: AttendanceReport) -> dict[str, Any]:
    return {
        "start": report.start,
        "end": report.end,
        "timezone": report.timezone,
        "school_days": report.school_days,
        "overall_rate": report.overall_rate,
        "students": report.students,
        "days": report.days,
    }


@router.get(
    "/attendance", response_model=AttendanceAnalytics, responses=error_responses(400, 401, 403)
)
async def attendance_analytics(
    tenant: TenantDep, session: SessionDep, start: Start, end: End, campus_id: CampusFilter = None
) -> AttendanceAnalytics:
    """Attendance per student and per school day (Mon-Fri) between `from` and `to`
    (inclusive, institution timezone). Only accepted check-ins count as presence."""
    report = await _report(tenant, session, start, end, campus_id)
    return AttendanceAnalytics.model_validate(_as_dict(report))


@router.get(
    "/attendance.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, **error_responses(400, 401, 403)},
)
async def attendance_csv(
    tenant: TenantDep, session: SessionDep, start: Start, end: End, campus_id: CampusFilter = None
) -> Response:
    """The same report as CSV (UTF-8 with BOM so spreadsheet apps detect the encoding)."""
    report = await _report(tenant, session, start, end, campus_id)
    filename = f"attendance_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content="﻿" + report_to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/staff", response_model=StaffAnalytics, responses=error_responses(400, 401, 403))
async def staff_analytics(
    tenant: TenantDep, session: SessionDep, start: Start, end: End, campus_id: CampusFilter = None
) -> StaffAnalytics:
    """Attendance of teachers and other staff (School Admins only: it is employment data)."""
    if not tenant.has_any(InstitutionRole.SCHOOL_ADMIN):
        raise PermissionDeniedError("Only school admins can see staff attendance")
    report: StaffReport = await AnalyticsService(session).staff_attendance(
        tenant.institution_id, start, end, campus_id
    )
    return StaffAnalytics(
        start=report.start,
        end=report.end,
        timezone=report.timezone,
        school_days=report.school_days,
        overall_rate=report.overall_rate,
        staff=[StaffAttendance(**row) for row in report.staff],
        days=[StaffDay(**row) for row in report.days],
    )


@router.get(
    "/person", response_model=PersonAnalytics, responses=error_responses(400, 401, 403, 404)
)
async def person_analytics(
    tenant: TenantDep,
    session: SessionDep,
    start: Start,
    end: End,
    student_id: Annotated[uuid.UUID | None, Query()] = None,
    staff_id: Annotated[uuid.UUID | None, Query()] = None,
    campus_id: CampusFilter = None,
) -> PersonAnalytics:
    """One person's school days: present or absent, first check-in and last check-out.

    Students: School Admins and teachers. Staff: School Admins only."""
    if (student_id is None) == (staff_id is None):
        raise DomainError("Give exactly one of student_id or staff_id")
    allowed = (
        (InstitutionRole.SCHOOL_ADMIN, InstitutionRole.TEACHER)
        if student_id is not None
        else (InstitutionRole.SCHOOL_ADMIN,)
    )
    if not tenant.has_any(*allowed):
        raise PermissionDeniedError("You cannot see this person's attendance")
    if student_id is not None:
        kind, subject = "student", student_id
    elif staff_id is not None:
        kind, subject = "staff", staff_id
    else:  # pragma: no cover - rejected above
        raise DomainError("Give exactly one of student_id or staff_id")
    report: PersonReport = await AnalyticsService(session).person(
        tenant.institution_id, kind, subject, start, end, campus_id
    )
    return PersonAnalytics(
        kind=report.kind,
        full_name=report.full_name,
        code=report.code,
        start=report.start,
        end=report.end,
        timezone=report.timezone,
        school_days=report.school_days,
        days_present=report.days_present,
        attendance_rate=report.attendance_rate,
        days=[PersonDay(**row) for row in report.days],
    )
