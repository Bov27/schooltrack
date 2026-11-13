"""SQLAlchemy declarative base and tenant-context helpers.

Tables are created by Alembic migrations written in SQL (see docs/database); the ORM
models map onto them and are not used to generate DDL.
"""

import enum
import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, Enum, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Every timestamp column is TIMESTAMPTZ; keep Python datetimes timezone-aware.
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Map a Python enum onto an existing PostgreSQL enum type (created by migrations)."""
    return Enum(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda members: [m.value for m in members],
    )


async def set_current_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Transaction-local, so a pooled connection never carries it into another request."""
    await session.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"), {"value": str(user_id)}
    )


async def set_current_institution(session: AsyncSession, institution_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_institution_id', :value, true)"),
        {"value": str(institution_id)},
    )
