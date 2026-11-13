"""Append-only audit log. Entries are written in the caller's transaction, so an action
and its audit record commit or roll back together."""

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        institution_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | uuid.UUID | None,
        changes: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        await self.session.execute(
            text(
                "INSERT INTO audit_logs "
                "(institution_id, actor_user_id, action, entity_type, entity_id, changes, "
                "request_id) "
                "VALUES (:inst, :actor, :action, :etype, :eid, CAST(:changes AS jsonb), :rid)"
            ),
            {
                "inst": institution_id,
                "actor": actor_user_id,
                "action": action,
                "etype": entity_type,
                "eid": None if entity_id is None else str(entity_id),
                "changes": None if changes is None else _json(changes),
                "rid": request_id,
            },
        )


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str, sort_keys=True)
