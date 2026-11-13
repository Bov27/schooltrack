"""SQL for attendance events and per-person state.

Events carry a geography point, so they are read and written with explicit SQL. The
subject column (student_id or staff_id) is chosen from a fixed mapping, never from input.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.state_machine import AttendanceState
from app.modules.institutions.service import Subject, SubjectKind

_SUBJECT_COLUMN = {SubjectKind.STUDENT: "student_id", SubjectKind.STAFF: "staff_id"}

EVENT_COLUMNS = (
    "id, event_type::text AS event_type, source::text AS source, campus_id, student_id, "
    "staff_id, actor_user_id, state_before::text AS state_before, "
    "state_after::text AS state_after, validation_status::text AS validation_status, "
    "validation_reasons, geofence_result::text AS geofence_result, distance_to_geofence_m, "
    "occurred_at, received_at, gps_accuracy_m, "
    "ST_Y(location::geometry) AS latitude, ST_X(location::geometry) AS longitude"
)
_POINT = (
    "ST_SetSRID(ST_MakePoint(CAST(:lng AS float8), CAST(:lat AS float8)), 4326)::geography"
)


@dataclass(frozen=True, slots=True)
class LockedState:
    state: AttendanceState
    last_event_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class PreviousFix:
    occurred_at: datetime
    distance_m: float


@dataclass(frozen=True, slots=True)
class NewEvent:
    institution_id: uuid.UUID
    campus_id: uuid.UUID
    subject: Subject
    actor_user_id: uuid.UUID
    device_id: uuid.UUID | None
    event_type: str
    source: str
    state_before: str
    state_after: str
    occurred_at: datetime
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    location_captured_at: datetime | None
    is_mock: bool | None
    geofence_id: uuid.UUID | None
    geofence_result: str
    distance_m: float | None
    idempotency_key: uuid.UUID
    validation_status: str
    validation_reasons: list[str]
    manual_reason: str | None


class AttendanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_key(
        self, institution_id: uuid.UUID, actor_user_id: uuid.UUID, key: uuid.UUID
    ) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                text(
                    f"SELECT {EVENT_COLUMNS} FROM attendance_events "
                    "WHERE institution_id = :inst AND actor_user_id = :actor "
                    "AND idempotency_key = :key"
                ),
                {"inst": institution_id, "actor": actor_user_id, "key": key},
            )
        ).one_or_none()
        return None if row is None else dict(row._mapping)

    async def lock_state(self, institution_id: uuid.UUID, subject: Subject) -> LockedState:
        """Create the person's state row if needed, then lock it until commit. Concurrent
        events for the same person wait here, so transitions are checked one at a time."""
        column = _SUBJECT_COLUMN[subject.kind]
        params = {"inst": institution_id, "subject": subject.id}
        await self.session.execute(
            text(
                f"INSERT INTO attendance_subject_states (institution_id, {column}) "
                "VALUES (:inst, :subject) ON CONFLICT DO NOTHING"
            ),
            params,
        )
        row = (
            await self.session.execute(
                text(
                    "SELECT current_state::text AS state, last_event_id "
                    "FROM attendance_subject_states "
                    f"WHERE institution_id = :inst AND {column} = :subject FOR UPDATE"
                ),
                params,
            )
        ).one()
        return LockedState(AttendanceState(row.state), row.last_event_id)

    async def update_state(
        self,
        institution_id: uuid.UUID,
        subject: Subject,
        state: AttendanceState,
        last_event_id: uuid.UUID,
    ) -> None:
        column = _SUBJECT_COLUMN[subject.kind]
        await self.session.execute(
            text(
                "UPDATE attendance_subject_states "
                "SET current_state = CAST(:state AS attendance_state), "
                "last_event_id = :event, updated_at = now() "
                f"WHERE institution_id = :inst AND {column} = :subject"
            ),
            {
                "inst": institution_id,
                "subject": subject.id,
                "state": state.value,
                "event": last_event_id,
            },
        )

    async def previous_fix(
        self,
        institution_id: uuid.UUID,
        subject: Subject,
        lat: float,
        lng: float,
        since: datetime,
    ) -> PreviousFix | None:
        """The person's latest located, non-rejected event since `since`, with its
        distance in metres to the new point."""
        column = _SUBJECT_COLUMN[subject.kind]
        row = (
            await self.session.execute(
                text(
                    f"SELECT occurred_at, ST_Distance(location, {_POINT}) AS distance_m "
                    "FROM attendance_events "
                    f"WHERE institution_id = :inst AND {column} = :subject "
                    "AND location IS NOT NULL AND validation_status <> 'REJECTED' "
                    "AND occurred_at >= :since "
                    "ORDER BY occurred_at DESC LIMIT 1"
                ),
                {
                    "inst": institution_id,
                    "subject": subject.id,
                    "lat": lat,
                    "lng": lng,
                    "since": since,
                },
            )
        ).one_or_none()
        if row is None:
            return None
        return PreviousFix(row.occurred_at, float(row.distance_m))

    async def insert(self, event: NewEvent) -> dict[str, Any]:
        column = _SUBJECT_COLUMN[event.subject.kind]
        row = (
            await self.session.execute(
                text(
                    "INSERT INTO attendance_events (institution_id, campus_id, "
                    f"{column}, actor_user_id, device_id, event_type, source, state_before, "
                    "state_after, occurred_at, location, gps_accuracy_m, location_captured_at, "
                    "is_mock_location, geofence_id, geofence_result, distance_to_geofence_m, "
                    "idempotency_key, validation_status, validation_reasons, manual_reason) "
                    "VALUES (:inst, :campus, :subject, :actor, :device, "
                    "CAST(:etype AS attendance_event_type), CAST(:source AS attendance_source), "
                    "CAST(:before AS attendance_state), CAST(:after AS attendance_state), "
                    f":occurred, {_POINT}, :accuracy, :captured, :mock, :geofence, "
                    "CAST(:gresult AS geofence_result), :distance, :key, "
                    "CAST(:vstatus AS validation_status), CAST(:reasons AS jsonb), :manual) "
                    f"RETURNING {EVENT_COLUMNS}"
                ),
                {
                    "inst": event.institution_id,
                    "campus": event.campus_id,
                    "subject": event.subject.id,
                    "actor": event.actor_user_id,
                    "device": event.device_id,
                    "etype": event.event_type,
                    "source": event.source,
                    "before": event.state_before,
                    "after": event.state_after,
                    "occurred": event.occurred_at,
                    "lat": event.latitude,
                    "lng": event.longitude,
                    "accuracy": event.accuracy_m,
                    "captured": event.location_captured_at,
                    "mock": event.is_mock,
                    "geofence": event.geofence_id,
                    "gresult": event.geofence_result,
                    "distance": event.distance_m,
                    "key": event.idempotency_key,
                    "vstatus": event.validation_status,
                    "reasons": json.dumps(event.validation_reasons),
                    "manual": event.manual_reason,
                },
            )
        ).one()
        return dict(row._mapping)

    async def get_for_update(
        self, institution_id: uuid.UUID, event_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                text(
                    f"SELECT {EVENT_COLUMNS} FROM attendance_events "
                    "WHERE institution_id = :inst AND id = :id FOR UPDATE"
                ),
                {"inst": institution_id, "id": event_id},
            )
        ).one_or_none()
        return None if row is None else dict(row._mapping)

    async def set_validation(
        self, institution_id: uuid.UUID, event_id: uuid.UUID, status: str
    ) -> dict[str, Any]:
        row = (
            await self.session.execute(
                text(
                    "UPDATE attendance_events "
                    "SET validation_status = CAST(:status AS validation_status) "
                    f"WHERE institution_id = :inst AND id = :id RETURNING {EVENT_COLUMNS}"
                ),
                {"inst": institution_id, "id": event_id, "status": status},
            )
        ).one()
        return dict(row._mapping)

    async def list_events(
        self,
        institution_id: uuid.UUID,
        *,
        student_ids: list[uuid.UUID] | None,
        staff_ids: list[uuid.UUID] | None,
        validation_status: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """student_ids/staff_ids: None = no restriction; [] = match nothing for that kind."""
        conditions = ["institution_id = :inst"]
        params: dict[str, Any] = {"inst": institution_id, "limit": limit, "offset": offset}
        if student_ids is not None or staff_ids is not None:
            params["students"] = student_ids or []
            params["staff"] = staff_ids or []
            conditions.append(
                "(student_id = ANY(CAST(:students AS uuid[])) "
                "OR staff_id = ANY(CAST(:staff AS uuid[])))"
            )
        if validation_status is not None:
            conditions.append("validation_status = CAST(:vstatus AS validation_status)")
            params["vstatus"] = validation_status
        if since is not None:
            conditions.append("occurred_at >= :since")
            params["since"] = since
        if until is not None:
            conditions.append("occurred_at < :until")
            params["until"] = until
        rows = (
            await self.session.execute(
                text(
                    f"SELECT {EVENT_COLUMNS} FROM attendance_events "
                    f"WHERE {' AND '.join(conditions)} "
                    "ORDER BY occurred_at DESC, id LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).all()
        return [dict(r._mapping) for r in rows]

    async def event_occurred_at(
        self, institution_id: uuid.UUID, event_id: uuid.UUID
    ) -> datetime | None:
        value: datetime | None = await self.session.scalar(
            text(
                "SELECT occurred_at FROM attendance_events "
                "WHERE institution_id = :inst AND id = :id"
            ),
            {"inst": institution_id, "id": event_id},
        )
        return value

    async def current_state(
        self, institution_id: uuid.UUID, subject: Subject
    ) -> LockedState:
        column = _SUBJECT_COLUMN[subject.kind]
        row = (
            await self.session.execute(
                text(
                    "SELECT current_state::text AS state, last_event_id "
                    "FROM attendance_subject_states "
                    f"WHERE institution_id = :inst AND {column} = :subject"
                ),
                {"inst": institution_id, "subject": subject.id},
            )
        ).one_or_none()
        if row is None:
            return LockedState(AttendanceState.OUTSIDE, None)
        return LockedState(AttendanceState(row.state), row.last_event_id)
