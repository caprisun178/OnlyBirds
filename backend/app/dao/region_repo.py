"""Cache in front of eBird's region-checklist + taxonomy calls.

Mirrors the `region_checklists` table design (see database.md) — one row per
region, refetched once stale. True cross-restart persistence lands with
PostgreSQL in roadmap step 3; until then this is a process-lifetime dict,
the same pattern as `app/dao/bird_photos.py`'s photo cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.dao import ebird

_STALE_AFTER = timedelta(days=30)
_cache: dict[str, dict] = {}  # region_code -> {"species": [...], "fetched_at": datetime}


async def get_checklist(region_code: str) -> list[dict]:
    """Every eBird `category == "species"` taxon ever reported in
    `region_code` (drops spuh/slash/hybrid/domestic entries — those aren't
    identifiable species and shouldn't count toward a life list), with
    common/scientific names, sorted taxonomically. Cached per region.
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
            }
            for t in taxonomy
            if t.get("category") == "species"
        ),
        key=lambda s: s["taxon_order"],
    )
    _cache[region_code] = {"species": species, "fetched_at": datetime.now(timezone.utc)}
    return species
