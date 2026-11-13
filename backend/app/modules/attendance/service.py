"""Attendance engine (ADR-004).

Recording an event, in one transaction:
    1. idempotency: a known key returns the original event (no side effects)
    2. request age (own events): stale or future requests are refused, nothing stored
    3. device must be the caller's own active device (if given)
    4. lock the person's state row (serializes concurrent events for that person)
    5. re-check idempotency under the lock (a concurrent retry may have just committed)
    6. state machine: invalid transitions are refused (409), nothing stored
    7. location verdict (geolocation module) + movement plausibility
    8. insert the immutable event; advance the state unless the event was REJECTED
Rejected attempts are stored (state unchanged) because they are evidence for review.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.modules.attendance.repository import AttendanceRepository, NewEvent
from app.modules.attendance.schemas import (
    AttendanceEventCreate,
    ManualEventCreate,
    ReviewDecision,
)
from app.modules.attendance.state_machine import (
    AttendanceState,
    EventType,
    InvalidTransitionError,
    next_state,
)
from app.infrastructure.orm import set_current_institution
from app.modules.audit.service import AuditService
from app.modules.geolocation.rules import Verdict
from app.modules.geolocation.service import GeolocationService
from app.modules.identity.service import IdentityService
from app.modules.institutions.service import InstitutionService, Subject, SubjectKind

IMPLAUSIBLE_MOVEMENT = "IMPLAUSIBLE_MOVEMENT"


class RequestRejectedError(DomainError):
    status_code = 422


class TransitionConflictError(ConflictError):
    pass


@dataclass(frozen=True, slots=True)
class RecordResult:
    event: dict[str, Any]
    created: bool


@dataclass(frozen=True, slots=True)
class _Assessment:
    status: str
    reasons: list[str]
    geofence_id: uuid.UUID | None
    geofence_result: str
    distance_m: float | None


class AttendanceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = AttendanceRepository(session)
        self.institutions = InstitutionService(session)

    # ---- own events (mobile app) --------------------------------------------------
    async def record_own(
        self,
        institution_id: uuid.UUID,
        user_id: uuid.UUID,
        body: AttendanceEventCreate,
        *,
        now: datetime | None = None,
    ) -> RecordResult:
        now = now or datetime.now(UTC)
        existing = await self.repo.find_by_key(institution_id, user_id, body.idempotency_key)
        if existing is not None:
            return self._replay(existing, body.event_type, body.campus_id)

        self._check_request_age(body.occurred_at, now)
        subject = await self._own_subject(institution_id, user_id, body.as_subject)
        if body.device_id is not None:
            device = await IdentityService(self.session, self.settings).active_device(
                user_id, body.device_id
            )
            if device is None:
                raise PermissionDeniedError("Unknown or revoked device")

        async def assess(state_before: AttendanceState) -> _Assessment:
            del state_before
            return await self._assess_location(institution_id, subject, body, now)

        return await self._record(
            institution_id=institution_id,
            subject=subject,
            actor_user_id=user_id,
            event_type=body.event_type,
            campus_id=body.campus_id,
            idempotency_key=body.idempotency_key,
            occurred_at=body.occurred_at,
            source="MOBILE_GPS",
            device_id=body.device_id,
            location=(body.latitude, body.longitude, body.accuracy_m),
            location_captured_at=body.location_captured_at,
            is_mock=body.is_mock,
            manual_reason=None,
            assess=assess,
        )

    # ---- manual events (School Admin) -------------------------------------------------
    async def record_manual(
        self,
        institution_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        body: ManualEventCreate,
        *,
        request_id: str | None = None,
    ) -> RecordResult:
        existing = await self.repo.find_by_key(
            institution_id, actor_user_id, body.idempotency_key
        )
        if existing is not None:
            return self._replay(existing, body.event_type, body.campus_id)

        occurred_at = body.occurred_at or datetime.now(UTC)
        skew = timedelta(seconds=self.settings.clock_skew_tolerance_s)
        if occurred_at > datetime.now(UTC) + skew:
            raise RequestRejectedError("Manual events cannot be dated in the future")
        if body.student_id is not None:
            subject = Subject(SubjectKind.STUDENT, body.student_id)
        else:
            assert body.staff_id is not None  # schema guarantees exactly one  # noqa: S101
            subject = Subject(SubjectKind.STAFF, body.staff_id)
        if not await self.institutions.subject_exists(institution_id, subject):
            raise NotFoundError("Student or staff member not found")
        if not await self.institutions.campus_exists(institution_id, body.campus_id):
            raise NotFoundError("Campus not found")

        async def assess(state_before: AttendanceState) -> _Assessment:
            del state_before
            return _Assessment("VALIDATED", [], None, "NOT_EVALUATED", None)

        result = await self._record(
            institution_id=institution_id,
            subject=subject,
            actor_user_id=actor_user_id,
            event_type=body.event_type,
            campus_id=body.campus_id,
            idempotency_key=body.idempotency_key,
            occurred_at=occurred_at,
            source="MANUAL",
            device_id=None,
            location=None,
            location_captured_at=None,
            is_mock=None,
            manual_reason=body.reason,
            assess=assess,
            audit_request_id=request_id,
        )
        return result

    # ---- review -----------------------------------------------------------------------
    async def review(
        self,
        institution_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        event_id: uuid.UUID,
        decision: ReviewDecision,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        event = await self.repo.get_for_update(institution_id, event_id)
        if event is None:
            raise NotFoundError("Attendance event not found")
        if event["validation_status"] not in ("PENDING", "FLAGGED_FOR_REVIEW"):
            raise ConflictError(
                f"Only pending or flagged events can be reviewed "
                f"(this one is {event['validation_status']})"
            )
        updated = await self.repo.set_validation(institution_id, event_id, decision.decision)
        await AuditService(self.session).record(
            institution_id=institution_id,
            actor_user_id=reviewer_id,
            action="attendance_event.reviewed",
            entity_type="attendance_event",
            entity_id=event_id,
            changes={
                "validation_status": [event["validation_status"], decision.decision],
                "note": decision.note,
            },
            request_id=request_id,
        )
        await self.session.commit()
        return updated

    # ---- queries ----------------------------------------------------------------------
    async def own_subjects(
        self, institution_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Subject]:
        return await self.institutions.subjects_for_user(institution_id, user_id)

    async def list_events(
        self,
        institution_id: uuid.UUID,
        *,
        restrict_to: list[Subject] | None,
        student_id: uuid.UUID | None,
        staff_id: uuid.UUID | None,
        validation_status: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """restrict_to=None means every subject (School Admin); otherwise only those."""
        students: list[uuid.UUID] | None = None
        staff: list[uuid.UUID] | None = None
        if restrict_to is not None:
            students = [s.id for s in restrict_to if s.kind is SubjectKind.STUDENT]
            staff = [s.id for s in restrict_to if s.kind is SubjectKind.STAFF]
        if student_id is not None or staff_id is not None:
            wanted_students = [student_id] if student_id else []
            wanted_staff = [staff_id] if staff_id else []
            allowed_students, allowed_staff = set(students or []), set(staff or [])
            if restrict_to is not None and not (
                set(wanted_students) <= allowed_students and set(wanted_staff) <= allowed_staff
            ):
                raise PermissionDeniedError("You can only see your own attendance")
            students, staff = wanted_students, wanted_staff
        return await self.repo.list_events(
            institution_id,
            student_ids=students,
            staff_ids=staff,
            validation_status=validation_status,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    async def current_states(
        self, institution_id: uuid.UUID, subjects: list[Subject]
    ) -> list[tuple[Subject, AttendanceState, uuid.UUID | None]]:
        states = []
        for subject in subjects:
            locked = await self.repo.current_state(institution_id, subject)
            states.append((subject, locked.state, locked.last_event_id))
        return states

    # ---- internals ----------------------------------------------------------------------
    async def _record(
        self,
        *,
        institution_id: uuid.UUID,
        subject: Subject,
        actor_user_id: uuid.UUID,
        event_type: EventType,
        campus_id: uuid.UUID,
        idempotency_key: uuid.UUID,
        occurred_at: datetime,
        source: str,
        device_id: uuid.UUID | None,
        location: tuple[float, float, float] | None,
        location_captured_at: datetime | None,
        is_mock: bool | None,
        manual_reason: str | None,
        assess: Callable[[AttendanceState], Awaitable["_Assessment"]],
        audit_request_id: str | None = None,
    ) -> RecordResult:
        locked = await self.repo.lock_state(institution_id, subject)

        # A concurrent retry with the same key may have committed while we waited.
        existing = await self.repo.find_by_key(institution_id, actor_user_id, idempotency_key)
        if existing is not None:
            await self.session.rollback()
            return self._replay(existing, event_type, campus_id)

        try:
            target = next_state(locked.state, event_type)
        except InvalidTransitionError as exc:
            await self.session.rollback()
            raise TransitionConflictError(str(exc)) from exc

        assessment: _Assessment = await assess(locked.state)
        accepted = assessment.status != "REJECTED"
        state_after = target if accepted else locked.state

        lat, lng, accuracy = location if location is not None else (None, None, None)
        try:
            event = await self.repo.insert(
                NewEvent(
                    institution_id=institution_id,
                    campus_id=campus_id,
                    subject=subject,
                    actor_user_id=actor_user_id,
                    device_id=device_id,
                    event_type=event_type.value,
                    source=source,
                    state_before=locked.state.value,
                    state_after=state_after.value,
                    occurred_at=occurred_at,
                    latitude=lat,
                    longitude=lng,
                    accuracy_m=accuracy,
                    location_captured_at=location_captured_at,
                    is_mock=is_mock,
                    geofence_id=assessment.geofence_id,
                    geofence_result=assessment.geofence_result,
                    distance_m=assessment.distance_m,
                    idempotency_key=idempotency_key,
                    validation_status=assessment.status,
                    validation_reasons=assessment.reasons,
                    manual_reason=manual_reason,
                )
            )
        except IntegrityError:
            # Same key used concurrently for a different person (manual entries).
            await self.session.rollback()
            await set_current_institution(self.session, institution_id)  # rollback cleared it
            existing = await self.repo.find_by_key(institution_id, actor_user_id, idempotency_key)
            if existing is None:
                raise
            return self._replay(existing, event_type, campus_id)

        if accepted:
            await self.repo.update_state(institution_id, subject, target, event["id"])
        if source == "MANUAL":
            await AuditService(self.session).record(
                institution_id=institution_id,
                actor_user_id=actor_user_id,
                action="attendance_event.manual_created",
                entity_type="attendance_event",
                entity_id=event["id"],
                changes={
                    "event_type": event_type.value,
                    "reason": manual_reason,
                    "subject": {subject.kind.value: str(subject.id)},
                },
                request_id=audit_request_id,
            )
        await self.session.commit()
        return RecordResult(event=event, created=True)

    async def _assess_location(
        self,
        institution_id: uuid.UUID,
        subject: Subject,
        body: AttendanceEventCreate,
        now: datetime,
    ) -> _Assessment:
        verdict = await GeolocationService(self.session, self.settings).evaluate(
            institution_id,
            campus_id=body.campus_id,
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_m=body.accuracy_m,
            captured_at=body.location_captured_at,
            is_mock=body.is_mock,
            now=now,
        )
        reasons = [r.value for r in verdict.reasons]
        status = verdict.verdict.value

        previous = await self.repo.previous_fix(
            institution_id,
            subject,
            body.latitude,
            body.longitude,
            since=now - timedelta(hours=self.settings.movement_window_h),
        )
        if previous is not None:
            elapsed = max(abs((body.occurred_at - previous.occurred_at).total_seconds()), 1.0)
            if previous.distance_m / elapsed > self.settings.max_plausible_speed_m_s:
                reasons.append(IMPLAUSIBLE_MOVEMENT)
                if verdict.verdict is Verdict.VALIDATED:
                    status = Verdict.FLAGGED_FOR_REVIEW.value

        return _Assessment(
            status=status,
            reasons=reasons,
            geofence_id=verdict.geofence_id,
            geofence_result=verdict.geofence_result.value,
            distance_m=verdict.distance_m,
        )

    async def _own_subject(
        self, institution_id: uuid.UUID, user_id: uuid.UUID, as_subject: str | None
    ) -> Subject:
        subjects = await self.institutions.subjects_for_user(institution_id, user_id)
        if as_subject is not None:
            subjects = [s for s in subjects if s.kind.value == as_subject]
        if not subjects:
            raise PermissionDeniedError(
                "Your account is not linked to a student or staff record in this institution"
            )
        if len(subjects) > 1:
            raise DomainError("Your account is both a student and staff: send 'as_subject'")
        return subjects[0]

    def _check_request_age(self, occurred_at: datetime, now: datetime) -> None:
        age = (now - occurred_at).total_seconds()
        if age > self.settings.request_max_age_s:
            raise RequestRejectedError(
                f"Request is too old ({age:.0f} s > {self.settings.request_max_age_s} s); "
                "capture a fresh location and try again"
            )
        if age < -self.settings.clock_skew_tolerance_s:
            raise RequestRejectedError(
                "Request timestamp is in the future; check the device clock"
            )

    @staticmethod
    def _replay(
        existing: dict[str, Any], event_type: EventType, campus_id: uuid.UUID
    ) -> RecordResult:
        if existing["event_type"] != event_type.value or existing["campus_id"] != campus_id:
            raise ConflictError("This idempotency key was already used for a different event")
        return RecordResult(event=existing, created=False)
