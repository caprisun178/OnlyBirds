"""`GET /trip/plan` and `app/services/trip.py`. eBird/iNaturalist are stubbed
at the dao layer (no live calls, per docs/ebird-api.md's offline-tests
rule); life-list cross-referencing goes through the same isolated
`InMemoryObservationRepo` the `client` fixture gives every test.
"""

import asyncio
from datetime import date

import httpx
import pytest

from app.dao import ebird, inaturalist
from app.dao.ebird import EBirdConfigError


@pytest.fixture(autouse=True)
def _clear_hotspot_sightings_cache():
    # hotspot_sightings() now caches per (lat, lng, radius_km, dates, loc_id)
    # — several tests below reuse the exact same coordinates/dates with
    # different mocks, which would otherwise silently return a different
    # test's cached result instead of exercising their own.
    from app.services.trip import _hotspot_sightings_cache

    _hotspot_sightings_cache.clear()
    yield
    _hotspot_sightings_cache.clear()


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


def test_species_window_is_last_year_padded_30_days_each_side(client, monkeypatch):
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
    # One year earlier (2025-10-15..2025-10-20), then padded 30 days each way.
    assert captured["d1"] == "2025-09-15"
    assert captured["d2"] == "2025-11-19"


def test_one_year_earlier_handles_feb_29_in_a_non_leap_year():
    from app.services.trip import _one_year_earlier

    # 2028 is a leap year; 2027 isn't — Feb 29, 2028 has no real "one year
    # earlier" date, so this should nudge back rather than crash.
    assert _one_year_earlier(date(2028, 2, 29)) == date(2027, 2, 28)


def test_one_year_earlier_normal_case():
    from app.services.trip import _one_year_earlier

    assert _one_year_earlier(date(2026, 10, 15)) == date(2025, 10, 15)


def test_last_year_window_pads_30_days_each_side():
    from app.services.trip import _last_year_window

    d1, d2 = _last_year_window(date(2026, 10, 15), date(2026, 10, 20))
    assert d1 == date(2025, 9, 15)
    assert d2 == date(2025, 11, 19)


def test_last_year_window_pads_a_single_day_trip_into_a_real_range():
    from app.services.trip import _last_year_window

    # The case that motivated the padding: a single-day trip (start == end)
    # shifted back exactly one year is a 1-day search window — too thin to
    # reliably return anything. Padded, it's a real 61-day range instead.
    d1, d2 = _last_year_window(date(2026, 10, 25), date(2026, 10, 25))
    assert d1 == date(2025, 9, 25)
    assert d2 == date(2025, 11, 24)


RAW_SIGHTING_OLD = {
    "id": 1,
    "place_guess": "Bethania--Black Walnut Bottom",
    "time_observed_at": "2025-10-16T08:00:00+00:00",
    "geojson": {"type": "Point", "coordinates": [-80.339, 36.178]},
    "photos": [],
    "taxon": {"id": 1, "name": "Cardinalis cardinalis", "preferred_common_name": "Northern Cardinal", "iconic_taxon_name": "Aves"},
}
RAW_SIGHTING_NEWER = {
    "id": 2,
    "place_guess": "Bethania--Black Walnut Bottom",
    "time_observed_at": "2025-10-18T08:00:00+00:00",
    "geojson": {"type": "Point", "coordinates": [-80.339, 36.178]},
    "photos": [],
    "taxon": {"id": 2, "name": "Cyanocitta cristata", "preferred_common_name": "Blue Jay", "iconic_taxon_name": "Aves"},
}


def test_hotspot_sightings_returns_observations_sorted_newest_first(client, monkeypatch):
    async def fake_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return [RAW_SIGHTING_OLD, RAW_SIGHTING_NEWER]

    monkeypatch.setattr(inaturalist, "get_nearby_observations", fake_nearby)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.178, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [o["species"]["common_name"] for o in body] == ["Blue Jay", "Northern Cardinal"]
    assert body[0]["lat"] == 36.178 and body[0]["lng"] == -80.339


