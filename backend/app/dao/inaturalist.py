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

# iNaturalist's "Alive or Dead" annotation (controlled term id 17, confirmed
# live against GET /v1/controlled_terms) — value 19 is "Dead". No bulk query
# param excludes this server-side (`term_id`/`term_value_id` only do
# *inclusion* — confirmed live: requesting term_value_id=19 alone returns
# only the ~250K explicitly-dead-tagged results out of iNaturalist's tens of
# millions, nowhere near "everything except dead ones"), so
# get_nearby_observations() below filters annotated-dead records out of the
# page it already fetched instead.
_DEAD_ANNOTATION = {"controlled_attribute_id": 17, "controlled_value_id": 19}


def _is_annotated_dead(record: dict) -> bool:
    return any(
        a.get("controlled_attribute_id") == _DEAD_ANNOTATION["controlled_attribute_id"]
        and a.get("controlled_value_id") == _DEAD_ANNOTATION["controlled_value_id"]
        for a in record.get("annotations", [])
    )


async def get_nearby_observations(
    lat: float,
    lng: float,
    radius_km: int = 25,
    per_page: int = 30,
    d1: str | None = None,
    d2: str | None = None,
    days_back: int | None = None,
) -> list[dict]:
    """Research-grade **bird** observations near a point, most recent first.

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
    filter correctly). Two ways to narrow the date window, for two different
    callers: `days_back`, used by Explore Map's "last N days" filter, turns
    into `d1 = today - days_back`. `d1`/`d2` (`YYYY-MM-DD`), same as
    `get_species_counts()`, give an explicit date range in any year —
    needed by docs/features/plan-a-trip.md's hotspot drill-down, where
    "today minus N days" can't express "this window, last year". An
    explicit `d1` wins over `days_back`'s computed value if both are somehow
    given; passing both isn't expected in practice. Omitted entirely,
    iNaturalist doesn't filter by date at all.
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
    if d1 is None and days_back is not None:
        d1 = (date.today() - timedelta(days=days_back)).isoformat()
    if d1:
        params["d1"] = d1
    if d2:
        params["d2"] = d2
    async with _client() as client:
        resp = await client.get("/observations", params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    # Found-dead reports (roadkill, window strikes, museum specimens logged
    # as a sighting, ...) are real iNaturalist records, just not what
    # Explore Map's pins are for — see _DEAD_ANNOTATION above for why this
    # can't be done as a request param instead.
    return [r for r in results if not _is_annotated_dead(r)]


async def get_species_counts(
    lat: float,
    lng: float,
    radius_km: int = 25,
    d1: str | None = None,
    d2: str | None = None,
    per_page: int = 20,
) -> list[dict]:
    """Species seen near a point, ranked by observation count — iNaturalist's
    own `/observations/species_counts` aggregation, not raw observations
    fetched one at a time and deduped by hand. Backs
    docs/features/plan-a-trip.md's "likely species" list: eBird has no
    equivalent reachable through the public API — its frequency/abundance
    data lives behind the separate Status & Trends product (special access,
    not the regular API key), and its `/historic` endpoint is per-day and
    keyed by eBird region code, not point+radius — so this is
    iNaturalist-only. `d1`/`d2` (`YYYY-MM-DD`) narrow to a date window in
    any year; omitted, iNaturalist doesn't filter by date at all.
    """
    params: dict[str, float | int | str] = {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "taxon_id": _AVES_TAXON_ID,
        "quality_grade": "research",
        "per_page": per_page,
    }
    if d1:
        params["d1"] = d1
    if d2:
        params["d2"] = d2
    async with _client() as client:
        resp = await client.get("/observations/species_counts", params=params)
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
