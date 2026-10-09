import asyncio

import httpx
import pytest

from app.dao import wikipedia

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

    result = asyncio.run(wikipedia._fetch_summary("Black-capped Chickadee"))
    assert result["extract"] == "The black-capped chickadee is a small songbird."
    assert result["content_url"] == "https://en.wikipedia.org/wiki/Black-capped_chickadee"


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
    # catchable outcome, same as Commons' own CommonsUnavailable.
    def raise_429(request):
        return httpx.Response(429, request=request, text="Too Many Requests")

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(raise_429))

    with pytest.raises(wikipedia.WikipediaUnavailable):
        asyncio.run(wikipedia._fetch_summary("Black-capped Chickadee"))


def test_get_summary_replaces_spaces_with_underscores_in_the_url(monkeypatch):
    def handler(request):
        assert "Black-capped%20Chickadee" not in str(request.url)
        assert "Black-capped_Chickadee" in str(request.url)
        return httpx.Response(200, request=request, json={"type": "standard", "extract": "x"})

    monkeypatch.setattr(wikipedia.httpx, "AsyncClient", _mock_client(handler))

    asyncio.run(wikipedia._fetch_summary("Black-capped Chickadee"))
