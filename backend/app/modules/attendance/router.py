import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import SchoolAdminDep, SessionDep, SettingsDep, TenantContext, TenantDep
from app.api.errors import error_responses
from app.modules.attendance.schemas import (
    AttendanceEventCreate,
    AttendanceEventOut,
    BatchItemOut,
    GuardedStudentOut,
    LocationOut,
    ManualEventCreate,
    OfflineBatch,
    OfflineBatchResult,
    ReviewDecision,
    SubjectStateOut,
    ValidationStatus,
)
from app.modules.attendance.service import AttendanceService
from app.modules.attendance.state_machine import allowed_events
from app.modules.institutions.models import InstitutionRole
from app.modules.institutions.service import InstitutionService, Subject, SubjectKind

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _out(event: dict[str, Any], *, with_location: bool) -> AttendanceEventOut:
    hidden = ("latitude", "longitude", "gps_accuracy_m")
    data = {k: v for k, v in event.items() if k not in hidden}
    location = None
    if with_location and event.get("latitude") is not None:
        location = LocationOut(
            latitude=event["latitude"],
            longitude=event["longitude"],
            accuracy_m=event["gps_accuracy_m"],
        )
    return AttendanceEventOut(**data, location=location)


def _request_id(request: Request) -> str | None:
    value: str | None = getattr(request.state, "request_id", None)
    return value


def _is_admin(tenant: TenantContext) -> bool:
    return tenant.has_any(InstitutionRole.SCHOOL_ADMIN)


@router.post(
    "/events",
    response_model=AttendanceEventOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Replay of an already recorded idempotency key"},
        **error_responses(401, 403, 404, 409, 422),
    },
)
async def record_event(
    body: AttendanceEventCreate,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> AttendanceEventOut:
    """Record the caller's own attendance action from the mobile app.

    - **201**: new event. Check `validation_status`: a `REJECTED` event is kept as
      evidence but does not change the attendance state.
    - **200**: the idempotency key was already used; the original event is returned.
    - **409**: the action is not allowed in the current state (e.g. CHECK_IN twice).
    - **422**: the request is too old or dated in the future.
    """
    result = await AttendanceService(session, settings).record_own(
        tenant.institution_id, tenant.user_id, body
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _out(result.event, with_location=False)


@router.post(
    "/manual-events",
    response_model=AttendanceEventOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
)
async def record_manual_event(
    body: ManualEventCreate,
    request: Request,
    response: Response,
    tenant: SchoolAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> AttendanceEventOut:
    """Auditable fallback when a person cannot use the app (no phone, no GPS signal).
    The reason is mandatory and the action is written to the audit log."""
    result = await AttendanceService(session, settings).record_manual(
        tenant.institution_id, tenant.user_id, body, request_id=_request_id(request)
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _out(result.event, with_location=True)


@router.get(
    "/events", response_model=list[AttendanceEventOut], responses=error_responses(401, 403)
)
async def list_events(
    tenant: TenantDep,
    session: SessionDep,
    settings: SettingsDep,
    student_id: Annotated[uuid.UUID | None, Query()] = None,
    staff_id: Annotated[uuid.UUID | None, Query()] = None,
    validation_status: Annotated[ValidationStatus | None, Query()] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AttendanceEventOut]:
    """School Admins see every event (with coordinates); everyone else sees only their
    own events, without coordinates."""
    service = AttendanceService(session, settings)
    admin = _is_admin(tenant)
    restrict_to = (
        None if admin else await service.visible_subjects(tenant.institution_id, tenant.user_id)
    )
    events = await service.list_events(
        tenant.institution_id,
        restrict_to=restrict_to,
        student_id=student_id,
        staff_id=staff_id,
        validation_status=validation_status,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return [_out(e, with_location=admin) for e in events]


@router.get("/state", response_model=list[SubjectStateOut], responses=error_responses(401, 403))
async def my_state(
    tenant: TenantDep, session: SessionDep, settings: SettingsDep
) -> list[SubjectStateOut]:
    """The caller's current attendance state and the actions allowed next."""
    service = AttendanceService(session, settings)
    subjects = await service.own_subjects(tenant.institution_id, tenant.user_id)
    states = await service.current_states(tenant.institution_id, subjects)
    return [
        SubjectStateOut(
            subject=subject.kind.value,
            subject_id=subject.id,
            state=state,
            allowed_events=allowed_events(state),
            last_event_id=last_event_id,
        )
        for subject, state, last_event_id in states
    ]


@router.post(
    "/events/{event_id}/review",
    response_model=AttendanceEventOut,
    responses=error_responses(401, 403, 404, 409),
)
async def review_event(
    event_id: uuid.UUID,
    body: ReviewDecision,
    request: Request,
    tenant: SchoolAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> AttendanceEventOut:
    """Validate or reject a flagged or pending event. Only the validation status
    changes; the event itself stays immutable and the decision is audited."""
    event = await AttendanceService(session, settings).review(
        tenant.institution_id, tenant.user_id, event_id, body, request_id=_request_id(request)
    )
    return _out(event, with_location=True)


@router.post(
    "/events/sync",
    response_model=OfflineBatchResult,
    responses=error_responses(401, 403, 422),
)
async def sync_offline_events(
    body: OfflineBatch, tenant: TenantDep, session: SessionDep, settings: SettingsDep
) -> OfflineBatchResult:
    """Upload events recorded while the phone had no connectivity (up to 50, any order).

    They are applied oldest first, each with the same checks as a live event except
    that the location rules are evaluated at the time the event happened. The answer
    has one result per event; retrying the batch is safe (idempotency keys).
    """
    results = await AttendanceService(session, settings).sync_offline(
        tenant.institution_id, tenant.user_id, body.events
    )
    return OfflineBatchResult(
        results=[
            BatchItemOut(
                idempotency_key=r.idempotency_key,
                outcome=r.outcome,
                status_code=r.status_code,
                event=None if r.event is None else _out(r.event, with_location=False),
                error=r.error,
            )
            for r in results
        ]
    )


@router.get(
    "/guardian/students",
    response_model=list[GuardedStudentOut],
    responses=error_responses(401, 403),
)
async def guardian_students(
    tenant: TenantDep, session: SessionDep, settings: SettingsDep
) -> list[GuardedStudentOut]:
    """For guardians: the students in their care and where each one is now."""
    students = await InstitutionService(session).guarded_students(
        tenant.institution_id, tenant.user_id
    )
    states = await AttendanceService(session, settings).current_states(
        tenant.institution_id, [Subject(SubjectKind.STUDENT, s.id) for s in students]
    )
    return [
        GuardedStudentOut(
            student_id=student.id,
            full_name=student.full_name,
            student_code=student.student_code,
            state=state,
            last_event_id=last_event_id,
        )
        for student, (_, state, last_event_id) in zip(students, states, strict=True)
    ]
