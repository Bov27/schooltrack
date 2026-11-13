"""The fictional demo institution: it must be usable end to end through the real API."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.demo import ACCOUNTS, DEMO_SLUG, DemoAlreadyExistsError, _school_days, seed_demo
from tests.db_support import DEFAULT_PASSWORD, auth, requires_database

pytestmark = [requires_database]
TODAY = date(2026, 11, 13)  # a Friday
ADMIN, TEACHER, STUDENT, GUARDIAN = (a.email for a in ACCOUNTS)


def test_school_days_skip_weekends_and_today() -> None:
    days = _school_days(TODAY, 6)
    assert days[-1] == date(2026, 11, 12)
    assert days[0] == date(2026, 11, 5)
    assert all(d.weekday() < 5 for d in days)


@pytest.fixture
def demo(owner_conn: psycopg.Connection[Any]) -> uuid.UUID:
    with owner_conn.transaction():
        return seed_demo(owner_conn, DEFAULT_PASSWORD, today=datetime.now(UTC).date())


def test_seed_refuses_to_run_twice(owner_conn: psycopg.Connection[Any], demo: uuid.UUID) -> None:
    with pytest.raises(DemoAlreadyExistsError, match=DEMO_SLUG):
        seed_demo(owner_conn, DEFAULT_PASSWORD)


def test_admin_sees_two_weeks_of_attendance(api: TestClient, demo: uuid.UUID) -> None:
    end = datetime.now(UTC).date()
    response = api.get(
        "/api/v1/analytics/attendance",
        params={"from": (end - timedelta(days=21)).isoformat(), "to": end.isoformat()},
        headers=auth(api, ADMIN),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["students"]) == 8
    assert 0.6 < body["overall_rate"] < 1
    assert sum(s["flagged_events"] for s in body["students"]) > 0


def test_guardian_sees_both_students(api: TestClient, demo: uuid.UUID) -> None:
    response = api.get("/api/v1/attendance/guardian/students", headers=auth(api, GUARDIAN))
    assert response.status_code == 200, response.text
    assert sorted(s["full_name"] for s in response.json()) == ["Santiago Rivera", "Valentina Muñoz"]
    assert {s["state"] for s in response.json()} == {"OUTSIDE"}


@pytest.mark.parametrize("email", [STUDENT, TEACHER])
def test_live_check_in_inside_the_demo_geofence(
    api: TestClient, demo: uuid.UUID, email: str
) -> None:
    headers = auth(api, email)
    states = api.get("/api/v1/attendance/state", headers=headers).json()
    assert states[0]["state"] == "OUTSIDE"
    assert "CHECK_IN" in states[0]["allowed_events"]
    campus = api.get("/api/v1/campuses", headers=headers).json()[0]["id"]
    now = datetime.now(UTC)
    response = api.post(
        "/api/v1/attendance/events",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "event_type": "CHECK_IN",
            "campus_id": campus,
            "occurred_at": (now - timedelta(seconds=1)).isoformat(),
            "latitude": 2.4419,
            "longitude": -76.6063,
            "accuracy_m": 8,
            "location_captured_at": (now - timedelta(seconds=2)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["validation_status"] == "VALIDATED"
