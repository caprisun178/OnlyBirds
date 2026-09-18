"""Resolves a real photo for a canned reference species (`app/data/birds.py`),
backed by Wikimedia Commons (`app/dao/commons.py`), with an in-memory cache
and a graceful fallback to the placeholder baked into `birds.py`.

This cache is process-lifetime only — a persistent cache table
(`species_content.media`, see `bird-info.md`) is the real long-term home for
this once that feature lands.
"""

from __future__ import annotations

from app.dao import commons

_cache: dict[str, dict] = {}


def _format_attribution(result: dict) -> str:
    # Creative Commons licenses require attribution — this is what the
    # candidate card credits under the photo, not just a nice-to-have.
    credit = f"{result['artist']} / Wikimedia Commons" if result.get("artist") else "Wikimedia Commons"
    if result.get("license"):
        credit += f" ({result['license']})"
    return credit


async def get_photo(bird: dict) -> dict:
    """`bird` is one of the dicts from `app/data/birds.py`. Looks up (and
    caches) a real Commons photo by scientific name; falls back to `bird`'s
    placeholder `photo_url` if Commons has nothing or the request fails.
    Returns `{photo_url, attribution}` — `attribution` is `None` for the
    placeholder, since there's no Commons content to credit.
    """
    scientific_name = bird["scientific_name"]
    cached = _cache.get(scientific_name)
    if cached is not None:
        return cached

    result = await commons.search_photo(scientific_name)
    if result:
        info = {
            "photo_url": result["photo_url"],
            "attribution": _format_attribution(result),
        }
    else:
        info = {"photo_url": bird["photo_url"], "attribution": None}

    _cache[scientific_name] = info
    return info
