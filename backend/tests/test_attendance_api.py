"""Attendance engine through the API, against real PostGIS."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.db_support import Factory, auth, requires_database
from tests.geo_support import CALI, POPAYAN, offset, wkt_square

pytestmark = [requires_database]
EVENTS = "/api/v1/attendance/events"


@dataclass
class School:
    a: uuid.UUID
    b: uuid.UUID
    campus: uuid.UUID
    campus_cali: uuid.UUID
    campus_b: uuid.UUID
    student: uuid.UUID
    student_user: uuid.UUID
    kid_without_phone: uuid.UUID


@pytest.fixture
def school(factory: Factory) -> School:
    a, b = factory.institution("colegio-a"), factory.institution("colegio-b")
    admin = factory.user("admin@colegio-a.test")
    student_user = factory.user("ana@colegio-a.test")
    factory.member(a, admin, "SCHOOL_ADMIN")
    factory.member(a, student_user, "STUDENT")
    factory.member(a, factory.user("nostudent@colegio-a.test"), "TEACHER")
    student = factory.student(a, "A-001", student_user)
    kid = factory.student(a, "A-002")

    campus = factory.campus(a, "Sede Centro")
    factory.geofence(a, campus, wkt_square(POPAYAN, 100))
    campus_cali = factory.campus(a, "Sede Cali")
    factory.geofence(a, campus_cali, wkt_square(CALI, 100))

    b_user = factory.user("bea@colegio-b.test")
    factory.member(b, b_user, "STUDENT")
    factory.student(b, "B-001", b_user)
    factory.member(b, factory.user("admin@colegio-b.test"), "SCHOOL_ADMIN")
    campus_b = factory.campus(b, "Sede B")
    return School(a, b, campus, campus_cali, campus_b, student, student_user, kid)


def event(
    school: School,
    event_type: str = "CHECK_IN",
    *,
    north_m: float = 0,
    origin: tuple[float, float] = POPAYAN,
    campus: uuid.UUID | None = None,
    accuracy_m: float = 8,
    age_s: float = 1,
    key: uuid.UUID | None = None,
    **extra: Any,
) -> dict[str, Any]:
    lat, lng = offset(origin, north_m, 0)
    now = datetime.now(UTC)
    body = {
        "idempotency_key": str(key or uuid.uuid4()),
        "event_type": event_type,
        "campus_id": str(campus or school.campus),
        "occurred_at": (now - timedelta(seconds=age_s)).isoformat(),
        "latitude": lat,
        "longitude": lng,
        "accuracy_m": accuracy_m,
        "location_captured_at": (now - timedelta(seconds=age_s + 1)).isoformat(),
    }
    body.update(extra)
    return body


def post(api: TestClient, body: dict[str, Any], email: str = "ana@colegio-a.test") -> Any:
    return api.post(EVENTS, json=body, headers=auth(api, email))


def state(api: TestClient, email: str = "ana@colegio-a.test") -> Any:
    return api.get("/api/v1/attendance/state", headers=auth(api, email)).json()


def count_events(owner_conn: psycopg.Connection[Any]) -> int:
    row = owner_conn.execute("SELECT count(*) FROM attendance_events").fetchone()
    assert row is not None
    return int(row[0])


# ---- happy path and state machine ------------------------------------------------------

def test_check_in_inside_the_campus(api: TestClient, school: School) -> None:
    response = post(api, event(school))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["validation_status"] == "VALIDATED"
    assert (body["state_before"], body["state_after"]) == ("OUTSIDE", "PRESENT")
    assert body["student_id"] == str(school.student)
    assert body["geofence_result"] == "INSIDE"
    assert body["location"] is None  # coordinates are not echoed to the student

    [current] = state(api)
    assert current["state"] == "PRESENT"
    assert sorted(current["allowed_events"]) == ["CHECK_OUT", "TEMPORARY_CHECK_OUT"]
    assert current["last_event_id"] == body["id"]


def test_full_school_day(api: TestClient, school: School) -> None:
    for event_type, expected in [
        ("CHECK_IN", "PRESENT"),
        ("TEMPORARY_CHECK_OUT", "TEMPORARY_EXIT"),
        ("RETURN", "PRESENT"),
        ("CHECK_OUT", "OUTSIDE"),
    ]:
        response = post(api, event(school, event_type))
        assert response.status_code == 201, response.text
        assert response.json()["state_after"] == expected


def test_duplicate_check_in_is_refused_and_not_stored(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any]
) -> None:
    assert post(api, event(school)).status_code == 201
    response = post(api, event(school))
    assert response.status_code == 409
    assert "Cannot CHECK_IN while PRESENT" in response.json()["error"]["message"]
    assert count_events(owner_conn) == 1


def test_check_out_without_check_in_is_refused(api: TestClient, school: School) -> None:
    assert post(api, event(school, "CHECK_OUT")).status_code == 409


# ---- idempotency --------------------------------------------------------------------

def test_retry_with_the_same_key_returns_the_original(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any]
) -> None:
    body = event(school)
    first = post(api, body)
    retry = post(api, body)
    assert (first.status_code, retry.status_code) == (201, 200)
    assert retry.json()["id"] == first.json()["id"]
    assert count_events(owner_conn) == 1


def test_late_retry_is_still_answered_with_the_original(api: TestClient, school: School) -> None:
    body = event(school)
    first = post(api, body).json()
    post(api, event(school, "CHECK_OUT"))  # state moved on since
    body["occurred_at"] = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    retry = post(api, body)
    assert retry.status_code == 200
    assert retry.json()["id"] == first["id"]


def test_reusing_a_key_for_a_different_action_conflicts(api: TestClient, school: School) -> None:
    key = uuid.uuid4()
    assert post(api, event(school, key=key)).status_code == 201
    assert post(api, event(school, "CHECK_OUT", key=key)).status_code == 409


# ---- validation outcomes ----------------------------------------------------------------

def test_outside_attempt_is_kept_as_evidence_but_state_does_not_change(
    api: TestClient, school: School
) -> None:
    response = post(api, event(school, north_m=300))
    assert response.status_code == 201
    body = response.json()
    assert body["validation_status"] == "REJECTED"
    assert body["validation_reasons"] == ["OUTSIDE_GEOFENCE"]
    assert body["state_after"] == "OUTSIDE"
    assert state(api)[0]["state"] == "OUTSIDE"
    # ...and a proper check-in still works afterwards.
    assert post(api, event(school)).json()["state_after"] == "PRESENT"


def test_boundary_case_is_accepted_but_flagged(api: TestClient, school: School) -> None:
    body = post(api, event(school, north_m=115, accuracy_m=25)).json()
    assert body["validation_status"] == "FLAGGED_FOR_REVIEW"
    assert body["validation_reasons"] == ["BOUNDARY_UNCERTAIN"]
    assert body["state_after"] == "PRESENT"


def test_mock_location_is_flagged(api: TestClient, school: School) -> None:
    body = post(api, event(school, is_mock=True)).json()
    assert body["validation_status"] == "FLAGGED_FOR_REVIEW"
    assert "MOCK_LOCATION_REPORTED" in body["validation_reasons"]


def test_implausible_movement_between_campuses_is_flagged(
    api: TestClient, school: School
) -> None:
    assert post(api, event(school)).json()["validation_status"] == "VALIDATED"
    # A second later, "checking out" inside the Cali campus geofence, ~120 km away.
    body = post(api, event(school, "CHECK_OUT", origin=CALI, campus=school.campus_cali)).json()
    assert body["geofence_result"] == "INSIDE"
    assert body["validation_status"] == "FLAGGED_FOR_REVIEW"
    assert body["validation_reasons"] == ["IMPLAUSIBLE_MOVEMENT"]


@pytest.mark.parametrize("age_s", [60, -30])
def test_stale_or_future_requests_are_refused(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any], age_s: float
) -> None:
    assert post(api, event(school, age_s=age_s)).status_code == 422
    assert count_events(owner_conn) == 0


# ---- who may record what --------------------------------------------------------------

def test_account_without_student_or_staff_record_is_refused(
    api: TestClient, school: School
) -> None:
    assert post(api, event(school), email="nostudent@colegio-a.test").status_code == 403


def test_other_schools_campus_is_not_found(api: TestClient, school: School) -> None:
    response = post(api, event(school, campus=school.campus_b))
    assert response.status_code == 404


def test_device_must_be_the_callers_own(api: TestClient, school: School) -> None:
    headers = auth(api, "ana@colegio-a.test")
    device = api.post(
        "/api/v1/devices",
        json={"installation_id": "ana-phone-0001", "platform": "ANDROID"},
        headers=headers,
    )
    assert device.status_code == 200
    again = api.post(
        "/api/v1/devices",
        json={"installation_id": "ana-phone-0001", "platform": "ANDROID", "app_version": "1.1"},
        headers=headers,
    )
    assert again.json()["id"] == device.json()["id"]

    foreign = post(api, event(school, device_id=str(uuid.uuid4())))
    assert foreign.status_code == 403
    own = post(api, event(school, device_id=device.json()["id"]))
    assert own.status_code == 201


# ---- reading history -----------------------------------------------------------------

def test_students_see_only_their_own_events_without_coordinates(
    api: TestClient, school: School
) -> None:
    post(api, event(school))
    post(api, event(school, "CHECK_IN"), email="bea@colegio-b.test")  # other school, 404
    mine = api.get(EVENTS, headers=auth(api, "ana@colegio-a.test")).json()
    assert len(mine) == 1
    assert mine[0]["location"] is None

    other = api.get(
        EVENTS,
        params={"student_id": str(school.kid_without_phone)},
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert other.status_code == 403


def test_admin_sees_all_events_with_coordinates_and_can_filter(
    api: TestClient, school: School
) -> None:
    post(api, event(school, north_m=300))  # rejected
    post(api, event(school))  # validated
    headers = auth(api, "admin@colegio-a.test")
    everything = api.get(EVENTS, headers=headers).json()
    assert len(everything) == 2
    assert everything[0]["location"]["latitude"] == pytest.approx(POPAYAN[0], abs=1e-3)

    rejected = api.get(EVENTS, params={"validation_status": "REJECTED"}, headers=headers).json()
    assert [e["validation_reasons"] for e in rejected] == [["OUTSIDE_GEOFENCE"]]

    other_school = api.get(EVENTS, headers=auth(api, "admin@colegio-b.test")).json()
    assert other_school == []


# ---- review and manual entries (audited) -------------------------------------------

def test_admin_reviews_a_flagged_event(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any]
) -> None:
    flagged = post(api, event(school, is_mock=True)).json()
    url = f"{EVENTS}/{flagged['id']}/review"

    student_try = api.post(
        url,
        json={"decision": "VALIDATED", "note": "looks fine"},
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert student_try.status_code == 403

    admin = auth(api, "admin@colegio-a.test")
    reviewed = api.post(url, json={"decision": "REJECTED", "note": "mock GPS app"}, headers=admin)
    assert reviewed.status_code == 200
    assert reviewed.json()["validation_status"] == "REJECTED"
    assert reviewed.json()["event_type"] == "CHECK_IN"  # the event itself is unchanged

    again = api.post(url, json={"decision": "VALIDATED", "note": "changed mind"}, headers=admin)
    assert again.status_code == 409

    audit = owner_conn.execute(
        "SELECT action, changes->>'note' FROM audit_logs WHERE entity_id = %s",
        (flagged["id"],),
    ).fetchall()
    assert audit == [("attendance_event.reviewed", "mock GPS app")]


def test_admin_records_manual_event_for_child_without_phone(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any]
) -> None:
    body = {
        "idempotency_key": str(uuid.uuid4()),
        "event_type": "CHECK_IN",
        "campus_id": str(school.campus),
        "student_id": str(school.kid_without_phone),
        "reason": "Grado primero, sin celular",
    }
    response = api.post(
        "/api/v1/attendance/manual-events", json=body, headers=auth(api, "admin@colegio-a.test")
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert (created["source"], created["validation_status"]) == ("MANUAL", "VALIDATED")
    assert created["state_after"] == "PRESENT"
    assert created["location"] is None

    audit = owner_conn.execute(
        "SELECT action FROM audit_logs WHERE entity_id = %s", (created["id"],)
    ).fetchall()
    assert audit == [("attendance_event.manual_created",)]


def test_manual_event_requires_admin_and_reason(api: TestClient, school: School) -> None:
    body = {
        "idempotency_key": str(uuid.uuid4()),
        "event_type": "CHECK_IN",
        "campus_id": str(school.campus),
        "student_id": str(school.kid_without_phone),
        "reason": "x",
    }
    url = "/api/v1/attendance/manual-events"
    assert api.post(url, json=body, headers=auth(api, "admin@colegio-a.test")).status_code == 422
    body["reason"] = "Sin celular"
    assert api.post(url, json=body, headers=auth(api, "ana@colegio-a.test")).status_code == 403


# ---- immutability, enforced by the database --------------------------------------------

def test_events_cannot_be_altered_or_deleted_even_by_the_owner_role(
    api: TestClient, school: School, owner_conn: psycopg.Connection[Any]
) -> None:
    event_id = post(api, event(school)).json()["id"]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute(
            "UPDATE attendance_events SET event_type = 'CHECK_OUT' WHERE id = %s", (event_id,)
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute("DELETE FROM attendance_events WHERE id = %s", (event_id,))
    owner_conn.execute(
        "INSERT INTO audit_logs (action, entity_type) VALUES ('test.entry', 'test')"
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute("DELETE FROM audit_logs")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute("UPDATE audit_logs SET action = 'tampered'")
