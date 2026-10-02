import asyncio

import httpx
import pytest

from app.dao import commons, ebird, region_repo
from app.dao.ebird import EBirdConfigError

RAW_SPPLIST = ["norcar", "amerob", "x00776", "houspa"]

RAW_TAXONOMY = [
    {"speciesCode": "norcar", "comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "category": "species", "taxonOrder": 100.0, "familyComName": "Cardinals"},
    {"speciesCode": "amerob", "comName": "American Robin", "sciName": "Turdus migratorius", "category": "species", "taxonOrder": 50.0, "familyComName": "Thrushes"},
    {"speciesCode": "houspa", "comName": "House Sparrow", "sciName": "Passer domesticus", "category": "species", "taxonOrder": 200.0, "familyComName": "Old World Sparrows"},
    {"speciesCode": "x00776", "comName": "duck sp.", "sciName": "Anatidae sp.", "category": "spuh", "taxonOrder": 75.0, "familyComName": "Ducks, Geese, and Waterfowl"},
]


@pytest.fixture(autouse=True)
def clear_region_cache(monkeypatch):
    monkeypatch.setattr(region_repo, "_cache", {})


@pytest.fixture(autouse=True)
def no_exotic_lookup(monkeypatch):
    """Default the escapee-filter's lookup to "nothing flagged" so existing
    tests don't need to know about it — tests exercising the filter itself
    override this within the test."""
    async def fake_recent_obs(region_code, days_back=30):
        return []

    monkeypatch.setattr(ebird, "recent_obs_in_region", fake_recent_obs)


def test_get_checklist_drops_non_species_and_sorts_taxonomically(monkeypatch):
    calls = {"spplist": 0, "taxonomy": 0}

    async def fake_spplist(region_code):
        calls["spplist"] += 1
        assert region_code == "US-NC"
        return RAW_SPPLIST

    async def fake_taxonomy(species_codes):
        calls["taxonomy"] += 1
        assert set(species_codes) == set(RAW_SPPLIST)
        return RAW_TAXONOMY

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)

    species = asyncio.run(region_repo.get_checklist("US-NC"))

    assert [s["code"] for s in species] == ["amerob", "norcar", "houspa"]  # taxon_order 50, 100, 200
    assert all(s["code"] != "x00776" for s in species)  # spuh dropped

    by_code = {s["code"]: s for s in species}
    assert by_code["norcar"]["family_common_name"] == "Cardinals"

    # Second call is served from cache, no second fetch.
    asyncio.run(region_repo.get_checklist("US-NC"))
    assert calls == {"spplist": 1, "taxonomy": 1}


def test_get_checklist_drops_currently_flagged_escapees(monkeypatch):
    # A one-off escapee report (e.g. a farm Ostrich) still shows up in
    # /product/spplist forever — that endpoint has no countable/established
    # concept. Regression test for that exact real-world case.
    async def fake_spplist(region_code):
        return RAW_SPPLIST + ["ostric2"]

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY + [
            {"speciesCode": "ostric2", "comName": "Common Ostrich", "sciName": "Struthio camelus",
             "category": "species", "taxonOrder": 2.0, "familyComName": "Ostriches"},
        ]

    async def fake_recent_obs(region_code, days_back):
        assert days_back == 30
        return [
            {"speciesCode": "ostric2", "exoticCategory": "X"},  # escapee — dropped
            {"speciesCode": "houspa", "exoticCategory": "N"},  # naturalized — kept
            {"speciesCode": "amerob"},  # no exoticCategory at all — a regular native record, kept
        ]

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)
    monkeypatch.setattr(ebird, "recent_obs_in_region", fake_recent_obs)

    species = asyncio.run(region_repo.get_checklist("US"))
    codes = {s["code"] for s in species}

    assert "ostric2" not in codes
    assert {"houspa", "amerob", "norcar"} <= codes


def test_get_checklist_drops_hand_maintained_exclusions_even_without_a_live_flag(monkeypatch):
    # The exact gap app/data/exotic_exclusions.py exists for: a species whose
    # only-ever escapee report is outside eBird's 30-day recent-observations
    # window has no live `exoticCategory` signal at all — `no_exotic_lookup`
    # (autouse) simulates that by returning no recent observations whatsoever.
    async def fake_spplist(region_code):
        return RAW_SPPLIST + ["ostric2"]

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY + [
            {"speciesCode": "ostric2", "comName": "Common Ostrich", "sciName": "Struthio camelus",
             "category": "species", "taxonOrder": 2.0, "familyComName": "Ostriches"},
        ]

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)

    species = asyncio.run(region_repo.get_checklist("US"))
    codes = {s["code"] for s in species}

    assert "ostric2" not in codes  # caught by the manual list, not the live lookup
    assert {"houspa", "amerob", "norcar"} <= codes  # everything else unaffected


