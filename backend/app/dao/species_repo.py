"""Persistence for the `species_content` cache table — see
docs/features/bird-info.md. Same dual-backend pattern as
`app/dao/pin_repo.py`: `InMemorySpeciesContentRepo` (default, and what every
test runs against) or `PostgresSpeciesContentRepo` (real persistence, once
`DATABASE_URL` is set).

Just the About-text cache — photos/audio keep their own existing caches
(`bird_photos.py` / `bird_audio.py`), not duplicated here.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool


class SpeciesContentRepo(Protocol):
    async def get(self, scientific_name: str) -> dict | None: ...
    async def upsert(self, scientific_name: str, about: str | None, about_source_url: str | None) -> None: ...


class InMemorySpeciesContentRepo:
    def __init__(self) -> None:
        self._by_name: dict[str, dict] = {}

    async def get(self, scientific_name: str) -> dict | None:
        return self._by_name.get(scientific_name)

    async def upsert(self, scientific_name: str, about: str | None, about_source_url: str | None) -> None:
        self._by_name[scientific_name] = {
            "about": about,
            "about_source_url": about_source_url,
            "fetched_at": datetime.now(timezone.utc),
        }


class PostgresSpeciesContentRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def get(self, scientific_name: str) -> dict | None:
        return await asyncio.to_thread(self._get_sync, scientific_name)

    async def upsert(self, scientific_name: str, about: str | None, about_source_url: str | None) -> None:
        await asyncio.to_thread(self._upsert_sync, scientific_name, about, about_source_url)

    def _get_sync(self, scientific_name: str) -> dict | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select about, about_source_url, fetched_at from species_content where scientific_name = %s",
                    (scientific_name,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def _upsert_sync(self, scientific_name: str, about: str | None, about_source_url: str | None) -> None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into species_content (scientific_name, about, about_source_url, fetched_at)
                    values (%s, %s, %s, now())
                    on conflict (scientific_name)
                        do update set about = excluded.about,
                                      about_source_url = excluded.about_source_url,
                                      fetched_at = excluded.fetched_at
                    """,
                    (scientific_name, about, about_source_url),
                )


def _build_default_repo() -> SpeciesContentRepo:
    if get_settings().database_url:
        return PostgresSpeciesContentRepo()
    return InMemorySpeciesContentRepo()


species_content_repo: SpeciesContentRepo = _build_default_repo()
