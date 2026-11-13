"""Database engine, sessions and the readiness probe."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class DatabaseProbe:
    """Facts the readiness endpoint reports about the runtime connection."""

    reachable: bool
    postgis_version: str | None = None
    role: str | None = None
    role_bypasses_rls: bool | None = None
    error: str | None = None


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            str(settings.database_url),
            pool_size=settings.db_pool_size,
            pool_pre_ping=True,
            echo=settings.db_echo,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def probe(self) -> DatabaseProbe:
        """Check connectivity, PostGIS, and that the connected role cannot bypass RLS."""
        try:
            async with self.engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT postgis_lib_version() AS postgis, current_user AS role, "
                            "(r.rolsuper OR r.rolbypassrls) AS bypasses_rls "
                            "FROM pg_roles r WHERE r.rolname = current_user"
                        )
                    )
                ).one()
        except Exception as exc:  # report, never crash the probe
            return DatabaseProbe(reachable=False, error=type(exc).__name__)
        return DatabaseProbe(
            reachable=True,
            postgis_version=row.postgis,
            role=row.role,
            role_bypasses_rls=bool(row.bypasses_rls),
        )

    async def dispose(self) -> None:
        await self.engine.dispose()
