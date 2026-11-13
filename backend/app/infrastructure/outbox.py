"""Transactional outbox (ADR-005): side effects are recorded as rows in the same
transaction as the business change, and delivered later by the worker. If the
transaction rolls back, the message disappears with it; if it commits, delivery is
guaranteed (at least once)."""

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def enqueue(
    session: AsyncSession, institution_id: uuid.UUID, topic: str, payload: dict[str, Any]
) -> None:
    await session.execute(
        text(
            "INSERT INTO outbox_events (institution_id, topic, payload) "
            "VALUES (:inst, :topic, CAST(:payload AS jsonb))"
        ),
        {"inst": institution_id, "topic": topic, "payload": json.dumps(payload, default=str)},
    )
