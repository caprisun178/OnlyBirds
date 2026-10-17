"""Persistence for the Bird Info page — see docs/features/bird-info.md.
Same dual-backend pattern as `app/dao/pin_repo.py`: `InMemorySpeciesRepo`
(default, and what every test runs against) or `PostgresSpeciesRepo` (real
persistence, once `DATABASE_URL` is set).

Two responsibilities, both small enough to share one file per the feature
page's own layering table: caching Wikipedia-sourced text
(`species_content`), and looking up a `species` row's taxonomy by
`scientific_name` for the profile header. That second one only ever
returns `common_name` in practice today — `observation_repo.py`'s
get-or-create never populates `taxon_group`/family data, so a profile's
`family` field is `None` far more often than not; the page already treats
that as a normal, not-an-error outcome (see bird-info.md).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.species import SpeciesContent


class SpeciesRepo(Protocol):
    async def get_content(self, scientific_name: str) -> SpeciesContent | None: ...
    async def upsert_content(self, content: SpeciesContent) -> SpeciesContent: ...
    async def get_taxonomy(self, scientific_name: str) -> dict | None: ...


class InMemorySpeciesRepo:
    def __init__(self) -> None:
        self._content: dict[str, SpeciesContent] = {}
        self._taxonomy: dict[str, dict] = {}

    async def get_content(self, scientific_name: str) -> SpeciesContent | None:
        return self._content.get(scientific_name.lower())

    async def upsert_content(self, content: SpeciesContent) -> SpeciesContent:
        self._content[content.scientific_name.lower()] = content
        return content

    async def get_taxonomy(self, scientific_name: str) -> dict | None:
        return self._taxonomy.get(scientific_name.lower())

    def _seed_taxonomy(self, scientific_name: str, common_name: str | None, family: str | None = None) -> None:
        """Test-only helper — the in-memory backend has no `species` table
        to read from, so tests that want `get_taxonomy()` to find something
        seed it directly instead of going through a real insert."""
        self._taxonomy[scientific_name.lower()] = {
            "scientific_name": scientific_name,
            "common_name": common_name,
            "family": family,
        }


class PostgresSpeciesRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def get_content(self, scientific_name: str) -> SpeciesContent | None:
        return await asyncio.to_thread(self._get_content_sync, scientific_name)

    async def upsert_content(self, content: SpeciesContent) -> SpeciesContent:
        return await asyncio.to_thread(self._upsert_content_sync, content)

    async def get_taxonomy(self, scientific_name: str) -> dict | None:
        return await asyncio.to_thread(self._get_taxonomy_sync, scientific_name)

    def _get_content_sync(self, scientific_name: str) -> SpeciesContent | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select * from species_content where lower(scientific_name) = lower(%s)",
                    (scientific_name,),
                )
                row = cur.fetchone()
        return self._row_to_content(row) if row else None

    def _upsert_content_sync(self, content: SpeciesContent) -> SpeciesContent:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into species_content
                        (scientific_name, about, about_source_url, sex_differences, migration, habitat, fetched_at)
                    values (%s, %s, %s, %s, %s, %s, now())
                    on conflict (scientific_name) do update set
                        about = excluded.about,
                        about_source_url = excluded.about_source_url,
                        sex_differences = excluded.sex_differences,
                        migration = excluded.migration,
                        habitat = excluded.habitat,
                        fetched_at = excluded.fetched_at
                    returning *
                    """,
                    (
                        content.scientific_name,
                        content.about,
                        content.about_source_url,
                        content.sex_differences,
                        content.migration,
                        content.habitat,
                    ),
                )
                row = cur.fetchone()
        return self._row_to_content(row)

    def _get_taxonomy_sync(self, scientific_name: str) -> dict | None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select scientific_name, common_name, taxon_group from species"
                    " where lower(scientific_name) = lower(%s)",
                    (scientific_name,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "scientific_name": row["scientific_name"],
            "common_name": row["common_name"],
            "family": row["taxon_group"],
        }

    @staticmethod
    def _row_to_content(row: dict) -> SpeciesContent:
        return SpeciesContent(
            scientific_name=row["scientific_name"],
            about=row["about"],
            about_source_url=row["about_source_url"],
            sex_differences=row["sex_differences"],
            migration=row["migration"],
            habitat=row["habitat"],
            fetched_at=row["fetched_at"],
        )


def _build_default_repo() -> SpeciesRepo:
    if get_settings().database_url:
        return PostgresSpeciesRepo()
    return InMemorySpeciesRepo()


species_repo: SpeciesRepo = _build_default_repo()
