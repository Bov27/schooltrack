"""Fixtures and factories for tests that need the real database.

Data is written through the owner connection (a superuser in docker compose and CI,
so it bypasses RLS); the API under test connects with the restricted roles, exactly
as in production.
"""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import create_app
from tests.conftest import make_settings

REQUIRED_ENV = ("DATABASE_URL", "MIGRATIONS_DATABASE_URL", "PLATFORM_DATABASE_URL")
DEFAULT_PASSWORD = "correct-horse-battery-staple"
_DEFAULT_HASH = hash_password(DEFAULT_PASSWORD)

requires_database = pytest.mark.skipif(
    not all(os.environ.get(name) for name in REQUIRED_ENV),
    reason=f"needs {', '.join(REQUIRED_ENV)}",
)


def _libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


class Factory:
    """Creates fictional test data with the owner connection."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def _one(self, sql: str, params: tuple[Any, ...]) -> uuid.UUID:
        row = self.conn.execute(sql, params).fetchone()
        assert row is not None
        value: uuid.UUID = row[0]
        return value

    def user(self, email: str, *, active: bool = True, name: str | None = None) -> uuid.UUID:
        return self._one(
            "INSERT INTO users (email, full_name, password_hash, is_active) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (email, name or email.split("@")[0], _DEFAULT_HASH, active),
        )

    def platform_admin(self, user_id: uuid.UUID) -> None:
        self.conn.execute("INSERT INTO platform_admins (user_id) VALUES (%s)", (user_id,))

    def institution(self, slug: str, *, active: bool = True) -> uuid.UUID:
        return self._one(
            "INSERT INTO institutions (name, slug, is_active) VALUES (%s, %s, %s) RETURNING id",
            (slug.replace("-", " ").title(), slug, active),
        )

    def member(
        self,
        institution_id: uuid.UUID,
        user_id: uuid.UUID,
        *roles: str,
        status: str = "ACTIVE",
    ) -> None:
        self.conn.execute(
            "INSERT INTO institution_memberships (institution_id, user_id, status) "
            "VALUES (%s, %s, %s)",
            (institution_id, user_id, status),
        )
        for role in roles:
            self.conn.execute(
                "INSERT INTO user_roles (institution_id, user_id, role) VALUES (%s, %s, %s)",
                (institution_id, user_id, role),
            )

    def campus(self, institution_id: uuid.UUID, name: str) -> uuid.UUID:
        return self._one(
            "INSERT INTO campuses (institution_id, name) VALUES (%s, %s) RETURNING id",
            (institution_id, name),
        )


@pytest.fixture
def owner_conn() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(_libpq(os.environ["MIGRATIONS_DATABASE_URL"]), autocommit=True) as conn:
        conn.execute("TRUNCATE institutions, users RESTART IDENTITY CASCADE")
        yield conn


@pytest.fixture
def factory(owner_conn: psycopg.Connection[Any]) -> Factory:
    return Factory(owner_conn)


@pytest.fixture
def api(owner_conn: psycopg.Connection[Any]) -> Iterator[TestClient]:
    settings = make_settings(
        database_url=os.environ["DATABASE_URL"],
        platform_database_url=os.environ["PLATFORM_DATABASE_URL"],
    )
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> dict[str, Any]:
    response = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def auth(api: TestClient, email: str, institution_id: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {login(api, email)['access_token']}"}
    if institution_id is not None:
        headers["X-Institution-Id"] = str(institution_id)
    return headers
