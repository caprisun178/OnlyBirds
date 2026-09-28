"""Persistence for user profiles (the `users` table).

Same shape as observation_repo.py: an in-memory repo when DATABASE_URL is
unset (tests), a Postgres repo otherwise. The external id ('u1') is
`auth_provider_id`; `User.id` is the internal uuid as text. A `users` row may
already exist because logging an observation creates one on the fly, so
`create` is an upsert.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.user import User, UserCreate, UserUpdate


class UserRepo(Protocol):
    async def get_by_auth_id(self, auth_id: str) -> User | None: ...
    async def get_by_username(self, username: str) -> User | None: ...
    async def create(self, payload: UserCreate) -> User: ...
    async def update(self, auth_id: str, changes: UserUpdate) -> User | None: ...


class InMemoryUserRepo:
    def __init__(self) -> None:
        self._by_auth_id: dict[str, User] = {}

    async def get_by_auth_id(self, auth_id: str) -> User | None:
        return self._by_auth_id.get(auth_id)

    async def get_by_username(self, username: str) -> User | None:
        for user in self._by_auth_id.values():
            if user.username == username:
                return user
        return None

    async def create(self, payload: UserCreate) -> User:
        existing = self._by_auth_id.get(payload.auth_provider_id)
        if existing:
            # Keep an already-chosen username; only fill blanks.
            updates = {}
            if existing.username is None and payload.username:
                updates["username"] = payload.username
            if existing.email is None and payload.email:
                updates["email"] = payload.email
            user = existing.model_copy(update=updates)
        else:
            user = User(
                id=uuid.uuid4().hex,
                auth_provider_id=payload.auth_provider_id,
                username=payload.username,
                email=payload.email,
            )
        self._by_auth_id[user.auth_provider_id] = user
        return user

    async def update(self, auth_id: str, changes: UserUpdate) -> User | None:
        existing = self._by_auth_id.get(auth_id)
        if existing is None:
            return None
        user = existing.model_copy(update=changes.model_dump(exclude_none=True))
        self._by_auth_id[auth_id] = user
        return user


_COLUMNS = "id, auth_provider_id, username, avatar_url, default_region, email"


class PostgresUserRepo:
    """Real persistence against Postgres (Neon). Sync queries run through
    asyncio.to_thread, same as PostgresObservationRepo."""

    async def get_by_auth_id(self, auth_id: str) -> User | None:
        return await asyncio.to_thread(self._get_sync, "auth_provider_id", auth_id)

    async def get_by_username(self, username: str) -> User | None:
        return await asyncio.to_thread(self._get_sync, "username", username)

    async def create(self, payload: UserCreate) -> User:
        return await asyncio.to_thread(self._create_sync, payload)

    async def update(self, auth_id: str, changes: UserUpdate) -> User | None:
        return await asyncio.to_thread(self._update_sync, auth_id, changes)

    # ---- sync internals ---------------------------------------------------

    @staticmethod
    def _row_to_user(row) -> User:
        return User(
            id=str(row["id"]),
            auth_provider_id=row["auth_provider_id"],
            username=row["username"],
            avatar_url=row["avatar_url"],
            default_region=row["default_region"],
            email=row["email"],
        )

    def _get_sync(self, column: str, value: str) -> User | None:
        # `column` is only ever one of two fixed strings from this class.
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"select {_COLUMNS} from users where {column} = %s", (value,))
                row = cur.fetchone()
        return self._row_to_user(row) if row else None

    def _create_sync(self, payload: UserCreate) -> User:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    insert into users (auth_provider_id, username, email)
                    values (%s, %s, %s)
                    on conflict (auth_provider_id) do update set
                        username = coalesce(users.username, excluded.username),
                        email    = coalesce(users.email, excluded.email)
                    returning {_COLUMNS}
                    """,
                    (payload.auth_provider_id, payload.username, payload.email),
                )
                row = cur.fetchone()
        return self._row_to_user(row)

    def _update_sync(self, auth_id: str, changes: UserUpdate) -> User | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    update users set
                        avatar_url     = coalesce(%s, avatar_url),
                        default_region = coalesce(%s, default_region)
                    where auth_provider_id = %s
                    returning {_COLUMNS}
                    """,
                    (changes.avatar_url, changes.default_region, auth_id),
                )
                row = cur.fetchone()
        return self._row_to_user(row) if row else None


def _build_default_repo() -> UserRepo:
    if get_settings().database_url:
        return PostgresUserRepo()
    return InMemoryUserRepo()


# Single shared instance for the process lifetime.
user_repo: UserRepo = _build_default_repo()