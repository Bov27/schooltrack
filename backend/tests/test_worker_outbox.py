"""Transactional outbox and notification delivery (ADR-005), against the real database
with the worker role."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.workers.processing import deliver_notifications, dispatch_outbox
from app.workers.push import PushMessage, PushResult
from tests.db_support import Factory, auth, requires_database
from tests.geo_support import POPAYAN, offset, wkt_square

pytestmark = [
    requires_database,
    pytest.mark.skipif(
        not os.environ.get("WORKER_DATABASE_URL"), reason="needs WORKER_DATABASE_URL"
    ),
]


class FakeSender:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[PushMessage] = []

    def send(self, messages: list[PushMessage]) -> list[PushResult]:
        self.sent.extend(messages)
        error = None if self.ok else "DeviceNotRegistered"
        return [PushResult(ok=self.ok, error=error) for _ in messages]


@dataclass
class School:
    inst: uuid.UUID
    campus: uuid.UUID
    guardian_user: uuid.UUID


@pytest.fixture
def worker_conn(owner_conn: Any) -> Iterator[psycopg.Connection[Any]]:
    dsn = os.environ["WORKER_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn:
        yield conn


@pytest.fixture
def school(factory: Factory) -> School:
    inst = factory.institution("colegio-a")
    student_user = factory.user("ana@colegio-a.test", name="Ana Gómez")
    factory.member(inst, student_user, "STUDENT")
    student = factory.student(inst, "A-001", student_user, name="Ana Gómez")
    mother = factory.user("mama@colegio-a.test")
    factory.member(inst, mother, "GUARDIAN")
    factory.guardian(inst, mother, student)
    uncle = factory.user("tio@colegio-a.test")
    factory.member(inst, uncle, "GUARDIAN")
    factory.guardian(inst, uncle, student, receives_alerts=False)
    campus = factory.campus(inst, "Sede Centro")
    factory.geofence(inst, campus, wkt_square(POPAYAN, 100))
    return School(inst, campus, mother)


def record(
    api: TestClient, school: School, event_type: str = "CHECK_IN", north_m: float = 0
) -> Any:
    lat, lng = offset(POPAYAN, north_m, 0)
    now = datetime.now(UTC)
    return api.post(
        "/api/v1/attendance/events",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "event_type": event_type,
            "campus_id": str(school.campus),
            "occurred_at": now.isoformat(),
            "latitude": lat,
            "longitude": lng,
            "accuracy_m": 5,
            "location_captured_at": (now - timedelta(seconds=1)).isoformat(),
        },
        headers=auth(api, "ana@colegio-a.test"),
    )


def outbox(owner_conn: Any) -> list[tuple[Any, ...]]:
    return owner_conn.execute(
        "SELECT topic, processed_at IS NOT NULL, attempts FROM outbox_events ORDER BY id"
    ).fetchall()


def notifications(owner_conn: Any) -> list[tuple[Any, ...]]:
    return owner_conn.execute(
        "SELECT recipient_user_id, title, body, status::text, attempts FROM notifications "
        "ORDER BY created_at"
    ).fetchall()


def test_event_and_outbox_message_are_committed_together(
    api: TestClient, school: School, owner_conn: Any
) -> None:
    assert record(api, school).status_code == 201
    assert outbox(owner_conn) == [("attendance.event_recorded", False, 0)]


def test_refused_or_rejected_events_produce_no_message(
    api: TestClient, school: School, owner_conn: Any
) -> None:
    assert record(api, school, north_m=500).json()["validation_status"] == "REJECTED"
    assert record(api, school, "CHECK_OUT").status_code == 409
    assert outbox(owner_conn) == []


def test_dispatch_notifies_only_guardians_who_receive_alerts(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any
) -> None:
    record(api, school)
    assert dispatch_outbox(worker_conn) == 1
    [(recipient, title, body, status, attempts)] = notifications(owner_conn)
    assert recipient == school.guardian_user
    assert title == "Llegada: Ana"
    assert body.startswith("Ana Gómez llegó a Sede Centro a las ")
    assert (status, attempts) == ("PENDING", 0)
    assert outbox(owner_conn) == [("attendance.event_recorded", True, 0)]


def test_redelivered_outbox_message_does_not_notify_twice(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any
) -> None:
    record(api, school)
    dispatch_outbox(worker_conn)
    owner_conn.execute("UPDATE outbox_events SET processed_at = NULL")  # simulate a crash
    dispatch_outbox(worker_conn)
    assert len(notifications(owner_conn)) == 1


def test_failing_message_is_retried_later_without_blocking_others(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any
) -> None:
    owner_conn.execute(
        "INSERT INTO outbox_events (institution_id, topic, payload) VALUES (%s, 'unknown', '{}')",
        (school.inst,),
    )
    record(api, school)
    assert dispatch_outbox(worker_conn) == 1
    rows = owner_conn.execute(
        "SELECT topic, processed_at IS NOT NULL, attempts, last_error, available_at > now() "
        "FROM outbox_events ORDER BY id"
    ).fetchall()
    assert rows[0][:3] == ("unknown", False, 1)
    assert "no handler" in rows[0][3]
    assert rows[0][4] is True  # backed off
    assert rows[1][:3] == ("attendance.event_recorded", True, 0)


def test_delivery_to_the_guardians_phone(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any, factory: Factory
) -> None:
    factory.device(school.guardian_user, "ExponentPushToken[mama-phone]")
    record(api, school)
    dispatch_outbox(worker_conn)
    sender = FakeSender()
    assert deliver_notifications(worker_conn, sender, max_attempts=3) == 1
    assert [m.token for m in sender.sent] == ["ExponentPushToken[mama-phone]"]
    assert sender.sent[0].title == "Llegada: Ana"
    assert notifications(owner_conn)[0][3:] == ("SENT", 1)


def test_without_a_push_device_the_notification_stays_in_app(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any
) -> None:
    record(api, school)
    dispatch_outbox(worker_conn)
    sender = FakeSender()
    assert deliver_notifications(worker_conn, sender, max_attempts=3) == 1
    assert sender.sent == []
    assert notifications(owner_conn)[0][3] == "SENT"


def test_push_failures_back_off_then_give_up(
    api: TestClient, school: School, owner_conn: Any, worker_conn: Any, factory: Factory
) -> None:
    factory.device(school.guardian_user, "ExponentPushToken[broken]")
    record(api, school)
    dispatch_outbox(worker_conn)
    failing = FakeSender(ok=False)

    assert deliver_notifications(worker_conn, failing, max_attempts=2) == 0
    status, attempts, due_later = owner_conn.execute(
        "SELECT status::text, attempts, next_attempt_at > now() FROM notifications"
    ).fetchone()
    assert (status, attempts, due_later) == ("PENDING", 1, True)

    # Not due yet: nothing is retried.
    assert deliver_notifications(worker_conn, failing, max_attempts=2) == 0
    assert len(failing.sent) == 1

    owner_conn.execute("UPDATE notifications SET next_attempt_at = now()")
    deliver_notifications(worker_conn, failing, max_attempts=2)
    assert owner_conn.execute("SELECT status::text, attempts FROM notifications").fetchone() == (
        "FAILED",
        2,
    )


def test_guardian_reads_and_acknowledges_notifications(
    api: TestClient, school: School, worker_conn: Any
) -> None:
    record(api, school)
    dispatch_outbox(worker_conn)
    mother = auth(api, "mama@colegio-a.test")
    listing = api.get("/api/v1/notifications", headers=mother).json()
    assert [n["title"] for n in listing] == ["Llegada: Ana"]

    other = api.post(
        f"/api/v1/notifications/{listing[0]['id']}/read", headers=auth(api, "tio@colegio-a.test")
    )
    assert other.status_code == 404

    read = api.post(f"/api/v1/notifications/{listing[0]['id']}/read", headers=mother)
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert api.get("/api/v1/notifications", params={"unread": True}, headers=mother).json() == []
