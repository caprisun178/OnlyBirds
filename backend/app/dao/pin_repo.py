"""Persistence for Pinned Birds — see docs/features/pinned-birds.md. Same
dual-backend pattern as `app/dao/observation_repo.py`: `InMemoryPinRepo`
(default, and what every test runs against) or `PostgresPinRepo` (real
persistence, once `DATABASE_URL` is set).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.pin import PinnedBird


def region_contains(pin_region: str, obs_region: str) -> bool:
    """`world` matches everything; otherwise a prefix match — `US-WA`
    contains `US-WA-033` but not `US-OR`. Mirrors the SQL match query in
    `PostgresPinRepo.find_matches` exactly, so both backends agree.
    """
    return pin_region == "world" or obs_region == pin_region or obs_region.startswith(pin_region + "-")


class PinRepo(Protocol):
    async def list_for_user(self, user_id: str) -> list[PinnedBird]: ...
    async def upsert(self, user_id: str, scientific_name: str, common_name: str | None, region: str) -> PinnedBird: ...
    async def update_region(self, user_id: str, scientific_name: str, region: str) -> PinnedBird | None: ...
    async def delete(self, user_id: str, scientific_name: str) -> bool: ...
    async def find_matches(self, scientific_name: str, obs_region: str, exclude_user_id: str) -> list[PinnedBird]: ...


class InMemoryPinRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, PinnedBird] = {}

    def _find(self, user_id: str, scientific_name: str) -> PinnedBird | None:
        name = scientific_name.lower()
        for pin in self._by_id.values():
            if pin.user_id == user_id and pin.scientific_name.lower() == name:
                return pin
        return None

    async def list_for_user(self, user_id: str) -> list[PinnedBird]:
        return [p for p in self._by_id.values() if p.user_id == user_id]

    async def upsert(self, user_id: str, scientific_name: str, common_name: str | None, region: str) -> PinnedBird:
        existing = self._find(user_id, scientific_name)
        if existing:
            updated = existing.model_copy(update={"region": region, "common_name": common_name or existing.common_name})
            self._by_id[updated.id] = updated
            return updated
        pin = PinnedBird(
            id=uuid.uuid4().hex,
            user_id=user_id,
            scientific_name=scientific_name,
            common_name=common_name,
            region=region,
        )
        self._by_id[pin.id] = pin
        return pin

    async def update_region(self, user_id: str, scientific_name: str, region: str) -> PinnedBird | None:
        existing = self._find(user_id, scientific_name)
        if existing is None:
            return None
        updated = existing.model_copy(update={"region": region})
        self._by_id[updated.id] = updated
        return updated

    async def delete(self, user_id: str, scientific_name: str) -> bool:
        existing = self._find(user_id, scientific_name)
        if existing is None:
            return False
        del self._by_id[existing.id]
        return True

    async def find_matches(self, scientific_name: str, obs_region: str, exclude_user_id: str) -> list[PinnedBird]:
        name = scientific_name.lower()
        return [
            p
            for p in self._by_id.values()
            if p.scientific_name.lower() == name
            and p.user_id != exclude_user_id
            and region_contains(p.region, obs_region)
        ]


class PostgresPinRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def list_for_user(self, user_id: str) -> list[PinnedBird]:
        return await asyncio.to_thread(self._list_for_user_sync, user_id)

    async def upsert(self, user_id: str, scientific_name: str, common_name: str | None, region: str) -> PinnedBird:
        return await asyncio.to_thread(self._upsert_sync, user_id, scientific_name, common_name, region)

    async def update_region(self, user_id: str, scientific_name: str, region: str) -> PinnedBird | None:
        return await asyncio.to_thread(self._update_region_sync, user_id, scientific_name, region)

    async def delete(self, user_id: str, scientific_name: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, user_id, scientific_name)

    async def find_matches(self, scientific_name: str, obs_region: str, exclude_user_id: str) -> list[PinnedBird]:
        return await asyncio.to_thread(self._find_matches_sync, scientific_name, obs_region, exclude_user_id)

    # ---- sync internals, each run off the event loop via to_thread above --

    @staticmethod
    def _get_or_create_user_id(cur, auth_provider_id: str) -> uuid.UUID:
        cur.execute(
            """
            insert into users (auth_provider_id) values (%s)
            on conflict (auth_provider_id)
                do update set auth_provider_id = excluded.auth_provider_id
            returning id
            """,
            (auth_provider_id,),
        )
        return cur.fetchone()["id"]

    def _list_for_user_sync(self, user_id: str) -> list[PinnedBird]:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return []
                cur.execute(
                    "select *, %s as user_auth_id from pinned_birds where user_id = %s",
                    (user_id, user_row["id"]),
                )
                rows = cur.fetchall()
        return [self._row_to_pin(r) for r in rows]

    def _upsert_sync(self, user_id: str, scientific_name: str, common_name: str | None, region: str) -> PinnedBird:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                db_user_id = self._get_or_create_user_id(cur, user_id)
                cur.execute(
                    """
                    insert into pinned_birds (user_id, scientific_name, common_name, region)
                    values (%s, %s, %s, %s)
                    on conflict (user_id, scientific_name)
                        do update set region = excluded.region,
                                      common_name = coalesce(excluded.common_name, pinned_birds.common_name)
                    returning *, %s as user_auth_id
                    """,
                    (db_user_id, scientific_name, common_name, region, user_id),
                )
                row = cur.fetchone()
        return self._row_to_pin(row)

    def _update_region_sync(self, user_id: str, scientific_name: str, region: str) -> PinnedBird | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return None
                cur.execute(
                    """
                    update pinned_birds set region = %s
                    where user_id = %s and scientific_name = %s
                    returning *, %s as user_auth_id
                    """,
                    (region, user_row["id"], scientific_name, user_id),
                )
                row = cur.fetchone()
        return self._row_to_pin(row) if row else None

    def _delete_sync(self, user_id: str, scientific_name: str) -> bool:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return False
                cur.execute(
                    "delete from pinned_birds where user_id = %s and scientific_name = %s",
                    (user_row["id"], scientific_name),
                )
                return cur.rowcount > 0

    def _find_matches_sync(self, scientific_name: str, obs_region: str, exclude_user_id: str) -> list[PinnedBird]:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (exclude_user_id,))
                observer_row = cur.fetchone()
                observer_id = observer_row["id"] if observer_row else None
                cur.execute(
                    """
                    select p.*, u.auth_provider_id as user_auth_id
                    from pinned_birds p
                    join users u on u.id = p.user_id
                    where lower(p.scientific_name) = lower(%s)
                      and p.user_id is distinct from %s
                      and ( p.region = 'world'
                            or %s = p.region
                            or %s like p.region || '-%%' )
                    """,
                    (scientific_name, observer_id, obs_region, obs_region),
                )
                rows = cur.fetchall()
        return [self._row_to_pin(r) for r in rows]

    @staticmethod
    def _row_to_pin(row: dict[str, Any]) -> PinnedBird:
        return PinnedBird(
            id=str(row["id"]),
            user_id=row["user_auth_id"],
            scientific_name=row["scientific_name"],
            common_name=row["common_name"],
            region=row["region"],
            created_at=row["created_at"],
        )


def _build_default_repo() -> PinRepo:
    if get_settings().database_url:
        return PostgresPinRepo()
    return InMemoryPinRepo()


pin_repo: PinRepo = _build_default_repo()
