"""Sticker catalog and award ledger.

The **catalog** (stickers and groups) is our own data, checked into the repo
as JSON fixtures and loaded into memory at startup. It changes with the code,
so it doesn't need a table.

The **awards** (who has earned what) are user data and must survive
restarts and redeploys. Same split as observation_repo.py / pin_repo.py:
`PostgresStickerRepo` keeps them in the `user_stickers` table
(migrations/0009_user_stickers.sql) when DATABASE_URL is set;
`InMemoryStickerRepo` keeps them in a dict otherwise (tests, local dev
without a database).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
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
        rarity_order = {"common": 0, "uncommon": 1, "rare": 2}
        return sorted(
            self._stickers.values(),
            key=lambda sticker: (rarity_order[sticker.rarity], sticker.sort_order, sticker.code),
        )

    def get_group(self, code: str) -> Group | None:
        """Find a group definition by its stable catalog code."""
        return self._groups.get(code)

    def get_sticker(self, code: str) -> Sticker | None:
        """Find a sticker definition by its stable catalog code."""
        return self._stickers.get(code)

    async def list_awards(self, user_id: str) -> list[UserSticker]:
        """Return all sticker awards belonging to one user."""
        return [award for award in self._awards.values() if award.user_id == user_id]

    async def award(
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


class PostgresStickerRepo(InMemoryStickerRepo):
    """Catalog from the JSON fixtures (inherited); awards in `user_stickers`.
    Sync queries run through asyncio.to_thread, same as PostgresPinRepo."""

    async def list_awards(self, user_id: str) -> list[UserSticker]:
        return await asyncio.to_thread(self._list_awards_sync, user_id)

    async def award(
        self, user_id: str, sticker_code: str, observation_id: str | None = None
    ) -> UserSticker:
        return await asyncio.to_thread(self._award_sync, user_id, sticker_code, observation_id)

    def _list_awards_sync(self, user_id: str) -> list[UserSticker]:
        with get_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select s.sticker_code, s.awarded_at, s.observation_id
                    from user_stickers s
                    join users u on u.id = s.user_id
                    where u.auth_provider_id = %s
                    order by s.awarded_at
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
        return [self._row_to_award(user_id, r) for r in rows]

    def _award_sync(self, user_id: str, sticker_code: str, observation_id: str | None) -> UserSticker:
        with get_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get-or-create the users row, same as the other repos: a
                # user's first lifer can arrive before anything else made one.
                cur.execute(
                    """
                    insert into users (auth_provider_id) values (%s)
                    on conflict (auth_provider_id)
                        do update set auth_provider_id = excluded.auth_provider_id
                    returning id
                    """,
                    (user_id,),
                )
                db_user_id = cur.fetchone()["id"]
                # The primary key (user_id, sticker_code) makes a repeat a
                # no-op; either way, return the row that's there.
                cur.execute(
                    """
                    insert into user_stickers (user_id, sticker_code, observation_id)
                    values (%s, %s, %s)
                    on conflict (user_id, sticker_code) do nothing
                    """,
                    (db_user_id, sticker_code, observation_id),
                )
                cur.execute(
                    """
                    select sticker_code, awarded_at, observation_id
                    from user_stickers where user_id = %s and sticker_code = %s
                    """,
                    (db_user_id, sticker_code),
                )
                row = cur.fetchone()
        return self._row_to_award(user_id, row)

    @staticmethod
    def _row_to_award(user_id: str, row: dict) -> UserSticker:
        return UserSticker(
            user_id=user_id,
            sticker_code=row["sticker_code"],
            awarded_at=row["awarded_at"],
            observation_id=str(row["observation_id"]) if row["observation_id"] else None,
        )


def _build_default_repo() -> InMemoryStickerRepo:
    if get_settings().database_url:
        return PostgresStickerRepo()
    return InMemoryStickerRepo()


sticker_repo = _build_default_repo()