def test_hotspot_sightings_window_is_last_year_padded_30_days_each_side(client, monkeypatch):
    captured = {}

    async def capturing_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        captured["d1"] = d1
        captured["d2"] = d2
        return []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", capturing_nearby)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.178, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    assert captured["d1"] == "2025-09-15"
    assert captured["d2"] == "2025-11-19"


def test_hotspot_sightings_rejects_end_date_before_start_date(client, monkeypatch):
    async def fake_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", fake_nearby)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.178, "lng": -80.339, "start_date": "2026-10-20", "end_date": "2026-10-15"},
    )
    assert resp.status_code == 422


RAW_EBIRD_HISTORIC = {
    "speciesCode": "blujay",
    "comName": "Blue Jay",
    "sciName": "Cyanocitta cristata",
    "locName": "Salem Lake",
    "obsDt": "2025-10-19 09:00",
    "subId": "S999",
    "lat": 36.178,
    "lng": -80.339,
}


def test_hotspot_sightings_merges_in_ebird_when_loc_id_given(client, monkeypatch):
    async def fake_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return [RAW_SIGHTING_OLD]  # Oct 16, Northern Cardinal

    # One eBird row on the very first day of eBird's (narrower, ±7-day)
    # window, none on the rest — just needs to prove the merge happens, not
    # exercise all ~15 days.
    async def fake_historic(loc_id, d):
        return [RAW_EBIRD_HISTORIC] if d == date(2025, 10, 8) else []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", fake_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", fake_historic)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={
            "lat": 36.178, "lng": -80.339,
            "start_date": "2026-10-15", "end_date": "2026-10-20",
            "loc_id": "L385792",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    sources = {o["source"] for o in body}
    assert sources == {"inat", "ebird"}
    assert any(o["species"]["common_name"] == "Blue Jay" and o["source"] == "ebird" for o in body)
    assert any(o["species"]["common_name"] == "Northern Cardinal" and o["source"] == "inat" for o in body)


def test_hotspot_sightings_omits_ebird_when_no_loc_id_given(client, monkeypatch):
    async def fake_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return []

    async def unexpected_call(loc_id, d):
        raise AssertionError("eBird shouldn't be called when no loc_id is given")

    monkeypatch.setattr(inaturalist, "get_nearby_observations", fake_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", unexpected_call)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.178, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_hotspot_sightings_degrades_gracefully_without_an_ebird_key(client, monkeypatch):
    async def fake_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return [RAW_SIGHTING_OLD]

    async def no_key(loc_id, d):
        raise EBirdConfigError("EBIRD_API_KEY is not set")

    monkeypatch.setattr(inaturalist, "get_nearby_observations", fake_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", no_key)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={
            "lat": 36.178, "lng": -80.339,
            "start_date": "2026-10-15", "end_date": "2026-10-20",
            "loc_id": "L385792",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1  # the iNaturalist result still comes through
    assert body[0]["source"] == "inat"


def test_hotspot_sightings_degrades_gracefully_when_inaturalist_fails(client, monkeypatch):
    # Confirmed live: a real httpx.RemoteProtocolError ("Server disconnected
    # without sending a response") from iNaturalist, mid-session, alongside
    # a concurrently-running, otherwise-successful eBird fetch — this used
    # to 502 the whole request and throw away that eBird data too.
    async def flaky_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    async def fake_historic(loc_id, d):
        return [RAW_EBIRD_HISTORIC] if d == date(2025, 10, 8) else []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", flaky_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", fake_historic)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={
            "lat": 36.178, "lng": -80.339,
            "start_date": "2026-10-15", "end_date": "2026-10-20",
            "loc_id": "L385792",
        },
    )
    assert resp.status_code == 200  # not a 502 — the eBird half still comes through
    body = resp.json()
    assert len(body) == 1
    assert body[0]["source"] == "ebird"


def test_hotspot_sightings_does_not_cache_a_failed_inaturalist_call(client, monkeypatch):
    call_count = {"inat": 0}
    should_fail = {"value": True}

    async def sometimes_flaky_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        call_count["inat"] += 1
        if should_fail["value"]:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return [RAW_SIGHTING_OLD]

    monkeypatch.setattr(inaturalist, "get_nearby_observations", sometimes_flaky_nearby)

    params = {"lat": 36.178, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"}
    first = client.get("/trip/hotspot-sightings", params=params)
    assert first.status_code == 200
    assert first.json() == []  # degraded, not cached

    should_fail["value"] = False
    second = client.get("/trip/hotspot-sightings", params=params)
    assert second.status_code == 200
    assert len(second.json()) == 1  # a fresh attempt, not served from a stale cached failure
    assert call_count["inat"] == 2  # both requests actually hit iNaturalist


def test_ebird_historic_window_calls_once_per_day_in_range():
    import asyncio

    from app.services.trip import _ebird_historic_window

    calls = []

    async def fake_historic(loc_id, d):
        calls.append(d)
        return []

    import app.dao.ebird as ebird_module
    real_fn = ebird_module.get_historic_checklist
    ebird_module.get_historic_checklist = fake_historic
    try:
        asyncio.run(_ebird_historic_window("L1", date(2026, 1, 1), date(2026, 1, 5)))
    finally:
        ebird_module.get_historic_checklist = real_fn

    assert sorted(calls) == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)]


