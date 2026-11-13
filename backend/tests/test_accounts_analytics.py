"""Accounts created by school admins, linking accounts to existing students, and
attendance analytics with CSV export."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.db_support import DEFAULT_PASSWORD, Factory, auth, login, requires_database

pytestmark = [requires_database]
NEW_PASSWORD = "otra-clave-segura-2027"


@dataclass
class School:
    inst: uuid.UUID
    campus: uuid.UUID
    pepito: uuid.UUID


@pytest.fixture
def school(factory: Factory) -> School:
    inst = factory.institution("colegio-a")
    factory.member(inst, factory.user("admin@colegio-a.test"), "SCHOOL_ADMIN")
    factory.member(inst, factory.user("teacher@colegio-a.test"), "TEACHER")
    pepito = factory.student(inst, "123", name="Pepito Pérez")
    return School(inst, factory.campus(inst, "Sede Centro"), pepito)


# ---- accounts -----------------------------------------------------------------------


def create_account(api: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> Any:
    return api.post(
        "/api/v1/accounts",
        json={"email": email, "full_name": "Pepito Pérez", "initial_password": password},
        headers=auth(api, "admin@colegio-a.test"),
    )


def test_admin_creates_an_account_that_can_log_in(
    api: TestClient, school: School, owner_conn: Any
) -> None:
    response = create_account(api, "Pepito@Colegio-A.test")
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "pepito@colegio-a.test"
    login(api, "pepito@colegio-a.test", DEFAULT_PASSWORD)
    audit = owner_conn.execute(
        "SELECT action FROM audit_logs WHERE action = 'account.created'"
    ).fetchall()
    assert audit == [("account.created",)]


def test_duplicate_email_and_weak_password_are_refused(api: TestClient, school: School) -> None:
    assert create_account(api, "pepito@colegio-a.test").status_code == 201
    assert create_account(api, "pepito@colegio-a.test").status_code == 409
    assert create_account(api, "otro@colegio-a.test", password="corta").status_code == 422


def test_teachers_cannot_create_accounts(api: TestClient, school: School) -> None:
    response = api.post(
        "/api/v1/accounts",
        json={"email": "x@colegio-a.test", "full_name": "X", "initial_password": "a" * 12},
        headers=auth(api, "teacher@colegio-a.test"),
    )
    assert response.status_code == 403


def test_changing_the_password_signs_out_every_session(api: TestClient, school: School) -> None:
    create_account(api, "pepito@colegio-a.test")
    session = login(api, "pepito@colegio-a.test", DEFAULT_PASSWORD)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    wrong = api.post(
        "/api/v1/users/me/password",
        json={"current_password": "nope", "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert wrong.status_code == 400  # not 401: the session is still valid

    changed = api.post(
        "/api/v1/users/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert changed.status_code == 204
    refresh = api.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refresh.status_code == 401
    login(api, "pepito@colegio-a.test", NEW_PASSWORD)


# ---- linking accounts to existing students -----------------------------------------


def test_link_an_account_to_an_existing_student(api: TestClient, school: School) -> None:
    create_account(api, "pepito@colegio-a.test")
    admin = auth(api, "admin@colegio-a.test")
    linked = api.patch(
        f"/api/v1/students/{school.pepito}",
        json={"user_email": "pepito@colegio-a.test"},
        headers=admin,
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["user_id"] is not None

    pepito = auth(api, "pepito@colegio-a.test", school.inst)
    [state] = api.get("/api/v1/attendance/state", headers=pepito).json()
    assert (state["subject_id"], state["state"]) == (str(school.pepito), "OUTSIDE")

    unlinked = api.patch(
        f"/api/v1/students/{school.pepito}", json={"unlink_account": True}, headers=admin
    )
    assert unlinked.json()["user_id"] is None
    assert api.get("/api/v1/attendance/state", headers=pepito).json() == []


def test_one_account_cannot_be_two_students(
    api: TestClient, school: School, factory: Factory
) -> None:
    other = factory.student(school.inst, "124", name="Otra")
    create_account(api, "pepito@colegio-a.test")
    admin = auth(api, "admin@colegio-a.test")
    body = {"user_email": "pepito@colegio-a.test"}
    first = api.patch(f"/api/v1/students/{school.pepito}", json=body, headers=admin)
    assert first.status_code == 200
    second = api.patch(f"/api/v1/students/{other}", json=body, headers=admin)
    assert second.status_code == 409


def test_rename_and_deactivate_are_audited(
    api: TestClient, school: School, owner_conn: Any
) -> None:
    admin = auth(api, "admin@colegio-a.test")
    response = api.patch(
        f"/api/v1/students/{school.pepito}",
        json={"full_name": "José Pérez", "is_active": False},
        headers=admin,
    )
    assert response.json()["full_name"] == "José Pérez"
    assert response.json()["is_active"] is False
    [(changes,)] = owner_conn.execute(
        "SELECT changes FROM audit_logs WHERE action = 'student.updated'"
    ).fetchall()
    assert changes["full_name"] == ["Pepito Pérez", "José Pérez"]


# ---- analytics ------------------------------------------------------------------------


def add_check_in(owner_conn: Any, school: School, student: uuid.UUID, at: str, status: str) -> None:
    actor = owner_conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    owner_conn.execute(
        """
        INSERT INTO attendance_events (institution_id, campus_id, student_id, actor_user_id,
            event_type, source, state_before, state_after, occurred_at, location,
            idempotency_key, validation_status)
        VALUES (%s, %s, %s, %s, 'CHECK_IN', 'MOBILE_GPS', 'OUTSIDE', 'PRESENT', %s,
            ST_GeogFromText('SRID=4326;POINT(-76.6063 2.4419)'), gen_random_uuid(),
            %s::validation_status)
        """,
        (school.inst, school.campus, student, actor, at, status),
    )


@pytest.fixture
def week(school: School, owner_conn: Any, factory: Factory) -> School:
    """Mon 9 - Fri 13 Nov 2026 (Bogotá). Pepito: present Tue, Wed (flagged), Fri late
    evening; rejected Thu; a Saturday check-in that must not count."""
    add_check_in(owner_conn, school, school.pepito, "2026-11-10 07:00-05", "VALIDATED")
    add_check_in(owner_conn, school, school.pepito, "2026-11-11 07:30-05", "FLAGGED_FOR_REVIEW")
    add_check_in(owner_conn, school, school.pepito, "2026-11-12 08:00-05", "REJECTED")
    add_check_in(owner_conn, school, school.pepito, "2026-11-13 23:30-05", "VALIDATED")
    add_check_in(owner_conn, school, school.pepito, "2026-11-14 09:00-05", "VALIDATED")
    factory.student(school.inst, "125", name='=HYPERLINK("http://evil")')
    return school


RANGE = {"from": "2026-11-09", "to": "2026-11-15"}


def test_attendance_report(api: TestClient, week: School) -> None:
    response = api.get(
        "/api/v1/analytics/attendance",
        params=RANGE,
        headers=auth(api, "teacher@colegio-a.test"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["school_days"] == 5
    assert body["timezone"] == "America/Bogota"
    pepito = next(s for s in body["students"] if s["student_code"] == "123")
    assert pepito["days_present"] == 3
    assert pepito["attendance_rate"] == pytest.approx(0.6)
    assert pepito["average_first_check_in"] == "12:40"
    assert (pepito["flagged_events"], pepito["rejected_events"]) == (1, 1)
    assert [d["students_present"] for d in body["days"]] == [0, 1, 1, 0, 1]
    assert body["overall_rate"] == pytest.approx(3 / 10)


def test_csv_export_is_spreadsheet_safe(api: TestClient, week: School) -> None:
    response = api.get(
        "/api/v1/analytics/attendance.csv",
        params=RANGE,
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attendance_2026-11-09_2026-11-15.csv" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert text.startswith("﻿student_code,full_name,days_present")
    assert "123,Pepito Pérez,3,5,0.6,12:40,1,1,0" in text
    assert "'=HYPERLINK" in text  # formula neutralised


def test_analytics_permissions_and_validation(api: TestClient, school: School) -> None:
    create_account(api, "pepito@colegio-a.test")
    api.patch(
        f"/api/v1/students/{school.pepito}",
        json={"user_email": "pepito@colegio-a.test"},
        headers=auth(api, "admin@colegio-a.test"),
    )
    student = api.get(
        "/api/v1/analytics/attendance",
        params=RANGE,
        headers=auth(api, "pepito@colegio-a.test"),
    )
    assert student.status_code == 403
    backwards = api.get(
        "/api/v1/analytics/attendance",
        params={"from": "2026-11-15", "to": "2026-11-09"},
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert backwards.status_code == 400


def add_staff_event(owner_conn: Any, school: School, staff: uuid.UUID, kind: str, at: str) -> None:
    before, after = ("OUTSIDE", "PRESENT") if kind == "CHECK_IN" else ("PRESENT", "OUTSIDE")
    actor = owner_conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    owner_conn.execute(
        """
        INSERT INTO attendance_events (institution_id, campus_id, staff_id, actor_user_id,
            event_type, source, state_before, state_after, occurred_at, location,
            idempotency_key, validation_status)
        VALUES (%s, %s, %s, %s, %s, 'MOBILE_GPS', %s, %s, %s,
            ST_GeogFromText('SRID=4326;POINT(-76.6063 2.4419)'), gen_random_uuid(), 'VALIDATED')
        """,
        (school.inst, school.campus, staff, actor, kind, before, after, at),
    )


@pytest.fixture
def staffed(week: School, owner_conn: Any, factory: Factory) -> uuid.UUID:
    """Laura teaches; she comes Mon and Tue (7:00-13:00 and 6:30-12:00)."""
    laura = factory.staff(
        week.inst, "DOC-1", factory.user("laura@colegio-a.test", name="Laura Docente")
    )
    add_staff_event(owner_conn, week, laura, "CHECK_IN", "2026-11-09 07:00-05")
    add_staff_event(owner_conn, week, laura, "CHECK_OUT", "2026-11-09 13:00-05")
    add_staff_event(owner_conn, week, laura, "CHECK_IN", "2026-11-10 06:30-05")
    add_staff_event(owner_conn, week, laura, "CHECK_OUT", "2026-11-10 12:00-05")
    return laura


def test_staff_report_is_for_admins(api: TestClient, staffed: uuid.UUID) -> None:
    response = api.get(
        "/api/v1/analytics/staff", params=RANGE, headers=auth(api, "admin@colegio-a.test")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    laura = next(s for s in body["staff"] if s["employee_code"] == "DOC-1")
    assert laura["full_name"] == "Laura Docente"
    assert (laura["days_present"], laura["school_days"]) == (2, 5)
    assert laura["average_first_check_in"] == "06:45"
    assert laura["average_last_check_out"] == "12:30"
    assert [d["present"] for d in body["days"]] == [1, 1, 0, 0, 0]

    teacher = api.get(
        "/api/v1/analytics/staff", params=RANGE, headers=auth(api, "teacher@colegio-a.test")
    )
    assert teacher.status_code == 403


def test_one_students_days(api: TestClient, week: School) -> None:
    response = api.get(
        "/api/v1/analytics/person",
        params={**RANGE, "student_id": str(week.pepito)},
        headers=auth(api, "teacher@colegio-a.test"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Pepito Pérez"
    assert (body["days_present"], body["school_days"]) == (3, 5)
    assert [d["present"] for d in body["days"]] == [False, True, True, False, True]
    assert body["days"][1]["first_check_in"] == "07:00"
    assert body["days"][3]["rejected_events"] == 1  # rejected attempt on Thursday
    assert body["days"][2]["flagged_events"] == 1


def test_one_staff_members_days_and_validation(
    api: TestClient, staffed: uuid.UUID, week: School
) -> None:
    admin = auth(api, "admin@colegio-a.test")
    response = api.get(
        "/api/v1/analytics/person", params={**RANGE, "staff_id": str(staffed)}, headers=admin
    )
    assert response.status_code == 200, response.text
    assert response.json()["days"][0]["last_check_out"] == "13:00"

    teacher = auth(api, "teacher@colegio-a.test")
    hidden = api.get(
        "/api/v1/analytics/person", params={**RANGE, "staff_id": str(staffed)}, headers=teacher
    )
    assert hidden.status_code == 403
    both = api.get(
        "/api/v1/analytics/person",
        params={**RANGE, "staff_id": str(staffed), "student_id": str(week.pepito)},
        headers=admin,
    )
    assert both.status_code == 400
    unknown = api.get(
        "/api/v1/analytics/person", params={**RANGE, "student_id": str(uuid.uuid4())}, headers=admin
    )
    assert unknown.status_code == 404
