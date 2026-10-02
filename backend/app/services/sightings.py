"""Business logic for nearby sightings — fans out to eBird, iNaturalist, and
our own logged observations, and returns one normalized, time-sorted list of
`Observation`s.

Realizes the "Adapter layer" box in the README architecture diagram.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError
from app.dao.observation_repo import observation_repo
from app.models.observation import Observation
from app.services import adapters


async def nearby(
    lat: float,
    lng: float,
    radius_km: int = 25,
    days_back: int = 7,
    include_ebird: bool = True,
    include_inat: bool = True,
    include_own: bool = True,
) -> list[Observation]:
    tasks: list = []
    tasks.append(_safe_ebird(lat, lng, radius_km, days_back) if include_ebird else _noop())
    tasks.append(_safe_inat(lat, lng, radius_km) if include_inat else _noop())
    tasks.append(_own_nearby(lat, lng, radius_km, days_back) if include_own else _noop())

    ebird_obs, inat_obs, own_obs = await asyncio.gather(*tasks)

    combined = [*ebird_obs, *inat_obs, *own_obs]
    combined.sort(key=lambda o: o.observed_at, reverse=True)
    return combined


async def _noop() -> list[Observation]:
    return []


async def _safe_ebird(lat, lng, radius_km, days_back) -> list[Observation]:
    try:
        raw = await ebird.get_nearby_bird_sightings(lat, lng, radius_km, days_back)
    except EBirdConfigError:
        return []
    return [adapters.from_ebird(r) for r in raw]


async def _safe_inat(lat, lng, radius_km) -> list[Observation]:
    raw = await inaturalist.get_nearby_observations(lat, lng, radius_km)
    return [adapters.from_inaturalist(r) for r in raw]


async def _own_nearby(lat, lng, radius_km, days_back) -> list[Observation]:
    """Other OnlyBirds users' (and the caller's own) logged sightings near
    this point — not an external API, so no adapter needed, `Observation` is
    already the shape `observation_repo` returns. See
    `dao/observation_repo.py#list_near` for how "near" is computed without a
    real PostGIS geom column.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    return await observation_repo.list_near(lat, lng, radius_km, since)
