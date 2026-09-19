"""Wikimedia Commons — raw HTTP calls only, no business logic.

Stand-in photo *and* audio source for the describe & guess candidate cards
(`app/data/birds.py`) until real Macaulay Library access exists — see
`docs/features/add-observation.md` for why: eBird's API has no media
endpoint, and Macaulay's public search now sits behind a bot-blocking
challenge. Commons' API is public, keyless, and stable — it also mirrors a
lot of Xeno-canto's call/song recordings for exactly this reason — and its
license metadata gives us the attribution Creative Commons requires.

Docs: https://commons.wikimedia.org/w/api.php
"""

from __future__ import annotations

import re

import httpx

from app.config import get_settings

_API_URL = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"}


_HIDDEN_SPAN_RE = re.compile(
    r'<span[^>]*style="[^"]*display:\s*none[^"]*"[^>]*>.*?</span>', re.IGNORECASE | re.DOTALL
)


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    # Commons' "Unknown author" template (and others) puts a hidden
    # screen-reader duplicate right after the visible text, e.g.
    # 'Unknown author<span style="display: none;">Unknown author</span>' —
    # drop that before stripping tags, or the credit line reads doubled.
    without_hidden = _HIDDEN_SPAN_RE.sub("", value)
    return re.sub(r"<[^>]+>", "", without_hidden).strip() or None


def format_attribution(result: dict) -> str:
    """Creative Commons licenses require attribution — shared by the photo
    and audio callers so the credit line under a candidate's media reads the
    same way either way."""
    credit = f"{result['artist']} / Wikimedia Commons" if result.get("artist") else "Wikimedia Commons"
    if result.get("license"):
        credit += f" ({result['license']})"
    return credit


async def _search(query: str, filetype: str, *, thumbnail: bool) -> dict | None:
    """The best Commons file of `filetype` ("bitmap" | "audio") whose title
    matches `query` (a scientific name works well — unambiguous, one species
    per binomial). Returns `{media_url, source_url, artist, license}`, or
    `None` if nothing matched or the request failed.
    """
    settings = get_settings()
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'intitle:"{query}" filetype:{filetype}',
        "gsrnamespace": "6",  # File namespace
        "gsrlimit": "1",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "format": "json",
    }
    if thumbnail:
        params["iiurlwidth"] = "320"

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.get(_API_URL, params=params, headers=_HEADERS)
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
    media_url = info.get("thumburl") or info.get("url")
    if not media_url:
        return None

    meta = info.get("extmetadata", {})
    return {
        "media_url": media_url,
        "source_url": info.get("descriptionurl"),
        "artist": _strip_html(meta.get("Artist", {}).get("value")),
        "license": meta.get("LicenseShortName", {}).get("value"),
    }


async def search_photo(query: str) -> dict | None:
    return await _search(query, "bitmap", thumbnail=True)


async def search_audio(query: str) -> dict | None:
    """A call/song recording — Commons hosts a lot of Xeno-canto's archive
    under the same file-search API used for photos."""
    return await _search(query, "audio", thumbnail=False)
