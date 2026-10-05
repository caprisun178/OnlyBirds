"""`app/dao/ebird.py#get_hotspots_near()` — verifies the actual request sent
and response pass-through. Mocked via a transport, per docs/ebird-api.md's
"no test hits a live API" rule. (Manually verified live once while building
this — see docs/features/plan-a-trip.md's build order — real field names:
locId, locName, lat, lng, numSpeciesAllTime, among others.)
"""

import asyncio

import httpx

from app.config import get_settings
from app.dao import ebird

RAW_HOTSPOT = {
    "locId": "L1021141",
    "locName": "Bethania--Black Walnut Bottom",
    "countryCode": "US",
    "subnational1Code": "US-NC",
    "subnational2Code": "US-NC-067",
    "lat": 36.1780162,
    "lng": -80.3390694,
    "latestObsDt": "2026-10-02 08:45",
    "numSpeciesAllTime": 160,
    "numChecklistsAllTime": 2134,
}


def test_get_hotspots_near_sends_the_right_params(monkeypatch):
    # A fake key, not whatever's (or isn't) in the real environment's .env —
    # same pattern test_health.py uses, so this test doesn't depend on
    # EBIRD_API_KEY happening to be configured wherever it runs.
    monkeypatch.setenv("EBIRD_API_KEY", "test-key")
    get_settings.cache_clear()

    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[RAW_HOTSPOT])

    real_async_client = httpx.AsyncClient

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = real_async_client(
                base_url=kwargs.get("base_url", ""), transport=httpx.MockTransport(handler)
            )

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, *args):
            await self._client.aclose()

    monkeypatch.setattr(ebird.httpx, "AsyncClient", FakeAsyncClient)

    try:
        result = asyncio.run(ebird.get_hotspots_near(36.18, -80.34, dist_km=15))
    finally:
        get_settings.cache_clear()  # don't leak the fake key into later tests

    assert captured["path"].endswith("/ref/hotspot/geo")
    assert captured["params"]["lat"] == "36.18"
    assert captured["params"]["lng"] == "-80.34"
    assert captured["params"]["dist"] == "15"
    assert captured["params"]["fmt"] == "json"
    assert result == [RAW_HOTSPOT]
