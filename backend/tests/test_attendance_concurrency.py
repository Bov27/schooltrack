"""Concurrency: simultaneous events for one person must be serialized by the row lock
on attendance_subject_states, so the state machine never sees a stale state."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import DomainError
from app.infrastructure.database import Database
from app.infrastructure.orm import set_current_institution, set_current_user
from app.modules.attendance.schemas import AttendanceEventCreate
from app.modules.attendance.service import AttendanceService, RecordResult
from tests.conftest import make_settings
from tests.db_support import Factory, requires_database
from tests.geo_support import POPAYAN, wkt_square

pytestmark = [requires_database]


@pytest.fixture
def setup(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    inst = factory.institution("colegio-a")
    user = factory.user("ana@colegio-a.test")
    factory.member(inst, user, "STUDENT")
    factory.student(inst, "A-001", user)
    campus = factory.campus(inst, "Sede Centro")
    factory.geofence(inst, campus, wkt_square(POPAYAN, 100))
    return inst, user, campus


def body(campus: uuid.UUID, key: uuid.UUID, event_type: str = "CHECK_IN") -> AttendanceEventCreate:
    now = datetime.now(UTC)
    return AttendanceEventCreate(
        idempotency_key=key,
        event_type=event_type,  # type: ignore[arg-type]
        campus_id=campus,
        occurred_at=now,
        latitude=POPAYAN[0],
        longitude=POPAYAN[1],
        accuracy_m=5,
        location_captured_at=now,
    )


async def run_concurrently(
    inst: uuid.UUID, user: uuid.UUID, bodies: list[AttendanceEventCreate]
) -> list[Any]:
    settings = make_settings(database_url=os.environ["DATABASE_URL"])
    database = Database(settings)

    async def attempt(payload: AttendanceEventCreate) -> RecordResult:
        async with database.session_factory() as session:
            await set_current_user(session, user)
            await set_current_institution(session, inst)
            return await AttendanceService(session, settings).record_own(inst, user, payload)

    try:
        return await asyncio.gather(*(attempt(b) for b in bodies), return_exceptions=True)
    finally:
        await database.dispose()


def test_simultaneous_check_ins_produce_exactly_one_event(
    setup: tuple[uuid.UUID, uuid.UUID, uuid.UUID], owner_conn: Any
) -> None:
    inst, user, campus = setup
    results = asyncio.run(
        run_concurrently(inst, user, [body(campus, uuid.uuid4()) for _ in range(8)])
    )
    created = [r for r in results if isinstance(r, RecordResult)]
    refused = [r for r in results if isinstance(r, DomainError)]
    unexpected = [r for r in results if not isinstance(r, (RecordResult, DomainError))]
    assert unexpected == []
    assert len(created) == 1
    assert len(refused) == 7
    assert all(r.status_code == 409 for r in refused)

    rows = owner_conn.execute("SELECT state_after::text FROM attendance_events").fetchall()
    assert rows == [("PRESENT",)]


def test_simultaneous_retries_of_one_request_store_it_once(
    setup: tuple[uuid.UUID, uuid.UUID, uuid.UUID], owner_conn: Any
) -> None:
    inst, user, campus = setup
    key = uuid.uuid4()
    results = asyncio.run(run_concurrently(inst, user, [body(campus, key) for _ in range(6)]))
    assert all(isinstance(r, RecordResult) for r in results), results
    assert {r.event["id"] for r in results} == {results[0].event["id"]}
    assert sum(r.created for r in results) == 1
    count = owner_conn.execute("SELECT count(*) FROM attendance_events").fetchone()
    assert count == (1,)
