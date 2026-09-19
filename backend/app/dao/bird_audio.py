"""Resolves a real call/song recording for a canned reference species
(`app/data/birds.py`), backed by Wikimedia Commons (`app/dao/commons.py`),
with an in-memory cache.

Unlike `bird_photos.py` there's no placeholder fallback here — a fabricated
bird call would actively mislead someone trying to identify a bird by ear,
so a species with no recording just has no audio; the "heard it" flow needs
to handle that (see `docs/features/add-observation.md`).
"""

from __future__ import annotations

from app.dao import commons

_cache: dict[str, dict | None] = {}


async def get_audio(bird: dict) -> dict | None:
    """`bird` is one of the dicts from `app/data/birds.py`. Looks up (and
    caches) a real Commons recording by scientific name. Returns
    `{audio_url, attribution}`, or `None` if Commons has nothing or the
    request fails — there is no placeholder to fall back to.
    """
    scientific_name = bird["scientific_name"]
    if scientific_name in _cache:
        return _cache[scientific_name]

    result = await commons.search_audio(scientific_name)
    info = (
        {"audio_url": result["media_url"], "attribution": commons.format_attribution(result)}
        if result
        else None
    )
    _cache[scientific_name] = info
    return info
