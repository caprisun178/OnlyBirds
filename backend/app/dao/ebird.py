"""
==============================
eBird script library
Description:
Raw access to the eBird API 2.0 — no business logic. Calls the REST endpoint
directly with httpx (async, one fewer dependency) rather than the `ebird-api`
wrapper suggested in the README. The API key is read from settings and sent
as the `X-eBirdApiToken` header; it never leaves the backend.
Docs: https://documenter.getpostman.com/view/664302/S1ENwy59

=============================
changeLog
=============================
09/11/2026 ... SP ... Added stub functions for planned-feature reads (taxonomy, region list/checklist, region/notable obs, region-for-point)
=============================
"""

import httpx

from app.config import get_settings


class EBirdConfigError(RuntimeError):
    """Raised when the eBird API key is not configured."""


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    if not settings.ebird_api_key:
        raise EBirdConfigError("EBIRD_API_KEY is not set")
    return httpx.AsyncClient(
        base_url=settings.ebird_base_url,
        headers={"X-eBirdApiToken": settings.ebird_api_key},
        timeout=settings.http_timeout_seconds,
    )


async def get_nearby_bird_sightings(
    lat: float,
    lng: float,
    dist_km: int = 25,
    days_back: int = 7,
) -> list[dict]:
    """Recent bird observations within `dist_km` of a point."""
    params = {"lat": lat, "lng": lng, "dist": dist_km, "back": days_back}
    async with _client() as client:
        resp = await client.get("/data/obs/geo/recent", params=params)
        resp.raise_for_status()
        return resp.json()


# --- Not implemented yet — stubs for planned features. ---------------------
# Each raises NotImplementedError; the endpoint and params are documented so
# filling one in is a matter of copying the httpx call shape above. See
# docs/ebird-api.md and the feature page named on each docstring.


async def get_taxonomy(species_codes: list[str] | None = None) -> list[dict]:
    """Common/scientific names + family for eBird species codes.

    `GET /ref/taxonomy/ebird` (optional `species=<comma-separated codes>` to
    scope it; omit for the full taxonomy). Needed by Life List (populating
    `species` from a region checklist) and Bird info (species search/profile).
    """
    params = {"fmt": "json"}
    if species_codes:
        params["species"] = ",".join(species_codes)
    async with _client() as client:
        resp = await client.get("/ref/taxonomy/ebird", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_region_children(parent_code: str, region_type: str) -> list[dict]:
    """Child regions one level below `parent_code` (e.g. states in a country).

    `GET /ref/region/list/{region_type}/{parent_code}` — region_type is
    `country` | `subnational1` | `subnational2`. Needed by Life List's region
    picker (also reused by User profiles' `default_region` picker).
    """
    async with _client() as client:
        resp = await client.get(f"/ref/region/list/{region_type}/{parent_code}")
        resp.raise_for_status()
        return resp.json()


async def get_region_spplist(region_code: str) -> list[str]:
    """The full list of eBird species codes ever reported in a region.

    `GET /product/spplist/{region_code}`. Needed by Life List to build the
    region's full checklist (cached in `region_checklists`).
    """
    async with _client() as client:
        resp = await client.get(f"/product/spplist/{region_code}")
        resp.raise_for_status()
        return resp.json()


async def recent_obs_in_region(region_code: str, days_back: int = 7) -> list[dict]:
    """Recent observations anywhere in a region (not point-radius).

    `GET /data/obs/{region_code}/recent` (`back=<days_back>`). Needed by
    Explore map when the viewport is region-shaped rather than a point.
    """
    raise NotImplementedError


async def notable_obs(region_code: str, days_back: int = 7) -> list[dict]:
    """Rare/notable observations in a region.

    `GET /data/obs/{region_code}/recent/notable` (`back=<days_back>`). Needed
    by Explore map's "notable only" filter.
    """
    raise NotImplementedError


async def region_for_point(lat: float, lng: float) -> str:
    """The eBird region code (e.g. `US-WA-033`) a lat/lng point falls in.

    Needed by Add Observation to fill `observations.region` on every insert.
    eBird has no direct "region for point" endpoint — the feature page leaves
    the approach open: either find a reverse-geocode workaround via
    `GET /ref/region/list/...` (fetch candidate regions and test containment)
    or do a local point-in-polygon check against a region-boundary dataset.
    Decide the approach when implementing this.
    """
    raise NotImplementedError
