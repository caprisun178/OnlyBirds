"""In-memory sticker catalog and award ledger.

The repository mirrors the future Postgres tables so the service does not need
to change when migrations replace this prototype store.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.sticker import Group, Sticker, UserSticker


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class InMemoryStickerRepo:
    def __init__(self) -> None:
        """Load the sticker catalog and prepare an empty award ledger."""
        self._stickers = self._load_stickers()
        self._groups = self._load_groups()
        self._awards: dict[tuple[str, str], UserSticker] = {}

    @staticmethod
    def _load_stickers() -> dict[str, Sticker]:
        """Read and validate sticker definitions from the JSON fixture."""
        rows = json.loads((DATA_DIR / "stickers.json").read_text())
        return {row["code"]: Sticker.model_validate(row) for row in rows}

    @staticmethod
    def _load_groups() -> dict[str, Group]:
        """Read and validate group definitions from the JSON fixture."""
        rows = json.loads((DATA_DIR / "groups.json").read_text())
        return {row["code"]: Group.model_validate(row) for row in rows}

    def list_stickers(self) -> list[Sticker]:
        """Return the catalog in rarity and display order."""
        return sorted(
            self._stickers.values(), key=lambda sticker: (sticker.rarity, sticker.sort_order)
        )

    def get_group(self, code: str) -> Group | None:
        """Find a group definition by its stable catalog code."""
        return self._groups.get(code)

    def list_awards(self, user_id: str) -> list[UserSticker]:
        """Return all sticker awards belonging to one user."""
        return [award for award in self._awards.values() if award.user_id == user_id]

    def award(
        self, user_id: str, sticker_code: str, observation_id: str | None = None
    ) -> UserSticker:
        """Create an award once and return the existing award on repeats."""
        key = (user_id, sticker_code)
        existing = self._awards.get(key)
        if existing:
            return existing
        award = UserSticker(
            user_id=user_id,
            sticker_code=sticker_code,
            awarded_at=datetime.now(timezone.utc),
            observation_id=observation_id,
        )
        self._awards[key] = award
        return award


sticker_repo = InMemoryStickerRepo()