def test_get_checklist_tolerates_escapee_lookup_failure(monkeypatch):
    async def fake_spplist(region_code):
        return RAW_SPPLIST

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY

    async def failing_recent_obs(region_code, days_back):
        raise httpx.HTTPError("eBird had a bad day")

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)
    monkeypatch.setattr(ebird, "recent_obs_in_region", failing_recent_obs)

    # The escapee-filter enrichment failing shouldn't take the whole
    # checklist down with it.
    species = asyncio.run(region_repo.get_checklist("US-NC"))
    assert len(species) == 3


def test_region_checklist_endpoint_marks_seen_species(client, monkeypatch):
    async def fake_spplist(region_code):
        return RAW_SPPLIST

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)

    client.post(
        "/observations",
        json={
            "user_id": "u1",
            "species": {"common_name": "American Robin", "scientific_name": "Turdus migratorius"},
            "observed_at": "2026-05-01T08:00:00+00:00",
            "photo_url": "https://example.com/robin.jpg",
            "lat": 35.9,
            "lng": -79.05,
            "source": "manual",
        },
    )

    resp = client.get("/regions/US-NC/checklist", params={"user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["seen"] == 1

    by_name = {s["common_name"]: s for s in body["species"]}
    assert by_name["American Robin"]["seen"] is True
    assert by_name["American Robin"]["photo_url"] == "https://example.com/robin.jpg"
    assert by_name["American Robin"]["family_common_name"] == "Thrushes"
    assert by_name["Northern Cardinal"]["seen"] is False
    assert by_name["Northern Cardinal"]["first_observed_at"] is None


def test_region_checklist_falls_back_to_stock_photo_when_user_has_none(client, monkeypatch):
    async def fake_spplist(region_code):
        return RAW_SPPLIST

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY

    async def fake_search_photo(query):
        assert query == "Turdus migratorius"
        return {
            "media_url": "https://upload.wikimedia.org/real-robin.jpg",
            "artist": "Jane Birder",
            "license": "CC BY-SA 3.0",
        }

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)
    monkeypatch.setattr(commons, "search_photo", fake_search_photo)

    client.post(
        "/observations",
        json={
            "user_id": "u1",
            "species": {"common_name": "American Robin", "scientific_name": "Turdus migratorius"},
            "observed_at": "2026-05-01T08:00:00+00:00",
            "lat": 35.9,
            "lng": -79.05,
            "source": "manual",
        },
    )

    resp = client.get("/regions/US-NC/checklist", params={"user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()

    by_name = {s["common_name"]: s for s in body["species"]}
    assert by_name["American Robin"]["seen"] is True
    assert by_name["American Robin"]["photo_url"] == "https://upload.wikimedia.org/real-robin.jpg"
    assert by_name["American Robin"]["photo_attribution"] == "Jane Birder / Wikimedia Commons (CC BY-SA 3.0)"
    # Not-seen species never get a stock-photo lookup.
    assert by_name["Northern Cardinal"]["photo_url"] is None


def test_region_checklist_without_user_id_is_all_unseen(client, monkeypatch):
    async def fake_spplist(region_code):
        return RAW_SPPLIST

    async def fake_taxonomy(species_codes):
        return RAW_TAXONOMY

    monkeypatch.setattr(ebird, "get_region_spplist", fake_spplist)
    monkeypatch.setattr(ebird, "get_taxonomy", fake_taxonomy)

    resp = client.get("/regions/US-NC/checklist")
    body = resp.json()
    assert body["seen"] == 0
    assert all(not s["seen"] for s in body["species"])


def test_list_regions_maps_ebird_response(client, monkeypatch):
    async def fake_children(parent_code, region_type):
        assert (parent_code, region_type) == ("US", "subnational1")
        return [{"code": "US-NC", "name": "North Carolina"}, {"code": "US-WA", "name": "Washington"}]

    monkeypatch.setattr(ebird, "get_region_children", fake_children)

    resp = client.get("/regions", params={"parent": "US", "type": "subnational1"})
    assert resp.status_code == 200
    assert resp.json() == [
        {"code": "US-NC", "name": "North Carolina"},
        {"code": "US-WA", "name": "Washington"},
    ]


def test_regions_endpoint_returns_503_when_ebird_key_missing(client, monkeypatch):
    async def raise_config_error(*args, **kwargs):
        raise EBirdConfigError("EBIRD_API_KEY is not set")

    monkeypatch.setattr(ebird, "get_region_children", raise_config_error)

    resp = client.get("/regions", params={"parent": "US", "type": "subnational1"})
    assert resp.status_code == 503
