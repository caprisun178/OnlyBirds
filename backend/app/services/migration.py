"""Business logic for the migration calendar — docs/features/migration-calendar.md.

A location snaps to a 0.5° grid cell; each cell's calendar is built once from
iNaturalist (~106 paced requests, about 2 minutes) in the background, stored
(`app/dao/migration_repo.py`), and shared by everyone in that cell. The
classification itself lives in `migration_patterns.py` (pure functions).
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta, timezone

from app.dao import bird_photos, inaturalist
from app.dao.migration_repo import migration_repo
from app.models.migration import (
    CalendarResponse,
    CalendarSpecies,
    NowResponse,
    NowSpecies,
)
from app.services import migration_patterns as patterns

log = logging.getLogger(__name__)

CELL_SIZE_DEG = 0.5
RADIUS_KM = 40
STALE_AFTER = timedelta(days=90)
REQUEST_SPACING_S = 1.0  # iNaturalist asks API clients to stay around 1 request/second
LIMITED_BELOW = 10_000  # whole-year bird observations — tuned on real cells, see doc §6
INSUFFICIENT_BELOW = 300
NOW_LIST_LIMIT = 15  # per list (arriving / peak / leaving)

# One build at a time per process, so concurrent first visits to different
# cells can't multiply the request rate against iNaturalist.
_build_lock = asyncio.Lock()


def cell_for(lat: float, lng: float) -> tuple[str, float, float]:
    """`(cell_id, center_lat, center_lng)` for the grid cell containing a point."""
    south = math.floor(lat / CELL_SIZE_DEG) * CELL_SIZE_DEG
    west = math.floor(lng / CELL_SIZE_DEG) * CELL_SIZE_DEG
    half = CELL_SIZE_DEG / 2
    return f"{south:g}:{west:g}", south + half, west + half


def current_week(today: date | None = None) -> int:
    """ISO week of the year, folded to 1–52 like the stored data."""
    return min((today or date.today()).isocalendar().week, patterns.WEEKS)


def _data_quality(total_obs: int) -> str:
    if total_obs < INSUFFICIENT_BELOW:
        return "insufficient"
    if total_obs < LIMITED_BELOW:
        return "limited"
    return "good"


def _is_stale(calendar: dict) -> bool:
    built_at = calendar.get("built_at")
    return built_at is not None and datetime.now(timezone.utc) - built_at > STALE_AFTER


async def build_cell(cell_id: str, center_lat: float, center_lng: float) -> None:
    """Fetches all 53 weeks (totals + species counts), then saves in one go.
    Run as a background task after `claim_build()` succeeded. Any failure
    marks the cell `failed`, so the next visit retries."""
    async with _build_lock:
        try:
            totals: dict[int, int] = {}
            species: dict[str, dict] = {}
            for week in range(1, 54):
                totals[week] = await inaturalist.count_weekly_observations(center_lat, center_lng, RADIUS_KM, week)
                await asyncio.sleep(REQUEST_SPACING_S)
                rows = await inaturalist.get_weekly_species_counts(center_lat, center_lng, RADIUS_KM, week)
                await asyncio.sleep(REQUEST_SPACING_S)
                for row in rows:
                    taxon = row.get("taxon") or {}
                    name = taxon.get("name")
                    if not name or taxon.get("rank") not in (None, "species"):
                        continue  # species only — subspecies/hybrids would double-count
                    sp = species.setdefault(name, {
                        "scientific_name": name,
                        "common_name": taxon.get("preferred_common_name"),
                        "inat_taxon_id": taxon.get("id"),
                        "weeks": {},
                    })
                    sp["weeks"][week] = row.get("count", 0)
            await migration_repo.save_build(cell_id, totals, list(species.values()))
        except Exception:
            log.exception("migration calendar build failed for cell %s", cell_id)
            await migration_repo.mark_failed(cell_id)


async def ensure_cell(lat: float, lng: float) -> tuple[str, dict | None, tuple | None]:
    """Looks up the cell for a point. Returns `(cell_id, calendar_or_None,
    build_args_or_None)`: `build_args` is set when the caller should start
    `build_cell(*build_args)` in the background — no data yet, or stale data."""
    cell_id, center_lat, center_lng = cell_for(lat, lng)
    calendar = await migration_repo.get_calendar(cell_id)
    needs_build = calendar is None or calendar.get("built_at") is None or _is_stale(calendar)
    if needs_build:
        # Refused when another request's build is already running (unless
        # that one looks abandoned) — then we just report "building".
        needs_build = await migration_repo.claim_build(cell_id, center_lat, center_lng, RADIUS_KM)
        calendar = await migration_repo.get_calendar(cell_id)
    build_args = (cell_id, center_lat, center_lng) if needs_build else None
    has_data = calendar is not None and calendar.get("built_at") is not None
    return cell_id, (calendar if has_data else None), build_args


async def _classified(cell_id: str, southern: bool) -> list[dict]:
    totals_by_week, species = await migration_repo.get_data(cell_id)
    totals = patterns.fold_weeks(totals_by_week)
    min_obs = patterns.min_obs_for(sum(totals))
    out = []
    for sp in species:
        counts = patterns.fold_weeks(sp["weeks"])
        relative = patterns.relative_weekly(counts, totals)
        if not any(relative):
            continue
        out.append({
            "scientific_name": sp["scientific_name"],
            "common_name": sp.get("common_name"),
            "pattern": patterns.classify(counts, relative, southern=southern, min_obs=min_obs),
            "weekly": relative,
        })
    return out


def _first_week(weekly: list[float]) -> int:
    """For ordering a bar chart: the week a species usually shows up."""
    present = [r >= patterns.PRESENT_FRACTION for r in weekly]
    if all(present):
        return -1
    # Start of its first run after an absence, so a winter visitor present
    # in both January and December sorts by its autumn arrival.
    for i in range(patterns.WEEKS):
        if present[i] and not present[i - 1]:
            return i
    return 0


async def calendar(cell_id: str, calendar_row: dict, lat: float) -> CalendarResponse:
    rows = await _classified(cell_id, southern=lat < 0)
    order = {"passage": 0, "summer": 1, "winter": 2, "resident": 3, "irregular": 4}
    rows.sort(key=lambda r: (order[r["pattern"]], _first_week(r["weekly"]), r["common_name"] or r["scientific_name"]))
    return CalendarResponse(
        cell_id=cell_id,
        built_at=calendar_row["built_at"],
        refreshing=_is_stale(calendar_row) or calendar_row["status"] == "building",
        data_quality=_data_quality(calendar_row.get("total_obs") or 0),
        total_obs=calendar_row.get("total_obs") or 0,
        species=[CalendarSpecies(**r) for r in rows],
    )


async def now(
    cell_id: str, calendar_row: dict, lat: float, week: int, seen_names: set[str] | None
) -> NowResponse:
    rows = await _classified(cell_id, southern=lat < 0)
    lists: dict[str, list[dict]] = {"arriving": [], "peak": [], "leaving": []}
    for r in rows:
        if r["pattern"] in ("resident", "irregular"):
            continue  # not migrating, or too little data to say
        state = patterns.movement(r["weekly"], week, r["pattern"])
        if state:
            lists[state].append(r)
    i = week - 1
    for key in lists:
        lists[key].sort(key=lambda r: r["weekly"][i], reverse=True)
        lists[key] = lists[key][:NOW_LIST_LIMIT]

    async def hydrate(r: dict) -> NowSpecies:
        photo = await bird_photos.get_stock_photo(r["scientific_name"], r["common_name"] or r["scientific_name"])
        return NowSpecies(
            **r,
            photo_url=photo.get("photo_url"),
            photo_attribution=photo.get("attribution"),
            on_life_list=(r["scientific_name"].lower() in seen_names) if seen_names is not None else None,
        )

    hydrated = {key: await asyncio.gather(*(hydrate(r) for r in rows_)) for key, rows_ in lists.items()}
    return NowResponse(
        cell_id=cell_id,
        week=week,
        built_at=calendar_row["built_at"],
        refreshing=_is_stale(calendar_row) or calendar_row["status"] == "building",
        data_quality=_data_quality(calendar_row.get("total_obs") or 0),
        **hydrated,
    )
