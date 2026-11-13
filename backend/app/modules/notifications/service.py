"""In-app notifications for the current user (any institution)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.infrastructure.orm import set_current_user
from app.modules.notifications.repository import NotificationRepository


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def list_mine(
        self, user_id: uuid.UUID, *, unread_only: bool, limit: int
    ) -> list[dict[str, Any]]:
        await set_current_user(self.session, user_id)
        return await self.repo.list_for(user_id, unread_only=unread_only, limit=limit)

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> dict[str, Any]:
        await set_current_user(self.session, user_id)
        notification = await self.repo.mark_read(user_id, notification_id)
        if notification is None:
            raise NotFoundError("Notification not found")
        await self.session.commit()
        return notification
