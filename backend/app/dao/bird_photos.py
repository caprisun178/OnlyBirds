"""Resolves a real photo for a species, backed by Wikimedia Commons
(`app/dao/commons.py`), with an in-memory cache and a generated placeholder
fallback (`https://placehold.co/...`) for when Commons has nothing — used by
both the describe & guess flow (`app/data/birds.py`'s canned reference set)
and Life List (`app/services/life_list.py`, for a seen species the user
hasn't uploaded their own photo of).

This cache is process-lifetime only — a persistent cache table
(`species_content.media`, see `bird-info.md`) is the real long-term home for
this once that feature lands.
"""

from __future__ import annotations

from urllib.parse import quote

from app.dao import commons

# scientific_name -> raw Commons search result, or None if Commons
# genuinely had nothing for it (cached too, so a species with no photo
# doesn't get re-queried on every lookup). Shared by both callers below.
#
# A *transient* Commons failure (rate limit, network error — see
# `commons.CommonsUnavailable`) is deliberately NOT cached here: a region
# checklist can look up dozens of species' photos in one request, and
# Commons' search API rate-limits quite readily under that kind of burst.
# Caching that as a permanent "nothing found" would mean one rate-limited
# moment denies a species a real photo for the rest of the process's
# uptime — so a transient failure just falls back to the placeholder for
# *this* call, leaving the next lookup free to try Commons again.
_cache: dict[str, dict | None] = {}

# One neutral color for the generated fallback — `app/data/birds.py` groups
# its own placeholders by "looks like this" category for its describe/guess
# UI, but Life List has no such grouping, so a single consistent tone is
# simpler and still visually matches (same `placehold.co` generator).
_PLACEHOLDER_COLOR = "5b7a99"


def _placeholder_photo(common_name: str) -> str:
    return f"https://placehold.co/320x220/{_PLACEHOLDER_COLOR}/ffffff?text={quote(common_name)}"


async def _lookup(scientific_name: str) -> dict | None:
    if scientific_name in _cache:
        return _cache[scientific_name]
    try:
        result = await commons.search_photo(scientific_name)
    except commons.CommonsUnavailable:
        return None  # transient — not cached, so a later call can retry
    _cache[scientific_name] = result
    return result


async def get_photo(bird: dict) -> dict:
    """`bird` is one of the dicts from `app/data/birds.py`. Looks up (and
    caches) a real Commons photo by scientific name; falls back to `bird`'s
    placeholder `photo_url` if Commons has nothing or the request fails.
    Returns `{photo_url, attribution}` — `attribution` is `None` for the
    placeholder, since there's no Commons content to credit.
    """
    result = await _lookup(bird["scientific_name"])
    if result:
        return {
            "photo_url": result["media_url"],
            "attribution": commons.format_attribution(result),
        }
    return {"photo_url": bird["photo_url"], "attribution": None}


async def get_stock_photo(scientific_name: str, common_name: str) -> dict:
    """A real Commons photo for `scientific_name`, cached — falls back to a
    generated placeholder (labelled with `common_name`, same style as
    `app/data/birds.py`'s) if Commons has nothing or the request fails, so a
    seen species without the user's own photo never renders with no image at
    all. Returns `{photo_url, attribution}`; `attribution` is `None` for the
    placeholder, same convention as `get_photo()`.
    """
    result = await _lookup(scientific_name)
    if result:
        return {
            "photo_url": result["media_url"],
            "attribution": commons.format_attribution(result),
        }
    return {"photo_url": _placeholder_photo(common_name), "attribution": None}
