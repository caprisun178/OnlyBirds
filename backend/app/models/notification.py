"""The notification feed — see docs/features/pinned-birds.md. Shared by
future features (Stickers is the next planned one) via `kind`.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NotificationKind = Literal["pin_hit", "sticker_awarded"]


class Notification(BaseModel):
    id: str | None = None
    user_id: str
    kind: NotificationKind
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime | None = None
