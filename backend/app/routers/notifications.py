"""The notification feed. See docs/features/pinned-birds.md.

    GET  /users/{user_id}/notifications?unread=true
    POST /users/{user_id}/notifications/read
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.models.notification import Notification
from app.services import notifications as notifications_service

router = APIRouter(tags=["notifications"])


class MarkReadRequest(BaseModel):
    ids: list[str] | None = None  # omitted marks the whole feed read


class MarkReadResponse(BaseModel):
    marked_read: int


@router.get("/users/{user_id}/notifications", response_model=list[Notification])
async def list_notifications(user_id: str, unread: bool = Query(default=False)):
    return await notifications_service.list_notifications(user_id, unread_only=unread)


@router.post("/users/{user_id}/notifications/read", response_model=MarkReadResponse)
async def mark_notifications_read(user_id: str, payload: MarkReadRequest = MarkReadRequest()):
    count = await notifications_service.mark_read(user_id, payload.ids)
    return MarkReadResponse(marked_read=count)
