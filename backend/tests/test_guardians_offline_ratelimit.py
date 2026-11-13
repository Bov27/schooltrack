"""Guardians, offline synchronization and login rate limiting."""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.db_support import DEFAULT_PASSWORD, Factory, auth, requires_database
from tests.geo_support import POPAYAN, offset, wkt_square

pytestmark = [requires_database]


@dataclass
class School:
    inst: uuid.UUID
    campus: uuid.UUID
    student: uuid.UUID
    other_student: uuid.UUID


@pytest.fixture
def school(factory: Factory) -> School:
    inst = factory.institution("colegio-a")
    factory.member(inst, factory.user("admin@colegio-a.test"), "SCHOOL_ADMIN")
    ana = factory.user("ana@colegio-a.test")
    factory.member(inst, ana, "STUDENT")
    student = factory.student(inst, "A-001", ana)
    other = factory.student(inst, "A-002")
    factory.user("mama@colegio-a.test")
    campus = factory.campus(inst, "Sede Centro")
    factory.geofence(inst, campus, wkt_square(POPAYAN, 100))
    return School(inst, campus, student, other)


def event(school: School, event_type: str, occurred: datetime, **extra: Any) -> dict[str, Any]:
    lat, lng = offset(POPAYAN, 0, 0)
    return {
        "idempotency_key": str(uuid.uuid4()),
        "event_type": event_type,
        "campus_id": str(school.campus),
        "occurred_at": occurred.isoformat(),
        "latitude": lat,
        "longitude": lng,
        "accuracy_m": 6,
        "location_captured_at": (occurred - timedelta(seconds=3)).isoformat(),
        **extra,
    }


# ---- guardians -------------------------------------------------------------------------

def test_admin_links_a_guardian_who_then_follows_the_student(
    api: TestClient, school: School, owner_conn: Any
) -> None:
    admin = auth(api, "admin@colegio-a.test")
    guardian = api.post(
        "/api/v1/guardians", json={"user_email": "mama@colegio-a.test"}, headers=admin
    )
    assert guardian.status_code == 201, guardian.text
    guardian_id = guardian.json()["id"]
    link = api.post(
        f"/api/v1/guardians/{guardian_id}/students",
        json={"student_id": str(school.student), "relationship": "MOTHER"},
        headers=admin,
    )
    assert link.status_code == 201
    again = api.post(
        f"/api/v1/guardians/{guardian_id}/students",
        json={"student_id": str(school.student), "relationship": "MOTHER"},
        headers=admin,
    )
    assert again.status_code == 409
    assert owner_conn.execute(
        "SELECT action FROM audit_logs WHERE action = 'guardian.linked'"
    ).fetchall() == [("guardian.linked",)]

    # The student checks in; the guardian sees the state and the event.
    now = datetime.now(UTC)
    assert api.post(
        "/api/v1/attendance/events",
        json=event(school, "CHECK_IN", now),
        headers=auth(api, "ana@colegio-a.test"),
    ).status_code == 201
    mother = auth(api, "mama@colegio-a.test")
    [child] = api.get("/api/v1/attendance/guardian/students", headers=mother).json()
    assert (child["full_name"], child["state"]) == ("Estudiante A-001", "PRESENT")
    events = api.get(
        "/api/v1/attendance/events", params={"student_id": str(school.student)}, headers=mother
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["location"] is None

    other = api.get(
        "/api/v1/attendance/events",
        params={"student_id": str(school.other_student)},
        headers=mother,
    )
    assert other.status_code == 403


def test_only_admins_manage_guardians(api: TestClient, school: School) -> None:
    response = api.post(
        "/api/v1/guardians",
        json={"user_email": "mama@colegio-a.test"},
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert response.status_code == 403


# ---- offline synchronization ------------------------------------------------------------

def sync(api: TestClient, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response = api.post(
        "/api/v1/attendance/events/sync",
        json={"events": events},
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert response.status_code == 200, response.text
    results: list[dict[str, Any]] = response.json()["results"]
    return results


def test_offline_day_is_applied_in_order(api: TestClient, school: School) -> None:
    start = datetime.now(UTC) - timedelta(hours=6)
    batch = [
        event(school, "CHECK_OUT", start + timedelta(hours=5)),
        event(school, "CHECK_IN", start),
        event(school, "RETURN", start + timedelta(hours=3)),
        event(school, "TEMPORARY_CHECK_OUT", start + timedelta(hours=2)),
    ]
    results = sync(api, batch)
    assert [r["outcome"] for r in results] == ["created"] * 4
    assert [r["event"]["event_type"] for r in results] == [
        "CHECK_IN", "TEMPORARY_CHECK_OUT", "RETURN", "CHECK_OUT"
    ]
    assert {r["event"]["source"] for r in results} == {"OFFLINE_SYNC"}
    assert {r["event"]["validation_status"] for r in results} == {"VALIDATED"}

    # Retrying the same batch is harmless.
    assert [r["outcome"] for r in sync(api, batch)] == ["replayed"] * 4


def test_one_bad_item_does_not_discard_the_others(api: TestClient, school: School) -> None:
    now = datetime.now(UTC)
    results = sync(
        api,
        [
            event(school, "CHECK_IN", now - timedelta(hours=100)),  # beyond the 72 h window
            event(school, "CHECK_IN", now - timedelta(hours=2)),
            event(school, "CHECK_IN", now - timedelta(hours=1)),  # invalid: already PRESENT
        ],
    )
    assert [(r["outcome"], r["status_code"]) for r in results] == [
        ("error", 422),
        ("created", 201),
        ("error", 409),
    ]


def test_offline_event_older_than_the_last_recorded_one_is_refused(
    api: TestClient, school: School
) -> None:
    now = datetime.now(UTC)
    live = api.post(
        "/api/v1/attendance/events",
        json=event(school, "CHECK_IN", now),
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert live.status_code == 201
    [result] = sync(api, [event(school, "CHECK_OUT", now - timedelta(hours=1))])
    assert (result["outcome"], result["status_code"]) == ("error", 409)
    assert "out of order" in result["error"]


def test_offline_location_rules_apply_at_the_time_of_the_event(
    api: TestClient, school: School
) -> None:
    occurred = datetime.now(UTC) - timedelta(hours=3)
    stale_fix = event(school, "CHECK_IN", occurred)
    stale_fix["location_captured_at"] = (occurred - timedelta(minutes=10)).isoformat()
    [result] = sync(api, [stale_fix])
    assert result["event"]["validation_status"] == "REJECTED"
    assert result["event"]["validation_reasons"] == ["LOCATION_TOO_OLD"]


# ---- login rate limiting ------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("REDIS_URL"), reason="needs REDIS_URL")
def test_repeated_failed_logins_are_throttled(
    api: TestClient, school: School, factory: Factory
) -> None:
    settings = make_settings(
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        login_max_attempts=3,
    )
    with TestClient(create_app(settings)) as client:
        bad = {"email": "ana@colegio-a.test", "password": "wrong"}
        for _ in range(3):
            assert client.post("/api/v1/auth/login", json=bad).status_code == 401
        blocked = client.post(
            "/api/v1/auth/login", json={"email": "ana@colegio-a.test", "password": DEFAULT_PASSWORD}
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0
        assert blocked.json()["error"]["code"] == "rate_limited"
