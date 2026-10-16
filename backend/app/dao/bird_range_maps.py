"""Resolves a range map for the Bird Info page, backed by Wikimedia Commons
(`app/dao/commons.py#search_range_map()`), with an in-memory cache.

The capstone-era stand-in for a real migration map — see
docs/features/bird-info.md. No placeholder fallback: a made-up map would be
worse than none, so a species with no Commons map just shows no map section.
"""

from __future__ import annotations

from app.dao import commons

_cache: dict[str, dict | None] = {}


async def get_range_map(scientific_name: str) -> dict | None:
    """Returns `{map_url, attribution, source_url, caption, legend}` or
    `None`; `legend` is `[{color, label}]`, possibly empty.
    A transient `CommonsUnavailable` isn't cached, so a later call retries —
    same reasoning as `bird_audio.py`."""
    if scientific_name in _cache:
        return _cache[scientific_name]

    try:
        result = await commons.search_range_map(scientific_name)
    except commons.CommonsUnavailable:
        return None

    info = (
        {
            "map_url": result["media_url"],
            "attribution": commons.format_attribution(result),
            "source_url": result["source_url"],
            "caption": result["caption"],
            "legend": result["legend"],
        }
        if result and result.get("media_url")
        else None
    )
    _cache[scientific_name] = info
    return info
