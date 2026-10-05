"""
==============================
iNaturalist script library
Description:
Raw access to the iNaturalist API v1 — no business logic. No auth required
for reads; OAuth2 would only be needed to write observations on a user's
behalf, which the base server does not do.
Docs: https://api.inaturalist.org/v1/docs/

=============================
changeLog
=============================
09/11/2026 ... SP ... Added obs_in_bbox() stub for Explore map
=============================
"""

from datetime import date, timedelta

import httpx

from app.config import get_settings


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.inat_base_url,
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"},
    )


async def search_species(query: str, per_page: int = 20) -> list[dict]:
    """Taxon autocomplete — returns the raw `results` array from /taxa."""
    async with _client() as client:
        resp = await client.get("/taxa", params={"q": query, "per_page": per_page})
        resp.raise_for_status()
        return resp.json().get("results", [])


async def get_taxon(taxon_id: int | str) -> dict | None:
    async with _client() as client:
        resp = await client.get(f"/taxa/{taxon_id}")
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


_AVES_TAXON_ID = 3  # iNaturalist's taxon id for Class Aves (birds) — see obs_in_bbox()'s docstring below


async def get_nearby_observations(
    lat: float,
    lng: float,
    radius_km: int = 25,
    per_page: int = 30,
    days_back: int | None = None,
) -> list[dict]:
    """Recent research-grade **bird** observations near a point.

    Regression: this used to omit `taxon_id`/`quality_grade` entirely, so it
    returned iNaturalist's full firehose near a point — mammals, insects,
    plants, unverified "casual" grade sightings, not just birds — which
    showed up as non-bird pins on the Explore Map. `taxon_id=3` (Aves) plus
    `quality_grade=research` narrows it to what this app is actually about.

    Second regression, found later: this had no date filtering at all —
    `order_by=observed_on&order=desc` only sorts newest-first, it doesn't
    exclude anything, so an "only show the last 7 days" request could still
    return a sighting from 8 months ago as long as it ranked within the
    first `per_page` results (a real "Since: Last 7 days doesn't filter"
    report, since iNat results get merged in alongside eBird's, which *does*
    filter correctly). `d1` (`YYYY-MM-DD`) is iNaturalist's own date-range
    param — `days_back`, when given, turns into `d1 = today - days_back`,
    excluding anything observed before that.
    """
    params: dict[str, float | int | str] = {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "per_page": per_page,
        "taxon_id": _AVES_TAXON_ID,
        "quality_grade": "research",
        "order_by": "observed_on",
        "order": "desc",
    }
    if days_back is not None:
        d1 = date.today() - timedelta(days=days_back)
        params["d1"] = d1.isoformat()
    async with _client() as client:
        resp = await client.get("/observations", params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])


# --- Not implemented yet — stub for a planned feature. ---------------------


async def obs_in_bbox(
    west: float,
    south: float,
    east: float,
    north: float,
    since: str | None = None,
) -> list[dict]:
    """Research-grade bird observations inside a map viewport.

    `GET /observations?taxon_id=3&nelat=&nelng=&swlat=&swlng=` (taxon 3 =
    Aves; `since=YYYY-MM-DD` narrows the date window). Needed by Explore map
    for the bounding-box (rather than point-radius) sighting query.
    """
    raise NotImplementedError
