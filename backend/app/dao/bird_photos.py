"""Resolves a real photo for a species, backed by Wikimedia Commons
(`app/dao/commons.py`), with a disk-backed cache and a generated placeholder
fallback (`https://placehold.co/...`) for when Commons has nothing — used by
both the describe & guess flow (`app/data/birds.py`'s canned reference set),
Life List (`app/services/life_list.py`, for a seen species the user hasn't
uploaded their own photo of), and Explore Map's species-filter suggestions
(`app/services/species.py#get_stock_photos`, most of which are eBird
sightings that never carry their own photo).

The cache used to be process-lifetime only — real, reported effect: the
first Commons lookup for a given species (one real HTTP round-trip) is
noticeably slow, and every server restart threw the whole cache away,
making that slow first-lookup happen again for species that had already
been resolved. Now persisted to `species_photo_cache.json` alongside this
file: loaded once at import, and every new entry is written straight back
out, so a species resolved once stays fast for the lifetime of the repo
checkout, not just the current process. A full long-term fix is still a
real cache table (`species_content.media`, see `bird-info.md`) — this is
the pragmatic version that doesn't need a migration to get most of the
benefit today.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from app.dao import commons

_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "species_photo_cache.json"


def _load_cache_file() -> dict[str, dict | None]:
    try:
        with _CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_cache_file() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(_cache, f, indent=2, sort_keys=True)
    except OSError as exc:
        # Best-effort — an unwritable cache file shouldn't break photo
        # lookups — but silent-forever was hard to debug, so log it.
        print(f"bird_photos: could not write cache file {_CACHE_FILE}: {exc}", flush=True)


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
_cache: dict[str, dict | None] = _load_cache_file()

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
    _save_cache_file()
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
