import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.api.deps import SessionDep, TenantDep
from app.api.errors import error_responses
from app.core.errors import PermissionDeniedError
from app.modules.analytics.service import AnalyticsService, AttendanceReport, report_to_csv
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
