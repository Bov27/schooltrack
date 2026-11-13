"""Authorization and tenant isolation through the HTTP API.

Two fictional schools, A and B. Every test checks that a user of A cannot read or
change B's data, whatever they put in headers or bodies.
"""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from tests.db_support import (
    Factory,
    auth,
    requires_database,
)

pytestmark = [requires_database]
CAMPUSES = "/api/v1/campuses"


@dataclass
class World:
    a: uuid.UUID
    b: uuid.UUID
    campus_a: uuid.UUID
    campus_b: uuid.UUID


@pytest.fixture
def world(factory: Factory) -> World:
    a, b = factory.institution("colegio-a"), factory.institution("colegio-b")
    admin_a = factory.user("admin@colegio-a.test")
    teacher_a = factory.user("teacher@colegio-a.test")
    admin_b = factory.user("admin@colegio-b.test")
    factory.member(a, admin_a, "SCHOOL_ADMIN")
    factory.member(a, teacher_a, "TEACHER")
    factory.member(b, admin_b, "SCHOOL_ADMIN")
    return World(a, b, factory.campus(a, "Sede Norte"), factory.campus(b, "Sede Sur"))


def test_institutions_lists_only_own(api: TestClient, world: World) -> None:
    response = api.get("/api/v1/institutions", headers=auth(api, "admin@colegio-a.test"))
    assert response.status_code == 200
    assert [i["id"] for i in response.json()] == [str(world.a)]


def test_campuses_of_own_institution(api: TestClient, world: World) -> None:
    response = api.get(CAMPUSES, headers=auth(api, "teacher@colegio-a.test", world.a))
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [str(world.campus_a)]


def test_single_membership_does_not_need_the_header(api: TestClient, world: World) -> None:
    response = api.get(CAMPUSES, headers=auth(api, "teacher@colegio-a.test"))
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [str(world.campus_a)]


def test_header_for_another_institution_is_refused(api: TestClient, world: World) -> None:
    response = api.get(CAMPUSES, headers=auth(api, "admin@colegio-a.test", world.b))
    assert response.status_code == 403


def test_unknown_institution_gets_the_same_answer_as_a_foreign_one(
    api: TestClient, world: World
) -> None:
    foreign = api.get(CAMPUSES, headers=auth(api, "admin@colegio-a.test", world.b))
    unknown = api.get(CAMPUSES, headers=auth(api, "admin@colegio-a.test", uuid.uuid4()))
    assert foreign.status_code == unknown.status_code == 403
    assert foreign.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_several_memberships_require_the_header(
    api: TestClient, world: World, factory: Factory
) -> None:
    both = factory.user("both@example.test")
    factory.member(world.a, both, "TEACHER")
    factory.member(world.b, both, "TEACHER")
    assert api.get(CAMPUSES, headers=auth(api, "both@example.test")).status_code == 400
    in_b = api.get(CAMPUSES, headers=auth(api, "both@example.test", world.b))
    assert [c["id"] for c in in_b.json()] == [str(world.campus_b)]


def test_suspended_membership_has_no_access(
    api: TestClient, world: World, factory: Factory
) -> None:
    user = factory.user("suspended@colegio-a.test")
    factory.member(world.a, user, "SCHOOL_ADMIN", status="SUSPENDED")
    headers = auth(api, "suspended@colegio-a.test", world.a)
    assert api.get(CAMPUSES, headers=headers).status_code == 403
    assert api.get("/api/v1/institutions", headers=headers).json() == []


def test_school_admin_creates_campus_in_own_institution(api: TestClient, world: World) -> None:
    response = api.post(
        CAMPUSES,
        json={"name": "Sede Centro", "timezone": "America/Bogota"},
        headers=auth(api, "admin@colegio-a.test", world.a),
    )
    assert response.status_code == 201, response.text
    assert response.json()["institution_id"] == str(world.a)


def test_client_cannot_choose_the_institution_in_the_body(api: TestClient, world: World) -> None:
    response = api.post(
        CAMPUSES,
        json={"name": "Infiltrada", "institution_id": str(world.b)},
        headers=auth(api, "admin@colegio-a.test", world.a),
    )
    assert response.status_code == 422
    b_campuses = api.get(CAMPUSES, headers=auth(api, "admin@colegio-b.test")).json()
    assert [c["name"] for c in b_campuses] == ["Sede Sur"]


def test_teacher_cannot_create_campus(api: TestClient, world: World) -> None:
    response = api.post(
        CAMPUSES, json={"name": "Sede X"}, headers=auth(api, "teacher@colegio-a.test", world.a)
    )
    assert response.status_code == 403


def test_duplicate_campus_name_conflicts_only_within_institution(
    api: TestClient, world: World
) -> None:
    # "Sede Sur" exists in B, so A may use the name...
    headers = auth(api, "admin@colegio-a.test", world.a)
    assert api.post(CAMPUSES, json={"name": "Sede Sur"}, headers=headers).status_code == 201
    # ...but not twice.
    assert api.post(CAMPUSES, json={"name": "Sede Sur"}, headers=headers).status_code == 409


def test_invalid_timezone_is_rejected(api: TestClient, world: World) -> None:
    response = api.post(
        CAMPUSES,
        json={"name": "Sede Luna", "timezone": "Mars/Olympus"},
        headers=auth(api, "admin@colegio-a.test", world.a),
    )
    assert response.status_code == 422


# ---- platform (Super Admin) -----------------------------------------------------

def test_platform_admin_creates_institution_with_first_admin(
    api: TestClient, world: World, factory: Factory
) -> None:
    factory.platform_admin(factory.user("root@schooltrack.test"))
    factory.user("rector@colegio-c.test")
    response = api.post(
        "/api/v1/institutions",
        json={"name": "Colegio C", "slug": "colegio-c", "admin_email": "rector@colegio-c.test"},
        headers=auth(api, "root@schooltrack.test"),
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["id"]

    me = api.get("/api/v1/users/me", headers=auth(api, "rector@colegio-c.test")).json()
    assert me["memberships"] == [
        {"institution_id": new_id, "institution_name": "Colegio C", "roles": ["SCHOOL_ADMIN"]}
    ]


def test_school_admin_cannot_create_institutions(api: TestClient, world: World) -> None:
    response = api.post(
        "/api/v1/institutions",
        json={"name": "Colegio Z", "slug": "colegio-z"},
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 403


def test_duplicate_slug_conflicts(api: TestClient, world: World, factory: Factory) -> None:
    factory.platform_admin(factory.user("root@schooltrack.test"))
    response = api.post(
        "/api/v1/institutions",
        json={"name": "Otro A", "slug": "colegio-a"},
        headers=auth(api, "root@schooltrack.test"),
    )
    assert response.status_code == 409


def test_unknown_admin_email_is_reported(api: TestClient, world: World, factory: Factory) -> None:
    factory.platform_admin(factory.user("root@schooltrack.test"))
    response = api.post(
        "/api/v1/institutions",
        json={"name": "Colegio D", "slug": "colegio-d", "admin_email": "nobody@example.test"},
        headers=auth(api, "root@schooltrack.test"),
    )
    assert response.status_code == 404
