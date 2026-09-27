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

# A species' top Commons search hit is sometimes a museum specimen photo
# (an egg, a skin, a skeleton) rather than a photo of the live bird — e.g.
# "Turdus migratorius" (American Robin) top-ranked a GLAM-batch-uploaded
# specimen photo from a French natural history museum (MHNT), filename just
# an accession number, ahead of several ordinary photos of a live robin
# further down the results — and its own descriptive text is in French
# ("Œuf" — egg), not English, since GLAM batch uploads keep the contributing
# institution's own language. Search relevance isn't tuned for "a photo of
# the animal" specifically, so photo search fetches a few extra candidates
# and skips any whose title, Commons categories, or ObjectName/
# ImageDescription metadata name one of these, in English or French — see
# `_search`.
_UNWANTED_PHOTO_KEYWORDS = (
    "egg", "eggs", "nest", "skull", "skeleton", "specimen", "taxidermy",
    "mount", "mounted", "illustration", "drawing", "painting", "diagram",
    "distribution map", "range map", "herbarium", "type specimen",
    "dead", "carcass", "roadkill",
    # French — common for GLAM uploads from French-speaking institutions
    # (MHNT/Muséum de Toulouse among them):
    "œuf", "oeuf", "nid", "crâne", "crane", "squelette", "spécimen",
    "naturalisé", "empaillé", "dessin", "carte de répartition",
    "mort", "cadavre",
)
_PHOTO_CANDIDATE_LIMIT = 10


def _is_unwanted_photo(title: str, categories: list[str]) -> bool:
    haystack = (title + " " + " ".join(categories)).lower()
    return any(keyword in haystack for keyword in _UNWANTED_PHOTO_KEYWORDS)


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


class CommonsUnavailable(RuntimeError):
    """The Commons request itself failed — network error, timeout, rate
    limit (Commons' search API returns 429 quite readily under any real
    query volume), or a 5xx. Distinct from a normal "no matching file"
    result so callers that cache results (`bird_photos.py`, `bird_audio.py`)
    know not to cache this outcome — caching a transient failure as a
    permanent "nothing found" would mean one rate-limited moment (e.g. a
    Life List checklist looking up photos for dozens of species at once)
    permanently denies that species a real photo for the rest of the
    process's uptime, even once Commons is available again.
    """


async def _search(query: str, filetype: str, *, thumbnail: bool) -> dict | None:
    """The best Commons file of `filetype` ("bitmap" | "audio") whose title
    matches `query` (a scientific name works well — unambiguous, one species
    per binomial). Returns `{media_url, source_url, artist, license}`, or
    `None` if nothing matched. Raises `CommonsUnavailable` if the request
    itself failed — see that class for why this is a distinct outcome from
    "nothing matched".
    """
    settings = get_settings()
    # Photo search fetches a few extra candidates (see
    # `_UNWANTED_PHOTO_KEYWORDS`) so it can skip past a top-ranked specimen
    # photo; audio has no equivalent problem, so it stays a single request
    # for the top hit.
    is_photo = filetype == "bitmap"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'intitle:"{query}" filetype:{filetype}',
        "gsrnamespace": "6",  # File namespace
        "gsrlimit": str(_PHOTO_CANDIDATE_LIMIT) if is_photo else "1",
        "prop": "imageinfo|categories" if is_photo else "imageinfo",
        "iiprop": "url|extmetadata",
        "format": "json",
    }
    if thumbnail:
        params["iiurlwidth"] = "320"

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.get(_API_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CommonsUnavailable(str(exc)) from exc

    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return None

    # `pages` isn't in search-rank order (it's keyed by page id) — each page
    # carries its own rank in `index`.
    candidates = sorted(pages.values(), key=lambda p: p.get("index", 0))

    info = None
    if is_photo:
        for page in candidates:
            imageinfo = page.get("imageinfo") or []
            if not imageinfo:
                continue
            categories = [c.get("title", "") for c in page.get("categories") or []]
            meta = imageinfo[0].get("extmetadata", {})
            # A GLAM batch-uploaded specimen photo (a museum's whole egg
            # collection digitized at once, say) often has an accession
            # number for a filename with no keyword in it at all — the
            # descriptive text ends up only in these metadata fields, not
            # the title, so both need checking too, not just title/categories.
            described_as = " ".join(
                meta.get(field, {}).get("value", "")
                for field in ("ObjectName", "ImageDescription")
            )
            if not _is_unwanted_photo(page.get("title", "") + " " + described_as, categories):
                info = imageinfo[0]
                break
    if info is None:
        # No un-flagged candidate (or this is an audio search, gsrlimit=1) —
        # fall back to the top-ranked hit rather than nothing at all.
        for page in candidates:
            imageinfo = page.get("imageinfo") or []
            if imageinfo:
                info = imageinfo[0]
                break
    if info is None:
        return None

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
