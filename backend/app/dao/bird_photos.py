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
out (merged with whatever's currently on disk, not a blind overwrite — see
`_save_cache_file()` for why that distinction mattered in practice), so a
species resolved once stays fast for the lifetime of the repo checkout, not
just the current process. A full long-term fix is still a real cache table
(`species_content.media`, see `bird-info.md`) — this is the pragmatic
version that doesn't need a migration to get most of the benefit today.
"""

from __future__ import annotations

import asyncio
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
    # Merge with whatever's on disk right now rather than blindly
    # overwriting with just this process's own `_cache` — real, observed
    # data loss otherwise: two server processes alive at once (the
    # `--reload` watcher's old worker not actually dying before a new one
    # starts, seen repeatedly in local dev — see docs/features/explore-map.md)
    # each hold their own in-memory `_cache`, loaded from disk at different
    # times. If the one with fewer entries (loaded before the other had
    # fetched more species) writes last, a plain overwrite would silently
    # erase everything the other process had already saved. Re-reading and
    # merging first means a write can only ever add entries, never lose
    # ones already on disk — this process's own `_cache` also absorbs the
    # merge result, so a late-loaded entry from another process becomes
    # visible here too. Doesn't fully solve two processes writing at the
    # exact same instant (would need real file locking for that), but turns
    # "stale process clobbers everything" into "worst case, one write loses
    # a race by a few milliseconds" — a real fix for a real incident.
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        on_disk = _load_cache_file()
        merged = {**on_disk, **_cache}
        with _CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, sort_keys=True)
        _cache.update(merged)
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
    Returns `{photo_url, attribution, flagged}` — `attribution` is `None`
    for the placeholder, since there's no Commons content to credit.
    `flagged` (see `commons.py#_search()`) is `False` for the placeholder —
    there's nothing to doubt about a picture we generated ourselves.
    """
    result = await _lookup(bird["scientific_name"])
    if result:
        return {
            "photo_url": result["media_url"],
            "attribution": commons.format_attribution(result),
            "flagged": result.get("flagged", False),
        }
    return {"photo_url": bird["photo_url"], "attribution": None, "flagged": False}


async def get_stock_photo(scientific_name: str, common_name: str) -> dict:
    """A real Commons photo for `scientific_name`, cached — falls back to a
    generated placeholder (labelled with `common_name`, same style as
    `app/data/birds.py`'s) if Commons has nothing or the request fails, so a
    seen species without the user's own photo never renders with no image at
    all. Returns `{photo_url, attribution, flagged}`; `attribution` is
    `None` for the placeholder, same convention as `get_photo()`. `.get()`
    on `flagged` (not a plain index) because cache entries written before
    this field existed don't have it — treated as "not flagged" rather than
    invalidating the whole cache; see `get_different_stock_photo()` for the
    actual remediation path for an already-cached bad photo.
    """
    result = await _lookup(scientific_name)
    if result:
        return {
            "photo_url": result["media_url"],
            "attribution": commons.format_attribution(result),
            "flagged": result.get("flagged", False),
        }
    return {"photo_url": _placeholder_photo(common_name), "attribution": None, "flagged": False}


async def get_different_stock_photo(scientific_name: str, common_name: str, exclude_photo_url: str) -> dict:
    """"Try another photo of this species" — Test Your Skill's remediation
    for a wrong/bad image (a quiz question showing a map instead of a bird
    was the real report that motivated this), and also how an already-cached
    bad photo actually gets fixed, not just newly-avoided ones (see
    `get_stock_photo()`'s note on old cache entries predating `flagged`).

    Deliberately bypasses `_lookup()`'s single-cached-result-per-species
    shortcut — the whole point is a *different* result than whatever's
    cached. If Commons has another real candidate, the cache is updated to
    it (so this fix benefits every future lookup of this species too, not
    just this one quiz session); if there's nothing else, the original
    photo is returned unchanged with `changed: False` so the caller can tell
    "no alternative exists" from "here's a different one."

    Retries once on a transient `CommonsUnavailable` (one real, observed
    case: a burst of quiz traffic hit Commons' rate limit) before giving up
    — unlike `get_question()`'s own 12-attempt loop across *different*
    species, this call has no other fallback, so a single rate-limited
    moment would otherwise get reported to the user as "no other photo
    exists" when Commons actually has plenty — confirmed live for several
    species that hit this exact message.
    """
    result = None
    for attempt in range(2):
        try:
            result = await commons.search_photo(scientific_name, exclude_media_urls=frozenset({exclude_photo_url}))
            break
        except commons.CommonsUnavailable:
            if attempt == 0:
                await asyncio.sleep(1)

    if result is None:
        existing = _cache.get(scientific_name)
        photo_url = existing["media_url"] if existing else _placeholder_photo(common_name)
        attribution = commons.format_attribution(existing) if existing else None
        return {"photo_url": photo_url, "attribution": attribution, "flagged": False, "changed": False}

    _cache[scientific_name] = result
    _save_cache_file()
    return {
        "photo_url": result["media_url"],
        "attribution": commons.format_attribution(result),
        "flagged": result.get("flagged", False),
        "changed": True,
    }
