"""Runs against a real PostGIS database (docker compose or CI).

Skipped when DATABASE_URL is unset.
"""

import asyncio
import os

import pytest

from app.infrastructure.database import Database
from tests.conftest import make_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"),
]


def test_runtime_role_cannot_bypass_rls_and_postgis_is_installed() -> None:
    async def run() -> None:
        database = Database(make_settings(database_url=os.environ["DATABASE_URL"]))
        try:
            probe = await database.probe()
        finally:
            await database.dispose()
        assert probe.reachable, probe.error
        assert probe.postgis_version is not None
        assert probe.role == "schooltrack_app"
        assert probe.role_bypasses_rls is False

    asyncio.run(run())
