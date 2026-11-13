import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, SessionDep
from app.api.errors import error_responses
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    kind: str
    title: str
    body: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
    sent_at: datetime | None
    read_at: datetime | None


@router.get("", response_model=list[NotificationOut], responses=error_responses(401))
async def list_notifications(
    user: CurrentUserDep,
    session: SessionDep,
    unread: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[NotificationOut]:
    rows = await NotificationService(session).list_mine(user.id, unread_only=unread, limit=limit)
    return [NotificationOut(**r) for r in rows]


@router.post(
    "/{notification_id}/read", response_model=NotificationOut, responses=error_responses(401, 404)
)
async def mark_read(
    notification_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> NotificationOut:
    return NotificationOut(**await NotificationService(session).mark_read(user.id, notification_id))
