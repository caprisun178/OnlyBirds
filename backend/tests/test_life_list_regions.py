import pytest

from app.dao import ebird, region_repo
from app.dao.ebird import EBirdConfigError

RAW_SPPLIST = ["norcar", "amerob", "x00776", "houspa"]

RAW_TAXONOMY = [
    {"speciesCode": "norcar", "comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "category": "species", "taxonOrder": 100.0},
    {"speciesCode": "amerob", "comName": "American Robin", "sciName": "Turdus migratorius", "category": "species", "taxonOrder": 50.0},
    {"speciesCode": "houspa", "comName": "House Sparrow", "sciName": "Passer domesticus", "category": "species", "taxonOrder": 200.0},
    {"speciesCode": "x00776", "comName": "duck sp.", "sciName": "Anatidae sp.", "category": "spuh", "taxonOrder": 75.0},
]


@pytest.fixture(autouse=True)
def clear_region_cache(monkeypatch):
    monkeypatch.setattr(region_repo, "_cache", {})


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

    import asyncio

    species = asyncio.run(region_repo.get_checklist("US-NC"))

    assert [s["code"] for s in species] == ["amerob", "norcar", "houspa"]  # taxon_order 50, 100, 200
    assert all(s["code"] != "x00776" for s in species)  # spuh dropped

    # Second call is served from cache, no second fetch.
    asyncio.run(region_repo.get_checklist("US-NC"))
    assert calls == {"spplist": 1, "taxonomy": 1}


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
    assert by_name["Northern Cardinal"]["seen"] is False
    assert by_name["Northern Cardinal"]["first_observed_at"] is None


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
