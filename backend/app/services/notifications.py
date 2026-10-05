"""Notification feed — see docs/features/pinned-birds.md. Generic over
`kind`: Pinned Birds is the first caller (`pin_hit`); Stickers (planned)
will be the second (`sticker_awarded`), reusing this same feed.
"""

from __future__ import annotations

from app.dao.notification_repo import notification_repo
from app.models.notification import Notification


async def list_notifications(user_id: str, unread_only: bool = False) -> list[Notification]:
    """Newest first."""
    return await notification_repo.list_for_user(user_id, unread_only)


async def unread_count(user_id: str) -> int:
    return await notification_repo.unread_count(user_id)


async def mark_read(user_id: str, ids: list[str] | None = None) -> int:
    """`ids` omitted marks the whole feed read; given, only those. Returns
    how many rows actually changed (already-read rows are a no-op, not an
    error).
    """
    return await notification_repo.mark_read(user_id, ids)
