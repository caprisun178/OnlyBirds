"""Wikipedia — raw HTTP calls only, no business logic. See
docs/features/bird-info.md for why Wikipedia (free, keyless, same trust tier
this app already accepted for Commons photos/audio) instead of Cornell's All
About Birds / Birds of the World (licensed, no public API).

Docs: https://en.wikipedia.org/api/rest_v1/
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_HEADERS = {"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"}


class WikipediaUnavailable(RuntimeError):
    """The request itself failed — network error, timeout, rate limit
    (confirmed live: Wikipedia's REST API returns 429 under the same kind of
    burst Commons does), or a 5xx. Distinct from a normal "no such article"
    result (a plain `None`) so `app/services/species.py#get_about()` knows
    not to cache this as a permanent "nothing found" — same reasoning as
    `app/dao/commons.py#CommonsUnavailable`."""


async def get_summary(title: str) -> dict | None:
    """Thin public wrapper around `_fetch_summary()` — the autouse
    `no_live_media_lookups` test fixture stubs this name out (same
    public/private split as `app/dao/commons.py`'s `search_photo` wrapping
    `_search`), so tests exercising the real HTTP/parsing logic call
    `_fetch_summary()` directly instead — see test_wikipedia.py.
    """
    return await _fetch_summary(title)


async def _fetch_summary(title: str) -> dict | None:
    """The lead-paragraph summary for a Wikipedia article titled `title`
    (try the common name first, scientific name as a fallback — bird
    articles are almost always titled by common name, not scientific name;
    see bird-info.md). Returns `{extract, content_url}`, or `None` if the
    page doesn't exist or is a disambiguation page (ambiguous — not a real
    answer, e.g. a common name shared with something else entirely). Raises
    `WikipediaUnavailable` if the request itself failed — see that class.
    """
    url = _SUMMARY_URL.format(title=title.replace(" ", "_"))
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            resp = await client.get(url, headers=_HEADERS)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise WikipediaUnavailable(str(exc)) from exc

    data = resp.json()
    if data.get("type") == "disambiguation":
        return None

    extract = data.get("extract")
    if not extract:
        return None

    return {
        "extract": extract,
        "content_url": data.get("content_urls", {}).get("desktop", {}).get("page"),
    }