def test_hotspot_sightings_ebird_window_is_narrower_than_inaturalists(client, monkeypatch):
    captured = {"inat": None, "ebird_days": []}

    async def capturing_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        captured["inat"] = (d1, d2)
        return []

    async def capturing_historic(loc_id, d):
        captured["ebird_days"].append(d)
        return []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", capturing_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", capturing_historic)

    resp = client.get(
        "/trip/hotspot-sightings",
        params={
            "lat": 36.178, "lng": -80.339,
            "start_date": "2026-10-15", "end_date": "2026-10-20",
            "loc_id": "L385792",
        },
    )
    assert resp.status_code == 200
    # iNaturalist keeps the full ±30-day pad (one call either way, so no cost
    # to widening it) — eBird gets the narrower ±7-day pad (one real HTTP
    # call per day, so narrower directly means faster).
    assert captured["inat"] == ("2025-09-15", "2025-11-19")
    assert min(captured["ebird_days"]) == date(2025, 10, 8)
    assert max(captured["ebird_days"]) == date(2025, 10, 27)
    assert len(captured["ebird_days"]) == 20  # Oct 8..27 inclusive


def test_hotspot_sightings_caches_a_repeat_call_for_the_same_hotspot_and_dates(client, monkeypatch):
    call_count = {"inat": 0, "ebird": 0}

    async def counting_nearby(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        call_count["inat"] += 1
        return [RAW_SIGHTING_OLD]

    async def counting_historic(loc_id, d):
        call_count["ebird"] += 1
        return []

    monkeypatch.setattr(inaturalist, "get_nearby_observations", counting_nearby)
    monkeypatch.setattr(ebird, "get_historic_checklist", counting_historic)

    params = {
        "lat": 36.178, "lng": -80.339,
        "start_date": "2026-10-15", "end_date": "2026-10-20",
        "loc_id": "L385792",
    }
    first = client.get("/trip/hotspot-sightings", params=params)
    second = client.get("/trip/hotspot-sightings", params=params)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()
    assert call_count["inat"] == 1  # not re-fetched on the second, identical request
    assert call_count["ebird"] == 20  # (one per day in the ±7-day window) — also not re-fetched


def test_hotspot_sightings_does_not_cache_across_different_hotspots(client, monkeypatch):
    async def nearby_by_lat(lat, lng, radius_km=25, per_page=30, d1=None, d2=None):
        return [RAW_SIGHTING_OLD] if lat == 36.178 else [RAW_SIGHTING_NEWER]

    monkeypatch.setattr(inaturalist, "get_nearby_observations", nearby_by_lat)

    first = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.178, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    second = client.get(
        "/trip/hotspot-sightings",
        params={"lat": 36.2, "lng": -80.339, "start_date": "2026-10-15", "end_date": "2026-10-20"},
    )
    assert first.json()[0]["species"]["common_name"] == "Northern Cardinal"
    assert second.json()[0]["species"]["common_name"] == "Blue Jay"
