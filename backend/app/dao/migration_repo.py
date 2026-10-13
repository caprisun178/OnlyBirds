"""Persistence for the migration calendar — see
docs/features/migration-calendar.md §3. Same dual-backend pattern as
`app/dao/pin_repo.py`: `InMemoryMigrationRepo` (default, and what every test
runs against) or `PostgresMigrationRepo` (once `DATABASE_URL` is set).

A cell's *data* (`built_at` set) and its *status* are separate on purpose:
a stale cell being rebuilt is `status = 'building'` but still has its old
data, which keeps being served until the rebuild finishes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool

# A build that hasn't finished in this long is treated as abandoned (e.g.
# the process slept or restarted mid-build), so a new one may claim it.
ABANDONED_AFTER = timedelta(minutes=10)


class MigrationRepo(Protocol):
    async def get_calendar(self, cell_id: str) -> dict | None: ...
    async def claim_build(self, cell_id: str, center_lat: float, center_lng: float, radius_km: int) -> bool: ...
    async def save_build(self, cell_id: str, weekly_totals: dict[int, int], species: list[dict]) -> None: ...
    async def mark_failed(self, cell_id: str) -> None: ...
    async def get_data(self, cell_id: str) -> tuple[dict[int, int], list[dict]]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryMigrationRepo:
    def __init__(self) -> None:
        self._calendars: dict[str, dict] = {}
        self._totals: dict[str, dict[int, int]] = {}
        self._species: dict[str, list[dict]] = {}

    async def get_calendar(self, cell_id: str) -> dict | None:
        row = self._calendars.get(cell_id)
        return dict(row) if row else None

    async def claim_build(self, cell_id: str, center_lat: float, center_lng: float, radius_km: int) -> bool:
        row = self._calendars.get(cell_id)
        if row and row["status"] == "building" and _now() - row["updated_at"] < ABANDONED_AFTER:
            return False
        if row is None:
            row = {
                "cell_id": cell_id, "center_lat": center_lat, "center_lng": center_lng,
                "radius_km": radius_km, "total_obs": None, "built_at": None,
            }
            self._calendars[cell_id] = row
        row.update(status="building", updated_at=_now())
        return True

    async def save_build(self, cell_id: str, weekly_totals: dict[int, int], species: list[dict]) -> None:
        self._totals[cell_id] = dict(weekly_totals)
        self._species[cell_id] = [dict(s, weeks=dict(s["weeks"])) for s in species]
        self._calendars[cell_id].update(
            status="ready", total_obs=sum(weekly_totals.values()), built_at=_now(), updated_at=_now()
        )

    async def mark_failed(self, cell_id: str) -> None:
        if cell_id in self._calendars:
            self._calendars[cell_id].update(status="failed", updated_at=_now())

    async def get_data(self, cell_id: str) -> tuple[dict[int, int], list[dict]]:
        return dict(self._totals.get(cell_id, {})), list(self._species.get(cell_id, []))


class PostgresMigrationRepo:
    async def get_calendar(self, cell_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_calendar_sync, cell_id)

    async def claim_build(self, cell_id: str, center_lat: float, center_lng: float, radius_km: int) -> bool:
        return await asyncio.to_thread(self._claim_build_sync, cell_id, center_lat, center_lng, radius_km)

    async def save_build(self, cell_id: str, weekly_totals: dict[int, int], species: list[dict]) -> None:
        await asyncio.to_thread(self._save_build_sync, cell_id, weekly_totals, species)

    async def mark_failed(self, cell_id: str) -> None:
        await asyncio.to_thread(self._mark_failed_sync, cell_id)

    async def get_data(self, cell_id: str) -> tuple[dict[int, int], list[dict]]:
        return await asyncio.to_thread(self._get_data_sync, cell_id)

    # ---- sync internals, each run off the event loop via to_thread above --

    def _get_calendar_sync(self, cell_id: str) -> dict | None:
        with get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select * from migration_calendars where cell_id = %s", (cell_id,))
            return cur.fetchone()

    def _claim_build_sync(self, cell_id: str, center_lat: float, center_lng: float, radius_km: int) -> bool:
        # One atomic statement, so two visitors can't both start a build:
        # inserts a new cell, or flips an existing one to 'building' only if
        # it isn't already building (or that build looks abandoned).
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into migration_calendars (cell_id, center_lat, center_lng, radius_km, status, updated_at)
                values (%s, %s, %s, %s, 'building', now())
                on conflict (cell_id) do update
                    set status = 'building', updated_at = now()
                    where migration_calendars.status <> 'building'
                       or migration_calendars.updated_at < now() - %s
                returning cell_id
                """,
                (cell_id, center_lat, center_lng, radius_km, ABANDONED_AFTER),
            )
            return cur.fetchone() is not None

    def _save_build_sync(self, cell_id: str, weekly_totals: dict[int, int], species: list[dict]) -> None:
        # Replace the cell's data wholesale in one transaction, so a reader
        # never sees half an old build and half a new one.
        with get_pool().connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("delete from migration_calendar_weeks where cell_id = %s", (cell_id,))
            cur.execute("delete from migration_calendar_counts where cell_id = %s", (cell_id,))
            cur.executemany(
                "insert into migration_calendar_weeks (cell_id, week, total_obs) values (%s, %s, %s)",
                [(cell_id, week, total) for week, total in weekly_totals.items()],
            )
            cur.executemany(
                """
                insert into migration_calendar_counts
                    (cell_id, scientific_name, common_name, inat_taxon_id, week, obs_count)
                values (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (cell_id, s["scientific_name"], s.get("common_name"), s.get("inat_taxon_id"), week, count)
                    for s in species
                    for week, count in s["weeks"].items()
                    if count
                ],
            )
            cur.execute(
                """
                update migration_calendars
                set status = 'ready', total_obs = %s, built_at = now(), updated_at = now()
                where cell_id = %s
                """,
                (sum(weekly_totals.values()), cell_id),
            )

    def _mark_failed_sync(self, cell_id: str) -> None:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update migration_calendars set status = 'failed', updated_at = now() where cell_id = %s",
                (cell_id,),
            )

    def _get_data_sync(self, cell_id: str) -> tuple[dict[int, int], list[dict]]:
        with get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select week, total_obs from migration_calendar_weeks where cell_id = %s", (cell_id,))
            totals = {r["week"]: r["total_obs"] for r in cur.fetchall()}
            cur.execute(
                """
                select scientific_name, common_name, inat_taxon_id, week, obs_count
                from migration_calendar_counts where cell_id = %s
                """,
                (cell_id,),
            )
            by_name: dict[str, dict[str, Any]] = {}
            for r in cur.fetchall():
                sp = by_name.setdefault(r["scientific_name"], {
                    "scientific_name": r["scientific_name"],
                    "common_name": r["common_name"],
                    "inat_taxon_id": r["inat_taxon_id"],
                    "weeks": {},
                })
                sp["weeks"][r["week"]] = r["obs_count"]
        return totals, list(by_name.values())


def _build_default_repo() -> MigrationRepo:
    if get_settings().database_url:
        return PostgresMigrationRepo()
    return InMemoryMigrationRepo()


# Single shared instance for the process lifetime.
migration_repo: MigrationRepo = _build_default_repo()
