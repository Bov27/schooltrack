"""Authentication against the real database (login, refresh rotation, logout, /users/me)."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.security import create_token
from tests.conftest import make_settings
from tests.db_support import (
    DEFAULT_PASSWORD,
    Factory,
    auth,
    login,
    requires_database,
)

pytestmark = [requires_database]
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


def test_login_returns_token_pair(api: TestClient, factory: Factory) -> None:
    factory.user("ana@colegio-a.test")
    body = login(api, "ana@colegio-a.test")
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert 0 < body["expires_in"] <= 15 * 60


def test_login_email_is_case_insensitive(api: TestClient, factory: Factory) -> None:
    factory.user("ana@colegio-a.test")
    login(api, "  Ana@Colegio-A.test ")


def test_wrong_password_and_unknown_email_get_the_same_answer(
    api: TestClient, factory: Factory
) -> None:
    factory.user("ana@colegio-a.test")
    wrong = api.post(LOGIN, json={"email": "ana@colegio-a.test", "password": "nope"})
    unknown = api.post(LOGIN, json={"email": "ghost@colegio-a.test", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.headers["WWW-Authenticate"] == "Bearer"


def test_inactive_user_cannot_log_in(api: TestClient, factory: Factory) -> None:
    factory.user("old@colegio-a.test", active=False)
    response = api.post(LOGIN, json={"email": "old@colegio-a.test", "password": DEFAULT_PASSWORD})
    assert response.status_code == 401


def test_me_requires_a_valid_access_token(api: TestClient, factory: Factory) -> None:
    assert api.get("/api/v1/users/me").status_code == 401
    bad = api.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401

    user_id = factory.user("ana@colegio-a.test")
    refresh_only = login(api, "ana@colegio-a.test")["refresh_token"]
    wrong_type = api.get("/api/v1/users/me", headers={"Authorization": f"Bearer {refresh_only}"})
    assert wrong_type.status_code == 401

    expired, _ = create_token(
        make_settings(), subject=user_id, token_type="access", ttl=timedelta(seconds=-5)
    )
    response = api.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_lists_active_memberships_and_roles(api: TestClient, factory: Factory) -> None:
    user = factory.user("ana@colegio-a.test")
    a, b, c = (factory.institution(s) for s in ("colegio-a", "colegio-b", "colegio-c"))
    factory.member(a, user, "SCHOOL_ADMIN", "TEACHER")
    factory.member(b, user, "GUARDIAN")
    factory.member(c, user, "TEACHER", status="SUSPENDED")

    response = api.get("/api/v1/users/me", headers=auth(api, "ana@colegio-a.test"))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ana@colegio-a.test"
    assert body["is_platform_admin"] is False
    memberships = {m["institution_id"]: sorted(m["roles"]) for m in body["memberships"]}
    assert memberships == {str(a): ["SCHOOL_ADMIN", "TEACHER"], str(b): ["GUARDIAN"]}


def test_deactivated_user_loses_access_immediately(api: TestClient, factory: Factory) -> None:
    user = factory.user("ana@colegio-a.test")
    headers = auth(api, "ana@colegio-a.test")
    factory.conn.execute("UPDATE users SET is_active = false WHERE id = %s", (user,))
    assert api.get("/api/v1/users/me", headers=headers).status_code == 401


def test_refresh_rotates_the_token(api: TestClient, factory: Factory) -> None:
    factory.user("ana@colegio-a.test")
    first = login(api, "ana@colegio-a.test")
    second = api.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    third = api.post(REFRESH, json={"refresh_token": second.json()["refresh_token"]})
    assert third.status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_the_whole_login(
    api: TestClient, factory: Factory
) -> None:
    factory.user("ana@colegio-a.test")
    stolen = login(api, "ana@colegio-a.test")["refresh_token"]
    legit = api.post(REFRESH, json={"refresh_token": stolen}).json()["refresh_token"]

    # The attacker replays the old token: rejected, and the family is revoked...
    assert api.post(REFRESH, json={"refresh_token": stolen}).status_code == 401
    # ...so the legitimate client's newer token stops working too.
    assert api.post(REFRESH, json={"refresh_token": legit}).status_code == 401


def test_other_logins_survive_a_revoked_family(api: TestClient, factory: Factory) -> None:
    factory.user("ana@colegio-a.test")
    phone = login(api, "ana@colegio-a.test")["refresh_token"]
    laptop = login(api, "ana@colegio-a.test")["refresh_token"]
    api.post("/api/v1/auth/logout", json={"refresh_token": phone})
    assert api.post(REFRESH, json={"refresh_token": phone}).status_code == 401
    assert api.post(REFRESH, json={"refresh_token": laptop}).status_code == 200


def test_logout_with_garbage_is_silent(api: TestClient) -> None:
    assert api.post("/api/v1/auth/logout", json={"refresh_token": "garbage"}).status_code == 204


def test_access_token_cannot_be_used_to_refresh(api: TestClient, factory: Factory) -> None:
    factory.user("ana@colegio-a.test")
    access = login(api, "ana@colegio-a.test")["access_token"]
    assert api.post(REFRESH, json={"refresh_token": access}).status_code == 401
