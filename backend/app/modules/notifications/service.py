"""In-app notifications for the current user (any institution)."""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.infrastructure.orm import set_current_user

_COLUMNS = (
    "id, institution_id, kind, title, body, payload, status::text AS status, "
    "created_at, sent_at, read_at"
)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_mine(
        self, user_id: uuid.UUID, *, unread_only: bool, limit: int
    ) -> list[dict[str, Any]]:
        await set_current_user(self.session, user_id)
        rows = (
            await self.session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM notifications "
                    "WHERE recipient_user_id = :user AND status <> 'CANCELLED' "
                    "AND (NOT :unread OR read_at IS NULL) "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"user": user_id, "unread": unread_only, "limit": limit},
            )
        ).all()
        return [dict(r._mapping) for r in rows]

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> dict[str, Any]:
        await set_current_user(self.session, user_id)
        row = (
            await self.session.execute(
                text(
                    "UPDATE notifications SET read_at = coalesce(read_at, now()) "
                    "WHERE id = :id AND recipient_user_id = :user "
                    f"RETURNING {_COLUMNS}"
                ),
                {"id": notification_id, "user": user_id},
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Notification not found")
        await self.session.commit()
        return dict(row._mapping)
