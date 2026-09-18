"""Wikimedia Commons — raw HTTP calls only, no business logic.

Stand-in photo source for the describe & guess candidate cards
(`app/data/birds.py`) until real Macaulay Library access exists — see
`docs/features/add-observation.md` for why: eBird's API has no photo
endpoint, and Macaulay's public search now sits behind a bot-blocking
challenge. Commons' API is public, keyless, and stable, and its license
metadata gives us the attribution Creative Commons requires.

Docs: https://commons.wikimedia.org/w/api.php
"""

from __future__ import annotations

import re

import httpx

from app.config import get_settings

_API_URL = "https://commons.wikimedia.org/w/api.php"


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"<[^>]+>", "", value).strip() or None


async def search_photo(query: str) -> dict | None:
    """The best Commons photo whose file title matches `query` (a scientific
    name works well — unambiguous, one species per binomial). Returns
    `{photo_url, source_url, artist, license}`, or `None` if nothing matched
    or the request failed.
    """
    settings = get_settings()
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'intitle:"{query}" filetype:bitmap',
        "gsrnamespace": "6",  # File namespace
        "gsrlimit": "1",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "320",
        "format": "json",
    }
    headers = {"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"}

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.get(_API_URL, params=params, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError:
        return None

    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return None

    imageinfo = next(iter(pages.values())).get("imageinfo") or []
    if not imageinfo:
        return None

    info = imageinfo[0]
    photo_url = info.get("thumburl") or info.get("url")
    if not photo_url:
        return None

    meta = info.get("extmetadata", {})
    return {
        "photo_url": photo_url,
        "source_url": info.get("descriptionurl"),
        "artist": _strip_html(meta.get("Artist", {}).get("value")),
        "license": meta.get("LicenseShortName", {}).get("value"),
    }
