"""Students and staff registration."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.db_support import Factory, auth, requires_database

pytestmark = [requires_database]


@pytest.fixture
def school(factory: Factory) -> uuid.UUID:
    a = factory.institution("colegio-a")
    factory.member(a, factory.user("admin@colegio-a.test"), "SCHOOL_ADMIN")
    factory.member(a, factory.user("teacher@colegio-a.test"), "TEACHER")
    factory.user("nuevo@colegio-a.test")  # account exists, not yet a member
    factory.user("profe@colegio-a.test")
    return a


def test_admin_registers_student_linked_to_an_account(api: TestClient, school: uuid.UUID) -> None:
    admin = auth(api, "admin@colegio-a.test")
    response = api.post(
        "/api/v1/students",
        json={
            "student_code": "A-100",
            "full_name": "Nuevo Estudiante",
            "user_email": "nuevo@colegio-a.test",
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    assert response.json()["user_id"] is not None

    me = api.get("/api/v1/users/me", headers=auth(api, "nuevo@colegio-a.test")).json()
    assert me["memberships"][0]["roles"] == ["STUDENT"]


def test_student_without_account(api: TestClient, school: uuid.UUID) -> None:
    response = api.post(
        "/api/v1/students",
        json={"student_code": "A-101", "full_name": "Niña de primero"},
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 201
    assert response.json()["user_id"] is None


def test_duplicate_student_code_conflicts(api: TestClient, school: uuid.UUID) -> None:
    admin = auth(api, "admin@colegio-a.test")
    body = {"student_code": "A-102", "full_name": "Uno"}
    assert api.post("/api/v1/students", json=body, headers=admin).status_code == 201
    assert api.post("/api/v1/students", json=body, headers=admin).status_code == 409


def test_unknown_account_is_reported(api: TestClient, school: uuid.UUID) -> None:
    response = api.post(
        "/api/v1/students",
        json={"student_code": "A-103", "full_name": "X", "user_email": "ghost@x.test"},
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 404


def test_teacher_can_list_but_not_create_students(api: TestClient, school: uuid.UUID) -> None:
    teacher = auth(api, "teacher@colegio-a.test")
    assert api.get("/api/v1/students", headers=teacher).status_code == 200
    response = api.post(
        "/api/v1/students", json={"student_code": "A-104", "full_name": "X"}, headers=teacher
    )
    assert response.status_code == 403


def test_teacher_staff_gets_the_teacher_role(api: TestClient, school: uuid.UUID) -> None:
    response = api.post(
        "/api/v1/staff",
        json={
            "employee_code": "E-1",
            "staff_type": "TEACHER",
            "user_email": "profe@colegio-a.test",
        },
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 201, response.text
    me = api.get("/api/v1/users/me", headers=auth(api, "profe@colegio-a.test")).json()
    assert me["memberships"][0]["roles"] == ["TEACHER"]
    listing = api.get("/api/v1/staff", headers=auth(api, "admin@colegio-a.test")).json()
    assert [s["employee_code"] for s in listing] == ["E-1"]
