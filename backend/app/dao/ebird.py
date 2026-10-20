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

import asyncio
from datetime import date
from math import atan2, cos, radians, sin, sqrt

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


async def get_hotspots_near(lat: float, lng: float, dist_km: int = 25) -> list[dict]:
    """Real, named, eBird-curated birding locations within `dist_km` of a
    point — each row includes `numSpeciesAllTime`, usable as a popularity
    signal. `GET /ref/hotspot/geo` (`dist` in km, 0-500; `fmt=json` since
    some `ref/` endpoints default to CSV otherwise). Needed by
    docs/features/plan-a-trip.md's hotspot suggestions — deliberately not
    Explore Map's location-name grouping, which only surfaces a place if
    sightings happen to already share its exact name; this is real, curated
    locations regardless of recent activity.
    """
    params = {"lat": lat, "lng": lng, "dist": dist_km, "fmt": "json"}
    async with _client() as client:
        resp = await client.get("/ref/hotspot/geo", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_historic_checklist(region_code: str, d: date) -> list[dict]:
    """Every species reported in a region on one specific past calendar
    day — eBird's only way to reach back further than the 30-day cap on its
    "recent" endpoints (`get_nearby_bird_sightings()`/`recent_obs_in_region()`
    above). `GET /data/obs/{region_code}/historic/{y}/{m}/{d}`. No
    date-range param — one call per day.

    `region_code` can be a real eBird region (`US-NC-067`) or — confirmed
    live against a real hotspot (`L385792`, Salem Lake, NC: real per-day
    checklist rows came back, same shape `adapters.from_ebird()` already
    parses) — a hotspot's own `locId`. That's what lets
    docs/features/plan-a-trip.md's hotspot drill-down use this without
    needing the lat/lng→region-code lookup `region_for_point()` below still
    doesn't have: a hotspot's `locId` already comes straight out of
    `get_hotspots_near()`.
    """
    async with _client() as client:
        resp = await client.get(f"/data/obs/{region_code}/historic/{d.year}/{d.month}/{d.day}")
        resp.raise_for_status()
        return resp.json()


# --- Not implemented yet — stubs for planned features. ---------------------
# Each raises NotImplementedError; the endpoint and params are documented so
# filling one in is a matter of copying the httpx call shape above. See
# docs/ebird-api.md and the feature page named on each docstring.


_TAXONOMY_BATCH_SIZE = 500  # eBird 400s a `species=` list somewhere between 500 and 1000 codes

# The full taxonomy (~17,900 taxa), fetched at most once per process — see
# get_taxonomy(). A plain module global, same process-lifetime pattern as
# region_repo.py's checklist cache; tests reset it to None.
_full_taxonomy: list[dict] | None = None
_full_taxonomy_lock = asyncio.Lock()

_RATE_LIMIT_MAX_WAIT_SECONDS = 5.0


async def _get_with_rate_limit_retry(client: httpx.AsyncClient, path: str, params: dict) -> httpx.Response:
    """One retry on a 429, waiting eBird's `Retry-After` (capped) or 1s.
    A real Render log: a burst of taxonomy calls got `429 Too Many Requests`
    and failed the whole request on the first one."""
    resp = await client.get(path, params=params)
    if resp.status_code == 429:
        try:
            wait = float(resp.headers.get("Retry-After", 1))
        except ValueError:
            wait = 1.0
        await asyncio.sleep(min(max(wait, 0.0), _RATE_LIMIT_MAX_WAIT_SECONDS))
        resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp


async def _get_full_taxonomy() -> list[dict]:
    global _full_taxonomy
    if _full_taxonomy is not None:
        return _full_taxonomy
    async with _full_taxonomy_lock:  # concurrent callers share one download
        if _full_taxonomy is None:
            async with _client() as client:
                resp = await _get_with_rate_limit_retry(client, "/ref/taxonomy/ebird", {"fmt": "json"})
                _full_taxonomy = resp.json()
    return _full_taxonomy


async def get_taxonomy(species_codes: list[str] | None = None) -> list[dict]:
    """Common/scientific names + family for eBird species codes.

    `GET /ref/taxonomy/ebird` (optional `species=<comma-separated codes>` to
    scope it; omit for the full taxonomy). Needed by Life List (populating
    `species` from a region checklist) and Bird info (species search/profile).

    A small list (one county, ~300 codes) is one scoped call. A list longer
    than eBird's undocumented `species=` limit (fails somewhere between 500
    and 1000 codes) used to be split into 500-code batches fired back to
    back — ~22 calls for the quiz's default "world" region, which got
    `429 Too Many Requests` on Render. Those now filter the full taxonomy
    instead: one download, cached for the process, shared by every large
    region.
    """
    if not species_codes:
        return await _get_full_taxonomy()

    if len(species_codes) > _TAXONOMY_BATCH_SIZE:
        wanted = set(species_codes)
        return [t for t in await _get_full_taxonomy() if t.get("speciesCode") in wanted]

    async with _client() as client:
        resp = await _get_with_rate_limit_retry(
            client, "/ref/taxonomy/ebird", {"fmt": "json", "species": ",".join(species_codes)}
        )
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
    """Recent observations anywhere in a region (not point-radius) — one row
    per species, its most recent report in the last `days_back` days. Each
    row includes `exoticCategory` (missing from the API reference doc, but
    defined by Cornell Lab — eBird's publisher — in their help center:
    "N" naturalized, "P" provisional, "X" escapee, absent for a regular
    native/countable record — see
    https://support.ebird.org/en/support/solutions/articles/48001218430-exotic-and-introduced-species-in-ebird
    and docs/ebird-api.md#exoticcategory--not-in-the-api-reference-but-documented-by-cornell).

    `GET /data/obs/{region_code}/recent` (`back=<days_back>`, capped at 30 by
    eBird itself). Needed by Explore map when the viewport is region-shaped
    rather than a point, and by Life List to drop escapee reports from a
    region's checklist (`region_repo._drop_escapees`).
    """
    async with _client() as client:
        resp = await client.get(f"/data/obs/{region_code}/recent", params={"back": days_back})
        resp.raise_for_status()
        return resp.json()


async def notable_obs(region_code: str, days_back: int = 7) -> list[dict]:
    """Rare/notable observations in a region.

    `GET /data/obs/{region_code}/recent/notable` (`back=<days_back>`). Needed
    by Explore map's "notable only" filter.
    """
    raise NotImplementedError


_REGION_LOOKUP_RADII_KM = [10, 50, 200, 500]  # 500 is eBird's own `dist` max — the widest this can search


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance — same formula `dao/observation_repo.py`'s
    `_haversine_km()` uses; kept as its own small copy here rather than a
    shared import, since the dao layer otherwise never reaches into the
    persistence layer (or vice versa) — see contributing.md's layering rule.
    """
    r = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


async def region_for_point(lat: float, lng: float) -> str:
    """The eBird region code (e.g. `US-WA-033`) a lat/lng point falls in.

    Needed by Add Observation to fill `observations.region` on every insert,
    and by Pinned Birds to match a new sighting's region against a user's
    watched region (`docs/features/pinned-birds.md`).

    eBird has no direct "region for point" endpoint — confirmed live:
    `GET /ref/region/list/{type}/{parent}` only returns `{code, name}`, no
    geometry, so "fetch candidate regions and test containment" isn't
    literally possible with that data alone. What *does* work: a hotspot
    record (`get_hotspots_near()`, already built) carries its own
    `subnational2Code`/`subnational1Code`/`countryCode` directly — so this
    finds the nearest real hotspot to the point and reads its region off
    that, expanding the search radius (up to eBird's own 500km `dist` cap)
    until one turns up. Falls back to `"world"` if nothing is found even at
    500km (extremely remote point) or if eBird isn't reachable — a failed
    region lookup should never block logging an observation.
    """
    try:
        for radius_km in _REGION_LOOKUP_RADII_KM:
            hotspots = await get_hotspots_near(lat, lng, radius_km)
            if not hotspots:
                continue
            nearest = min(hotspots, key=lambda h: _distance_km(lat, lng, h["lat"], h["lng"]))
            for key in ("subnational2Code", "subnational1Code", "countryCode"):
                code = nearest.get(key)
                if code:
                    return code
    except (EBirdConfigError, httpx.HTTPError):
        pass
    return "world"
