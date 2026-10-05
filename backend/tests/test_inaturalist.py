"""`app/dao/inaturalist.py` — verifies the actual request params sent, since
the bug this guards against (non-bird, non-research-grade results on the
Explore Map) was a missing query param, not a response-parsing mistake. Uses
a mock transport, per docs/ebird-api.md's "no test hits a live API" rule
(applies to iNaturalist too, not just eBird).
"""

import asyncio

import httpx

from app.dao import inaturalist


def test_get_nearby_observations_filters_to_research_grade_birds(monkeypatch):
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"results": []})

    real_async_client = httpx.AsyncClient

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = real_async_client(base_url=kwargs.get("base_url", ""), transport=httpx.MockTransport(handler))

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            await self._client.aclose()

    monkeypatch.setattr(inaturalist.httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(inaturalist.get_nearby_observations(36.13, -80.47, radius_km=25))

    assert captured["params"]["taxon_id"] == "3"  # Aves
    assert captured["params"]["quality_grade"] == "research"
    assert captured["params"]["lat"] == "36.13"
    assert captured["params"]["lng"] == "-80.47"
    assert "d1" not in captured["params"]  # omitted when not given — unfiltered by date, as before
    assert "d2" not in captured["params"]


def test_get_nearby_observations_sends_the_date_window_when_given(monkeypatch):
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"results": []})

    real_async_client = httpx.AsyncClient

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = real_async_client(base_url=kwargs.get("base_url", ""), transport=httpx.MockTransport(handler))

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            await self._client.aclose()

    monkeypatch.setattr(inaturalist.httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        inaturalist.get_nearby_observations(36.13, -80.47, radius_km=2, d1="2025-10-15", d2="2025-10-20")
    )

    assert captured["params"]["d1"] == "2025-10-15"
    assert captured["params"]["d2"] == "2025-10-20"
