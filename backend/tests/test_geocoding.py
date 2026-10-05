import asyncio

import httpx

from app.dao import nominatim

RAW_SEARCH_RESULT = [
    {
        "display_name": "Discovery Park, 3801, Magnolia, Seattle, King County, Washington, 98199, United States",
        "lat": "47.6618111",
        "lon": "-122.4219145",
    }
]

RAW_REVERSE_RESULT = {
    "display_name": "1181, Discovery Park Boulevard, Magnolia, Seattle, King County, Washington, 98199, United States",
    "lat": "47.6618837",
    "lon": "-122.4219008",
}


def test_search_normalizes_nominatim_result(client, monkeypatch):
    async def fake_search(query, limit=5):
        assert query == "Discovery Park Seattle"
        return RAW_SEARCH_RESULT

    monkeypatch.setattr(nominatim, "search", fake_search)

    resp = client.get("/geocode/search", params={"q": "Discovery Park Seattle"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["display_name"].startswith("Discovery Park")
    assert body[0]["lat"] == 47.6618111
    assert body[0]["lng"] == -122.4219145


def test_search_requires_a_query(client):
    resp = client.get("/geocode/search")
    assert resp.status_code == 422


def test_reverse_normalizes_nominatim_result(client, monkeypatch):
    async def fake_reverse(lat, lng):
        assert (lat, lng) == (47.6618, -122.4219)
        return RAW_REVERSE_RESULT

    monkeypatch.setattr(nominatim, "reverse", fake_reverse)

    resp = client.get("/geocode/reverse", params={"lat": 47.6618, "lng": -122.4219})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lat"] == 47.6618837
    assert body["lng"] == -122.4219008


def test_reverse_returns_null_when_nominatim_has_nothing(client, monkeypatch):
    async def fake_reverse(lat, lng):
        return None

    monkeypatch.setattr(nominatim, "reverse", fake_reverse)

    resp = client.get("/geocode/reverse", params={"lat": 0, "lng": 0})
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_client_is_reused_across_calls(monkeypatch):
    # Regression: _client() used to open (and immediately close) a brand new
    # httpx.AsyncClient per call — a fresh TCP+TLS handshake to Nominatim on
    # every keystroke once Explore Map's search went live-as-you-type.
    # Real, measured slowness followed. _get_client() should hand back the
    # same instance every time instead.
    monkeypatch.setattr(nominatim, "_client", None)
    first = nominatim._get_client()
    second = nominatim._get_client()
    assert first is second


def test_search_caches_identical_queries_briefly(monkeypatch):
    # Regression: live-as-you-type search can legitimately re-request the
    # exact same string (pause then resume, backspace to an earlier prefix,
    # reopening a just-used search) — each of those should be served from
    # cache, not hit Nominatim (and its ~1 req/sec usage-policy ceiling)
    # again.
    monkeypatch.setattr(nominatim, "_client", None)
    monkeypatch.setattr(nominatim, "_search_cache", {})

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=RAW_SEARCH_RESULT)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        nominatim.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(
            base_url=kwargs.get("base_url", ""),
            timeout=kwargs.get("timeout"),
            headers=kwargs.get("headers"),
            transport=httpx.MockTransport(handler),
        ),
    )

    first = asyncio.run(nominatim.search("Discovery Park"))
    second = asyncio.run(nominatim.search("Discovery Park"))

    assert first == second == RAW_SEARCH_RESULT
    assert call_count == 1  # the second call was served from cache
