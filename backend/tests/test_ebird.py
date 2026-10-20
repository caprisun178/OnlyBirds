"""`app/dao/ebird.py#get_hotspots_near()` — verifies the actual request sent
and response pass-through. Mocked via a transport, per docs/ebird-api.md's
"no test hits a live API" rule. (Manually verified live once while building
this — see docs/features/plan-a-trip.md's build order — real field names:
locId, locName, lat, lng, numSpeciesAllTime, among others.)
"""

import asyncio
from datetime import date

import httpx

from app.config import get_settings
from app.dao import ebird
from app.dao.ebird import EBirdConfigError

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


RAW_HISTORIC_OBS = {
    "speciesCode": "cangoo",
    "comName": "Canada Goose",
    "sciName": "Branta canadensis",
    "locId": "L385792",
    "locName": "Salem Lake",
    "obsDt": "2026-10-04 08:00",
    "howMany": 24,
    "lat": 36.096551,
    "lng": -80.1878357,
    "subId": "S399064232",
}


def test_get_historic_checklist_sends_the_right_path(monkeypatch):
    monkeypatch.setenv("EBIRD_API_KEY", "test-key")
    get_settings.cache_clear()

    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        return httpx.Response(200, json=[RAW_HISTORIC_OBS])

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
        # A hotspot locId works here too, not just a region code (US-NC-067,
        # etc.) — confirmed live against the real API; see
        # get_historic_checklist()'s docstring.
        result = asyncio.run(ebird.get_historic_checklist("L385792", date(2026, 10, 4)))
    finally:
        get_settings.cache_clear()

    assert captured["path"].endswith("/data/obs/L385792/historic/2026/10/4")
    assert result == [RAW_HISTORIC_OBS]


def test_region_for_point_returns_the_nearest_hotspots_subnational2(monkeypatch):
    near = {"lat": 36.10, "lng": -80.10, "subnational2Code": "US-NC-067", "subnational1Code": "US-NC", "countryCode": "US"}
    far = {"lat": 37.50, "lng": -80.10, "subnational2Code": "US-NC-999", "subnational1Code": "US-NC", "countryCode": "US"}

    async def fake_hotspots(lat, lng, dist_km=25):
        return [far, near]  # nearest isn't first in the list — must actually compare distances

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots)

    result = asyncio.run(ebird.region_for_point(36.11, -80.11))

    assert result == "US-NC-067"


def test_region_for_point_falls_back_to_subnational1_then_country(monkeypatch):
    async def fake_hotspots(lat, lng, dist_km=25):
        return [{"lat": lat, "lng": lng, "subnational1Code": "US-NC", "countryCode": "US"}]

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots)
    assert asyncio.run(ebird.region_for_point(36.1, -80.1)) == "US-NC"

    async def fake_hotspots_country_only(lat, lng, dist_km=25):
        return [{"lat": lat, "lng": lng, "countryCode": "US"}]

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots_country_only)
    assert asyncio.run(ebird.region_for_point(36.1, -80.1)) == "US"


def test_region_for_point_expands_radius_until_a_hotspot_is_found(monkeypatch):
    calls = []

    async def fake_hotspots(lat, lng, dist_km=25):
        calls.append(dist_km)
        if dist_km < 200:
            return []
        return [{"lat": lat, "lng": lng, "subnational2Code": "US-NC-067"}]

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots)

    result = asyncio.run(ebird.region_for_point(36.1, -80.1))

    assert result == "US-NC-067"
    assert calls == [10, 50, 200]  # stopped as soon as one succeeded, didn't try 500


def test_region_for_point_falls_back_to_world_when_nothing_found_at_any_radius(monkeypatch):
    async def no_hotspots(lat, lng, dist_km=25):
        return []

    monkeypatch.setattr(ebird, "get_hotspots_near", no_hotspots)

    assert asyncio.run(ebird.region_for_point(0.0, -140.0)) == "world"


def test_region_for_point_falls_back_to_world_without_crashing_when_ebird_unconfigured(monkeypatch):
    async def no_key(lat, lng, dist_km=25):
        raise EBirdConfigError("EBIRD_API_KEY is not set")

    monkeypatch.setattr(ebird, "get_hotspots_near", no_key)

    assert asyncio.run(ebird.region_for_point(36.1, -80.1)) == "world"


def _mock_ebird(monkeypatch, handler):
    monkeypatch.setenv("EBIRD_API_KEY", "test-key")
    get_settings.cache_clear()
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


def _taxon(code):
    return {"speciesCode": code, "comName": code, "sciName": code, "category": "species"}


def test_get_taxonomy_small_list_is_one_scoped_call(monkeypatch):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=[_taxon("norcar")])

    _mock_ebird(monkeypatch, handler)
    result = asyncio.run(ebird.get_taxonomy(["norcar", "amerob"]))

    assert len(calls) == 1
    assert calls[0]["species"] == "norcar,amerob"
    assert [t["speciesCode"] for t in result] == ["norcar"]


def test_get_taxonomy_large_list_filters_one_cached_full_download(monkeypatch):
    calls = []
    full = [_taxon(f"sp{i}") for i in range(2000)]

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=full)

    _mock_ebird(monkeypatch, handler)
    codes = [f"sp{i}" for i in range(0, 2000, 2)]  # 1000 codes — over the 500 batch limit

    first = asyncio.run(ebird.get_taxonomy(codes))
    second = asyncio.run(ebird.get_taxonomy(codes[:600]))

    assert len(calls) == 1  # one full download, reused by the second call
    assert "species" not in calls[0]
    assert {t["speciesCode"] for t in first} == set(codes)
    assert len(second) == 600


def test_get_taxonomy_retries_once_after_a_429(monkeypatch):
    responses = [httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200, json=[_taxon("norcar")])]

    def handler(request):
        return responses.pop(0)

    _mock_ebird(monkeypatch, handler)
    result = asyncio.run(ebird.get_taxonomy(["norcar"]))

    assert [t["speciesCode"] for t in result] == ["norcar"]
    assert responses == []


def test_get_taxonomy_raises_after_a_second_429(monkeypatch):
    import pytest

    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "0"})

    _mock_ebird(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(ebird.get_taxonomy(["norcar"]))
