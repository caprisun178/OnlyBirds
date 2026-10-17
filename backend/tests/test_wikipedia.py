"""`app/dao/wikipedia.py` — `_fetch_summary()`'s HTTP/parsing behavior tested
directly against a mocked transport (offline-tests rule, docs/ebird-api.md);
`_extract_matching_sections()`'s section-matching logic tested directly
against canned section lists/extract text, not live Wikipedia. `get_sections()`'s
own HTTP calls were live-verified once by hand while building it (see
docs/features/bird-info.md's build order) and are mocked everywhere else in
the suite via conftest.py's autouse fixture — same as `get_summary()`'s.
"""

import asyncio

import httpx
import pytest

from app.dao import wikipedia
from app.dao.wikipedia import _extract_matching_sections

_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    """Same fake-`httpx.AsyncClient` pattern as test_commons.py — a real
    client wired to a mock transport, no real network call."""

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = _RealAsyncClient(transport=httpx.MockTransport(handler))

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            await self._client.aclose()

    return FakeAsyncClient


def test_get_summary_returns_extract_and_source_url(monkeypatch):
    # Title arrives already underscored — the caller's job (see
    # app/services/species.py#_get_or_fetch_content), since the same title
    # string is reused for get_sections()'s action-API calls too, where
    # MediaWiki treats underscores and spaces as equivalent either way.
    def handler(request):
        assert "Black-capped_Chickadee" in str(request.url)
        return httpx.Response(
            200,
            request=request,
            json={
                "type": "standard",
                "extract": "The black-capped chickadee is a small songbird.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Black-capped_chickadee"}},
            },
        )

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    result = asyncio.run(wikipedia._fetch_summary("Black-capped_Chickadee"))
    assert result["extract"] == "The black-capped chickadee is a small songbird."
    assert result["source_url"] == "https://en.wikipedia.org/wiki/Black-capped_chickadee"


def test_get_summary_returns_none_on_404(monkeypatch):
    def handler(request):
        return httpx.Response(404, request=request, json={"type": "https://mediawiki.org/wiki/HyperSwitch/errors/not_found"})

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    assert asyncio.run(wikipedia._fetch_summary("Nonexistent Fake Bird")) is None


def test_get_summary_returns_none_for_disambiguation_page(monkeypatch):
    # A common name shared with something else entirely (e.g. "Robin" also
    # being a given name) lands on a disambiguation page, not a real answer.
    def handler(request):
        return httpx.Response(200, request=request, json={"type": "disambiguation", "extract": "Robin may refer to:"})

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    assert asyncio.run(wikipedia._fetch_summary("Robin")) is None


def test_get_summary_returns_none_when_extract_is_missing(monkeypatch):
    def handler(request):
        return httpx.Response(200, request=request, json={"type": "standard"})

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    assert asyncio.run(wikipedia._fetch_summary("Some Title")) is None


def test_get_summary_raises_wikipedia_unavailable_on_rate_limit(monkeypatch):
    # Regression: real, observed case — a burst of profile lookups during
    # testing hit Wikipedia's 429, and an unhandled httpx.HTTPStatusError
    # propagated all the way up through get_profile()'s asyncio.gather(),
    # cancelling the photo/audio lookups too. A 429 has to be a distinct,
    # catchable outcome, same as Commons' own CommonsUnavailable — and
    # specifically a 4xx, not a 5xx, so a fix that only special-cased
    # `status_code >= 500` wouldn't actually catch it (see _fetch_summary's
    # own docstring for why that distinction matters here).
    def raise_429(request):
        return httpx.Response(429, request=request, text="Too Many Requests")

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(raise_429))

    with pytest.raises(wikipedia.WikipediaUnavailable):
        asyncio.run(wikipedia._fetch_summary("Black-capped Chickadee"))


def test_get_summary_builds_the_rest_summary_url_from_the_given_title(monkeypatch):
    def handler(request):
        assert str(request.url) == "https://en.wikipedia.org/api/rest_v1/page/summary/Black-capped_Chickadee"
        return httpx.Response(200, request=request, json={"type": "standard", "extract": "x"})

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    asyncio.run(wikipedia._fetch_summary("Black-capped_Chickadee"))


def test_matches_description_and_combined_habitat_section():
    sections = [
        {"index": "1", "line": "Taxonomy", "toclevel": 1},
        {"index": "2", "line": "Description", "toclevel": 1},
        {"index": "3", "line": "Distribution and habitat", "toclevel": 1},
        {"index": "4", "line": "References", "toclevel": 1},
    ]
    full_text = (
        "Intro paragraph.\n\n"
        "Taxonomy\n"
        "Taxonomy text here.\n\n"
        "Description\n"
        "Males and females look alike.\n\n"
        "Distribution and habitat\n"
        "Found in forests year-round.\n\n"
        "References\n"
        "Some citation."
    )
    result = _extract_matching_sections(full_text, sections)
    assert result["sex_differences"] == "Males and females look alike."
    assert result["habitat"] == "Found in forests year-round."
    # No standalone "Migration" heading — falls back to the combined section.
    assert result["migration"] == "Found in forests year-round."


def test_standalone_migration_section_is_used_over_the_habitat_fallback():
    sections = [
        {"index": "1", "line": "Habitat", "toclevel": 1},
        {"index": "2", "line": "Migration", "toclevel": 1},
    ]
    full_text = "Habitat\nLives in wetlands.\n\nMigration\nWinters in South America."
    result = _extract_matching_sections(full_text, sections)
    assert result["habitat"] == "Lives in wetlands."
    assert result["migration"] == "Winters in South America."


def test_subsections_are_included_in_the_parent_sections_text():
    sections = [
        {"index": "1", "line": "Distribution and habitat", "toclevel": 1},
        {"index": "2", "line": "Breeding range", "toclevel": 2},
        {"index": "3", "line": "Conservation", "toclevel": 1},
    ]
    full_text = (
        "Distribution and habitat\n"
        "Found across North America.\n\n"
        "Breeding range\n"
        "Breeds in the boreal forest.\n\n"
        "Conservation\n"
        "Least concern."
    )
    result = _extract_matching_sections(full_text, sections)
    assert "Found across North America." in result["habitat"]
    assert "Breeds in the boreal forest." in result["habitat"]
    assert "Least concern." not in result["habitat"]


def test_no_matching_sections_returns_empty_dict():
    sections = [
        {"index": "1", "line": "Taxonomy", "toclevel": 1},
        {"index": "2", "line": "Cultural significance", "toclevel": 1},
    ]
    full_text = "Taxonomy\nSome text.\n\nCultural significance\nMore text."
    assert _extract_matching_sections(full_text, sections) == {}


def test_a_heading_not_found_verbatim_in_the_extract_is_skipped_not_crashed():
    # Can happen if the plain-text extract renders a heading slightly
    # differently than the sections API's title (rare, but shouldn't 500).
    sections = [{"index": "1", "line": "Habitat", "toclevel": 1}]
    full_text = "Some unrelated intro text with no matching heading line at all."
    assert _extract_matching_sections(full_text, sections) == {}
