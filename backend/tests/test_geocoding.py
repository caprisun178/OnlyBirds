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
