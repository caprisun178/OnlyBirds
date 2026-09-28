"""Cache in front of eBird's region-checklist + taxonomy calls.

Mirrors the `region_checklists` table design (see database.md) — one row per
region, refetched once stale. True cross-restart persistence lands with
PostgreSQL in roadmap step 3; until then this is a process-lifetime dict,
the same pattern as `app/dao/bird_photos.py`'s photo cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.dao import ebird
from app.data.exotic_exclusions import EXCLUDED_SPECIES_CODES

_STALE_AFTER = timedelta(days=30)
_cache: dict[str, dict] = {}  # region_code -> {"species": [...], "fetched_at": datetime}

# eBird's own hard cap on how far back "recent observations" can look —
# see `_drop_escapees`.
_EXOTIC_LOOKBACK_DAYS = 30


async def get_checklist(region_code: str) -> list[dict]:
    """Every eBird `category == "species"` taxon ever reported in
    `region_code` (drops spuh/slash/hybrid/domestic entries — those aren't
    identifiable species and shouldn't count toward a life list), with
    common/scientific names, sorted taxonomically, and with escapees dropped
    — both currently-flagged ones (`_drop_escapees`) and the hand-maintained
    ones in `app/data/exotic_exclusions.py`, for escapees outside what eBird's
    API can catch live. Cached per region.
    """
    cached = _cache.get(region_code)
    if cached and datetime.now(timezone.utc) - cached["fetched_at"] < _STALE_AFTER:
        return cached["species"]

    codes = await ebird.get_region_spplist(region_code)
    taxonomy = await ebird.get_taxonomy(codes) if codes else []
    species = sorted(
        (
            {
                "code": t["speciesCode"],
                "common_name": t["comName"],
                "scientific_name": t["sciName"],
                "taxon_order": t.get("taxonOrder") or 0,
                # eBird's family grouping (e.g. "Ducks, Geese, and Waterfowl",
                # "Crows, Jays, and Magpies") — used as the "bird type" filter.
                "family_common_name": t.get("familyComName") or "",
            }
            for t in taxonomy
            if t.get("category") == "species"
        ),
        key=lambda s: s["taxon_order"],
    )
    species = [s for s in species if s["code"] not in EXCLUDED_SPECIES_CODES]
    species = await _drop_escapees(region_code, species)
    _cache[region_code] = {"species": species, "fetched_at": datetime.now(timezone.utc)}
    return species


async def _drop_escapees(region_code: str, species: list[dict]) -> list[dict]:
    """`/product/spplist/{region}` returns every species code *ever* reported
    in the region, with no established/countable status attached — that's
    how e.g. a single old report of an escaped farm Ostrich ends up on a
    region's "full checklist" next to species that actually belong there.
    eBird tracks that status (`exoticCategory`) per observation, not per
    species-list entry — defined by Cornell Lab (eBird's publisher) in
    https://support.ebird.org/en/support/solutions/articles/48001218430-exotic-and-introduced-species-in-ebird,
    see docs/ebird-api.md — so it's cross-referenced here via each species'
    most recent regional report: `"X"` (escapee, not countable) gets
    dropped; `"N"` (naturalized, e.g. House Sparrow) and `"P"` (provisional)
    stay, matching eBird's own default regional-checklist behavior.

    Best-effort, not exhaustive: eBird's "recent observations" endpoint —
    the only place this status is exposed — only looks back
    `_EXOTIC_LOOKBACK_DAYS` days (eBird's own cap, not ours). A species
    whose *only* report ever was an escapee sighting older than that has no
    signal to catch it here. This thins out ongoing local escapee
    populations (Muscovy Duck, Monk Parakeet, feral Helmeted Guineafowl,
    ...), which are the common case — not a guarantee against every one-off
    historic record.
    """
    try:
        recent = await ebird.recent_obs_in_region(region_code, days_back=_EXOTIC_LOOKBACK_DAYS)
    except httpx.HTTPError:
        return species  # a failed enrichment call shouldn't fail the whole checklist

    escapee_codes = {obs["speciesCode"] for obs in recent if obs.get("exoticCategory") == "X"}
    if not escapee_codes:
        return species
    return [s for s in species if s["code"] not in escapee_codes]
