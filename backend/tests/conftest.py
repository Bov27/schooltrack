from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.database import DatabaseProbe
from app.main import create_app

# Database fixtures (owner_conn, factory, api) live in tests/db_support.py.
pytest_plugins = ["tests.db_support"]

# A syntactically valid URL; unit tests never open a connection to it.
UNIT_DB_URL = "postgresql+psycopg://unit:unit@localhost:1/unit"
TEST_JWT_SECRET = "test-secret-that-is-long-enough-for-hs256-0123456789"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": UNIT_DB_URL,
        "environment": "test",
        "jwt_secret": TEST_JWT_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class FakeDatabase:
    """Stands in for app.infrastructure.database.Database in unit tests."""

    def __init__(self, probe: DatabaseProbe) -> None:
        self._probe = probe

    async def probe(self) -> DatabaseProbe:
        return self._probe

    async def dispose(self) -> None:
        return None


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def use_fake_database(client: TestClient, probe: DatabaseProbe) -> None:
    client.app.state.database = FakeDatabase(probe)  # type: ignore[attr-defined]
