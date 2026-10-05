"""Business logic for Plan a Trip — see docs/features/plan-a-trip.md.

Fans out to eBird (hotspots) and iNaturalist (last-year species counts)
concurrently, then cross-references the caller's life list if given.
"""

from __future__ import annotations

import asyncio
from datetime import date

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError
from app.models.trip import Hotspot, LikelySpecies, TripPlan
from app.services import adapters
from app.services.life_list import get_life_list

_SPECIES_PER_TRIP = 30


def _one_year_earlier(d: date) -> date:
    """Same month/day, one year back — guards the one real edge case (a
    Feb 29 trip date in a year that isn't itself a leap year) by nudging
    back a day rather than crashing.
    """
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


async def plan_trip(
    lat: float,
    lng: float,
    start_date: date,
    end_date: date,
    radius_km: int = 25,
    user_id: str | None = None,
) -> TripPlan:
    """Suggested hotspots + likely species for a trip on `start_date`..
    `end_date` (this year or any year) — "likely" means "reported this often
    in roughly the same window last year" (see docs/features/plan-a-trip.md
    for why that's the honest scope, not a multi-year average). `user_id`
    is optional: given, each species' `new_for_you` is set from the caller's
    actual life list; omitted, it's left `None` rather than guessed.
    """
    d1 = _one_year_earlier(start_date)
    d2 = _one_year_earlier(end_date)

    hotspots_task = _safe_hotspots(lat, lng, radius_km)
    species_task = inaturalist.get_species_counts(
        lat, lng, radius_km, d1=d1.isoformat(), d2=d2.isoformat(), per_page=_SPECIES_PER_TRIP
    )
    life_list_task = get_life_list(user_id) if user_id else _noop()

    raw_hotspots, raw_species, life_list_entries = await asyncio.gather(
        hotspots_task, species_task, life_list_task
    )

    hotspots = [adapters.from_ebird_hotspot(h) for h in raw_hotspots]
    hotspots.sort(key=lambda h: h.species_all_time, reverse=True)

    likely_species = [adapters.from_inat_species_count(r) for r in raw_species]
    if user_id:
        seen = {
            e.species.scientific_name
            for e in life_list_entries
            if e.species.scientific_name
        }
        for sp in likely_species:
            sp.new_for_you = bool(sp.species.scientific_name) and sp.species.scientific_name not in seen

    return TripPlan(hotspots=hotspots, likely_species=likely_species)


async def _safe_hotspots(lat: float, lng: float, radius_km: int) -> list[dict]:
    """No `EBIRD_API_KEY` configured shouldn't take down the whole trip
    plan — just means no hotspot suggestions, same graceful-degradation
    pattern `services/sightings.py#_safe_ebird` already uses.
    """
    try:
        return await ebird.get_hotspots_near(lat, lng, radius_km)
    except EBirdConfigError:
        return []


async def _noop() -> list:
    return []
