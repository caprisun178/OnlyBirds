"""`GET /trip/plan` and `app/services/trip.py`. eBird/iNaturalist are stubbed
at the dao layer (no live calls, per docs/ebird-api.md's offline-tests
rule); life-list cross-referencing goes through the same isolated
`InMemoryObservationRepo` the `client` fixture gives every test.
"""

import asyncio
from datetime import date

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError

RAW_HOTSPOT_SMALL = {"locId": "L1", "locName": "Small Spot", "lat": 36.1, "lng": -80.3, "numSpeciesAllTime": 50}
RAW_HOTSPOT_BIG = {"locId": "L2", "locName": "Big Spot", "lat": 36.2, "lng": -80.4, "numSpeciesAllTime": 200}

RAW_SPECIES_COUNT = {
    "count": 12,
    "taxon": {
        "id": 1,
        "name": "Cardinalis cardinalis",
        "preferred_common_name": "Northern Cardinal",
        "iconic_taxon_name": "Aves",
    },
}


def _stub_sources(monkeypatch, hotspots=None, species=None):
    async def fake_hotspots(lat, lng, radius_km=25):
        return hotspots if hotspots is not None else [RAW_HOTSPOT_SMALL, RAW_HOTSPOT_BIG]

    async def fake_species_counts(lat, lng, radius_km=25, d1=None, d2=None, per_page=20):
        return species if species is not None else [RAW_SPECIES_COUNT]

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots)
    monkeypatch.setattr(inaturalist, "get_species_counts", fake_species_counts)


def test_plan_trip_rejects_end_date_before_start_date(client, monkeypatch):
    _stub_sources(monkeypatch)
    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-20", "end_date": "2026-10-15"},
    )
    assert resp.status_code == 422


def test_plan_trip_returns_hotspots_sorted_by_popularity(client, monkeypatch):
    _stub_sources(monkeypatch)
    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    hotspots = resp.json()["hotspots"]
    assert [h["name"] for h in hotspots] == ["Big Spot", "Small Spot"]  # most species_all_time first


def test_plan_trip_returns_likely_species(client, monkeypatch):
    _stub_sources(monkeypatch)
    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    species = resp.json()["likely_species"]
    assert len(species) == 1
    assert species[0]["species"]["common_name"] == "Northern Cardinal"
    assert species[0]["observation_count"] == 12
    assert species[0]["new_for_you"] is None  # no user_id given — not guessed at


def test_plan_trip_marks_new_for_you_against_the_callers_life_list(client, monkeypatch):
    _stub_sources(monkeypatch, species=[RAW_SPECIES_COUNT])

    # Log this species for u1 — it should come back new_for_you=False.
    resp = client.post(
        "/observations",
        json={
            "user_id": "u1",
            "species": {"common_name": "Northern Cardinal", "scientific_name": "Cardinalis cardinalis"},
            "observed_at": "2026-01-01T08:00:00+00:00",
            "lat": 36.1, "lng": -80.3,
            "source": "manual",
            "status": "logged",
        },
    )
    assert resp.status_code == 201

    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.json()["likely_species"][0]["new_for_you"] is False


def test_plan_trip_marks_unseen_species_as_new_for_you(client, monkeypatch):
    _stub_sources(monkeypatch, species=[RAW_SPECIES_COUNT])

    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.json()["likely_species"][0]["new_for_you"] is True


def test_plan_trip_degrades_gracefully_without_an_ebird_key(client, monkeypatch):
    async def no_key(lat, lng, radius_km=25):
        raise EBirdConfigError("EBIRD_API_KEY is not set")

    monkeypatch.setattr(ebird, "get_hotspots_near", no_key)
    _stub_sources_species_only(monkeypatch)

    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    assert resp.json()["hotspots"] == []


def _stub_sources_species_only(monkeypatch):
    async def fake_species_counts(lat, lng, radius_km=25, d1=None, d2=None, per_page=20):
        return [RAW_SPECIES_COUNT]

    monkeypatch.setattr(inaturalist, "get_species_counts", fake_species_counts)


def test_species_window_uses_the_same_dates_one_year_earlier(client, monkeypatch):
    captured = {}

    async def fake_hotspots(lat, lng, radius_km=25):
        return []

    async def capturing_species_counts(lat, lng, radius_km=25, d1=None, d2=None, per_page=20):
        captured["d1"] = d1
        captured["d2"] = d2
        return []

    monkeypatch.setattr(ebird, "get_hotspots_near", fake_hotspots)
    monkeypatch.setattr(inaturalist, "get_species_counts", capturing_species_counts)

    resp = client.get(
        "/trip/plan",
        params={"lat": 36.1, "lng": -80.3, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    assert captured["d1"] == "2025-10-15"
    assert captured["d2"] == "2025-10-20"


def test_one_year_earlier_handles_feb_29_in_a_non_leap_year():
    from app.services.trip import _one_year_earlier

    # 2028 is a leap year; 2027 isn't — Feb 29, 2028 has no real "one year
    # earlier" date, so this should nudge back rather than crash.
    assert _one_year_earlier(date(2028, 2, 29)) == date(2027, 2, 28)


def test_one_year_earlier_normal_case():
    from app.services.trip import _one_year_earlier

    assert _one_year_earlier(date(2026, 10, 15)) == date(2025, 10, 15)
