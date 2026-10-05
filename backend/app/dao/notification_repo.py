"""Persistence for the notification feed — see docs/features/pinned-birds.md.
Same dual-backend pattern as `app/dao/observation_repo.py`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.notification import Notification


class NotificationRepo(Protocol):
    async def insert(
        self, user_id: str, kind: str, payload: dict[str, Any], dedupe_key: str | None
    ) -> Notification | None:
        """Returns `None` (not an error) if `dedupe_key` already exists for
        any user — the day's repeat sighting collapses to the first
        notification rather than spamming a second one. See
        docs/features/pinned-birds.md#match--notify.
        """
        ...

    async def list_for_user(self, user_id: str, unread_only: bool = False) -> list[Notification]: ...
    async def mark_read(self, user_id: str, ids: list[str] | None = None) -> int: ...
    async def unread_count(self, user_id: str) -> int: ...


class InMemoryNotificationRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, Notification] = {}
        self._dedupe_keys: set[str] = set()

    async def insert(
        self, user_id: str, kind: str, payload: dict[str, Any], dedupe_key: str | None
    ) -> Notification | None:
        if dedupe_key and dedupe_key in self._dedupe_keys:
            return None
        n = Notification(
            id=uuid.uuid4().hex,
            user_id=user_id,
            kind=kind,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        self._by_id[n.id] = n
        if dedupe_key:
            self._dedupe_keys.add(dedupe_key)
        return n

    async def list_for_user(self, user_id: str, unread_only: bool = False) -> list[Notification]:
        rows = [n for n in self._by_id.values() if n.user_id == user_id]
        if unread_only:
            rows = [n for n in rows if n.read_at is None]
        return sorted(rows, key=lambda n: n.created_at, reverse=True)

    async def mark_read(self, user_id: str, ids: list[str] | None = None) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        for n_id, n in list(self._by_id.items()):
            if n.user_id != user_id or n.read_at is not None:
                continue
            if ids is not None and n_id not in ids:
                continue
            self._by_id[n_id] = n.model_copy(update={"read_at": now})
            count += 1
        return count

    async def unread_count(self, user_id: str) -> int:
        return sum(1 for n in self._by_id.values() if n.user_id == user_id and n.read_at is None)


class PostgresNotificationRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def insert(
        self, user_id: str, kind: str, payload: dict[str, Any], dedupe_key: str | None
    ) -> Notification | None:
        return await asyncio.to_thread(self._insert_sync, user_id, kind, payload, dedupe_key)

    async def list_for_user(self, user_id: str, unread_only: bool = False) -> list[Notification]:
        return await asyncio.to_thread(self._list_for_user_sync, user_id, unread_only)

    async def mark_read(self, user_id: str, ids: list[str] | None = None) -> int:
        return await asyncio.to_thread(self._mark_read_sync, user_id, ids)

    async def unread_count(self, user_id: str) -> int:
        return await asyncio.to_thread(self._unread_count_sync, user_id)

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

    def _insert_sync(
        self, user_id: str, kind: str, payload: dict[str, Any], dedupe_key: str | None
    ) -> Notification | None:
        import json

        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                db_user_id = self._get_or_create_user_id(cur, user_id)
                cur.execute(
                    """
                    insert into notifications (user_id, kind, payload, dedupe_key)
                    values (%s, %s, %s, %s)
                    on conflict (dedupe_key) do nothing
                    returning *, %s as user_auth_id
                    """,
                    (db_user_id, kind, json.dumps(payload), dedupe_key, user_id),
                )
                row = cur.fetchone()
        return self._row_to_notification(row) if row else None

    def _list_for_user_sync(self, user_id: str, unread_only: bool) -> list[Notification]:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return []
                query = "select *, %s as user_auth_id from notifications where user_id = %s"
                params: list[Any] = [user_id, user_row["id"]]
                if unread_only:
                    query += " and read_at is null"
                query += " order by created_at desc"
                cur.execute(query, params)
                rows = cur.fetchall()
        return [self._row_to_notification(r) for r in rows]

    def _mark_read_sync(self, user_id: str, ids: list[str] | None) -> int:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return 0
                if ids:
                    id_uuids = [uuid.UUID(i) for i in ids]
                    cur.execute(
                        """
                        update notifications set read_at = now()
                        where user_id = %s and read_at is null and id = any(%s)
                        """,
                        (user_row["id"], id_uuids),
                    )
                else:
                    cur.execute(
                        "update notifications set read_at = now() where user_id = %s and read_at is null",
                        (user_row["id"],),
                    )
                return cur.rowcount

    def _unread_count_sync(self, user_id: str) -> int:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return 0
                cur.execute(
                    "select count(*) as n from notifications where user_id = %s and read_at is null",
                    (user_row["id"],),
                )
                return cur.fetchone()["n"]

    @staticmethod
    def _row_to_notification(row: dict[str, Any]) -> Notification:
        return Notification(
            id=str(row["id"]),
            user_id=row["user_auth_id"],
            kind=row["kind"],
            payload=row["payload"],
            read_at=row["read_at"],
            created_at=row["created_at"],
        )


def _build_default_repo() -> NotificationRepo:
    if get_settings().database_url:
        return PostgresNotificationRepo()
    return InMemoryNotificationRepo()


notification_repo: NotificationRepo = _build_default_repo()
