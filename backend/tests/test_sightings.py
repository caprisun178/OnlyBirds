"""GET /sightings/nearby — merges eBird, iNaturalist, and our own logged
observations. eBird/iNat are stubbed out at the dao layer (no live calls,
per docs/ebird-api.md's offline-tests rule); our own observations go through
the same `InMemoryObservationRepo` the `client` fixture isolates per test.
"""

from datetime import datetime, timedelta, timezone

from app.dao import ebird, inaturalist

SEATTLE = {"lat": 47.6062, "lng": -122.3321}
FAR_AWAY = {"lat": 40.7128, "lng": -74.0060}  # New York — outside any reasonable radius from Seattle


def _stub_external_sources(monkeypatch):
    async def no_ebird(lat, lng, dist_km=25, days_back=7):
        return []

    async def no_inat(lat, lng, radius_km=25, days_back=None):
        return []

    monkeypatch.setattr(ebird, "get_nearby_bird_sightings", no_ebird)
    monkeypatch.setattr(inaturalist, "get_nearby_observations", no_inat)


def _log_observation(client, **overrides):
    payload = {
        "user_id": "u1",
        "species": {"common_name": "American Robin", "scientific_name": "Turdus migratorius"},
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
        "status": "logged",
        **SEATTLE,
        **overrides,
    }
    resp = client.post("/observations", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_nearby_includes_a_logged_observation_within_radius(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    _log_observation(client, location_name="Discovery Park", notes="Heard calling from the big oak near the entrance")

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["source"] == "manual"
    assert body[0]["location_name"] == "Discovery Park"
    assert body[0]["notes"] == "Heard calling from the big oak near the entrance"
    assert body[0]["species"]["common_name"] == "American Robin"


def test_nearby_excludes_a_logged_observation_outside_radius(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    _log_observation(client, **FAR_AWAY)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25})
    assert resp.status_code == 200
    assert resp.json() == []


def test_nearby_excludes_observations_outside_the_days_back_window(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    _log_observation(client, observed_at=old_date)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25, "days_back": 7})
    assert resp.status_code == 200
    assert resp.json() == []


def test_nearby_excludes_non_logged_observations(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    _log_observation(client, status="draft")

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25})
    assert resp.status_code == 200
    assert resp.json() == []


def test_source_filter_manual_excludes_ebird_and_inat(client, monkeypatch):
    async def fake_ebird(lat, lng, dist_km=25, days_back=7):
        return [{
            "speciesCode": "norcar", "comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis",
            "locName": "Some Park", "obsDt": "2026-09-01 08:00", "subId": "S1", "lat": lat, "lng": lng,
        }]

    async def no_inat(lat, lng, radius_km=25, days_back=None):
        return []

    monkeypatch.setattr(ebird, "get_nearby_bird_sightings", fake_ebird)
    monkeypatch.setattr(inaturalist, "get_nearby_observations", no_inat)
    _log_observation(client)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25, "source": "manual"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["source"] == "manual"


def test_source_filter_ebird_excludes_manual(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    _log_observation(client)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25, "source": "ebird"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_source_filter_all_includes_manual(client, monkeypatch):
    _stub_external_sources(monkeypatch)
    _log_observation(client)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25, "source": "all"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_days_back_reaches_the_inaturalist_call(client, monkeypatch):
    # Regression: iNaturalist results had no date filtering at all, so a
    # "Since: Last 7 days" request could still surface an 8-month-old
    # sighting (a real report) — days_back must actually reach the DAO call,
    # not just the eBird one.
    captured = {}

    async def no_ebird(lat, lng, dist_km=25, days_back=7):
        return []

    async def capturing_inat(lat, lng, radius_km=25, days_back=None):
        captured["days_back"] = days_back
        return []

    monkeypatch.setattr(ebird, "get_nearby_bird_sightings", no_ebird)
    monkeypatch.setattr(inaturalist, "get_nearby_observations", capturing_inat)

    resp = client.get("/sightings/nearby", params={**SEATTLE, "radius_km": 25, "days_back": 14})
    assert resp.status_code == 200
    assert captured["days_back"] == 14
