"""Wikipedia — the About block's summary, plus a heuristic pull of a few
article sections for the Bird Info page's sex-differences/migration/habitat
text. See docs/features/bird-info.md for why Wikipedia (not Cornell) and why
these three are prose, not structured fields.

No API key, no auth — both endpoints used here are the public, anonymous
MediaWiki/REST APIs.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_REST_BASE = "https://en.wikipedia.org/api/rest_v1"
_ACTION_API = "https://en.wikipedia.org/w/api.php"

# Wikimedia's API etiquette policy blocks requests with no (or a generic
# default) User-Agent — confirmed live: httpx's own default UA gets a flat
# 403 from the REST summary endpoint. A descriptive UA with a contact point
# is what the policy actually asks for.
# https://meta.wikimedia.org/wiki/User-Agent_policy
_HEADERS = {"User-Agent": "OnlyBirds/0.1 (https://github.com/caprisun178/OnlyBirds; beta bird app)"}

# Case-insensitive substring match against a Wikipedia section's own title —
# most bird articles follow WikiProject Birds' structure closely enough for
# this to work most of the time, but it's a real convention, not a schema
# (see bird-info.md's note). `habitat` intentionally also matches
# "Distribution and habitat" (the common combined heading); `migration`
# falls back to that same combined section when there's no standalone one
# (see _get_sections_sync's docstring).
_SECTION_PATTERNS = {
    "sex_differences": ("description",),
    "migration": ("migration",),
    "habitat": ("habitat", "distribution"),
}


class WikipediaUnavailable(Exception):
    """A transient failure (network, rate limit, 5xx) — distinct from "no
    such article," which just means there's nothing to show, not an error.
    """


async def get_summary(title: str) -> dict | None:
    """Thin public wrapper around `_fetch_summary()` — the autouse
    `no_live_media_lookups` test fixture stubs this name out (same
    public/private split as `app/dao/commons.py`'s `search_photo` wrapping
    `_search`), so a test exercising the real HTTP/parsing logic calls
    `_fetch_summary()` directly instead — see test_wikipedia.py.
    """
    return await _fetch_summary(title)


async def _fetch_summary(title: str) -> dict | None:
    """One paragraph + the article URL for `title` (page title, not a
    scientific name — see bird-info.md's note on why common name first).
    Returns `None` for a 404 or a disambiguation page; raises
    `WikipediaUnavailable` for anything that looks transient — confirmed
    live: a 429 under the same kind of burst Commons' own API rate-limits
    under, same reasoning as `app/dao/commons.py#CommonsUnavailable`. Every
    status-code check and `raise_for_status()` call has to stay *inside*
    the `try` below — a 429 is a 4xx, not a 5xx, so a version of this that
    only special-cased `>= 500` before calling `raise_for_status()` outside
    the `try` would let a 429 escape as a bare, uncaught `HTTPStatusError`.
    """
    settings = get_settings()
    url = f"{_REST_BASE}/page/summary/{httpx.URL(title).path or title}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS) as client:
            resp = await client.get(url)
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
        "source_url": data.get("content_urls", {}).get("desktop", {}).get("page"),
    }


async def get_sections(title: str) -> dict[str, str]:
    """Best-effort `{sex_differences?, migration?, habitat?}` text pulled
    from `title`'s own sections — only the keys that actually matched
    something are present (not `None` placeholders; callers treat a missing
    key as "the article didn't say," same as the About block's `None`).
    Returns `{}` (not an error) if the article doesn't exist or has none of
    the patterns in `_SECTION_PATTERNS`.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS) as client:
            sections_resp = await client.get(
                _ACTION_API,
                params={"action": "parse", "page": title, "prop": "sections", "format": "json"},
            )
            sections_resp.raise_for_status()
            sections_data = sections_resp.json()
            if "error" in sections_data:
                return {}  # no such page — not an error, just nothing to show

            extract_resp = await client.get(
                _ACTION_API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exsectionformat": "plain",
                    "titles": title,
                    "format": "json",
                },
            )
            extract_resp.raise_for_status()
            extract_data = extract_resp.json()
    except httpx.HTTPError as exc:
        raise WikipediaUnavailable(str(exc)) from exc

    pages = extract_data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), None)
    full_text = page.get("extract") if page else None
    if not full_text:
        return {}

    sections = sections_data.get("parse", {}).get("sections", [])
    return _extract_matching_sections(full_text, sections)


def _extract_matching_sections(full_text: str, sections: list[dict]) -> dict[str, str]:
    lines = full_text.split("\n")

    # Find each section header's line position, in document order, scanning
    # forward from the previous match — a title that happens to repeat
    # elsewhere in body text won't be mistaken for the real heading line as
    # long as headings themselves appear in the order the API reported.
    positions: list[tuple[int, int]] = []  # (line_index, toclevel)
    search_from = 0
    for section in sections:
        title = section["line"].strip()
        toclevel = section["toclevel"]
        for i in range(search_from, len(lines)):
            if lines[i].strip() == title:
                positions.append((i, toclevel))
                search_from = i + 1
                break
        else:
            positions.append((-1, toclevel))  # heading text wasn't found verbatim — skip it below

    found: dict[str, str] = {}
    for field, patterns in _SECTION_PATTERNS.items():
        for idx, (section, (line_idx, toclevel)) in enumerate(zip(sections, positions)):
            if line_idx == -1:
                continue
            title_lower = section["line"].strip().lower()
            if not any(p in title_lower for p in patterns):
                continue

            end_line = len(lines)
            for later_line_idx, later_toclevel in positions[idx + 1 :]:
                if later_line_idx != -1 and later_toclevel <= toclevel:
                    end_line = later_line_idx
                    break

            body = "\n".join(lines[line_idx + 1 : end_line]).strip()
            if body:
                found[field] = body
            break  # first matching section wins for this field

    # Most bird articles fold migration into "Distribution and habitat"
    # rather than giving it its own heading (confirmed live — see
    # docs/features/bird-info.md's note). When there's no standalone
    # migration section, the habitat text already covers it in practice.
    if "migration" not in found and "habitat" in found:
        found["migration"] = found["habitat"]

    return found
