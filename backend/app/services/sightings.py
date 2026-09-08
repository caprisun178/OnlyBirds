"""Business logic for nearby sightings — fans out to both external APIs and
returns one normalized, time-sorted list of `Observation`s.

Realizes the "Adapter layer" box in the README architecture diagram.
"""

from __future__ import annotations

import asyncio

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError
from app.models.observation import Observation
from app.services import adapters


async def nearby(
    lat: float,
    lng: float,
    radius_km: int = 25,
    days_back: int = 7,
    include_ebird: bool = True,
    include_inat: bool = True,
) -> list[Observation]:
    tasks: list = []
    if include_ebird:
        tasks.append(_safe_ebird(lat, lng, radius_km, days_back))
    else:
        tasks.append(_noop())
    tasks.append(_safe_inat(lat, lng, radius_km) if include_inat else _noop())

    ebird_obs, inat_obs = await asyncio.gather(*tasks)

    combined = [*ebird_obs, *inat_obs]
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
