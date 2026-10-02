"""`POST /species/photos` — backs Explore Map's species-filter suggestions.
Mocked at `commons.search_photo` (same layer `test_bird_photos.py` mocks at),
per docs/ebird-api.md's "no test hits a live API" rule.
"""

import asyncio

from app.dao import bird_photos, commons


def test_photos_endpoint_returns_a_guaranteed_photo_per_species(client, monkeypatch):
    async def fake_search(query):
        if query == "Turdus migratorius":
            return {"media_url": "https://upload.wikimedia.org/real-robin.jpg", "artist": "Jane Birder"}
        return None  # Corvus brachyrhynchos falls back to a placeholder

    monkeypatch.setattr(commons, "search_photo", fake_search)

    resp = client.post(
        "/species/photos",
        json=[
            {"scientific_name": "Turdus migratorius", "common_name": "American Robin"},
            {"scientific_name": "Corvus brachyrhynchos", "common_name": "American Crow"},
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    robin = next(p for p in body if p["scientific_name"] == "Turdus migratorius")
    crow = next(p for p in body if p["scientific_name"] == "Corvus brachyrhynchos")
    assert robin["photo_url"] == "https://upload.wikimedia.org/real-robin.jpg"
    assert crow["photo_url"].startswith("https://placehold.co/")  # never blank


def test_photos_endpoint_skips_entries_with_no_scientific_name(client, monkeypatch):
    async def fake_search(query):
        return None

    monkeypatch.setattr(commons, "search_photo", fake_search)

    resp = client.post("/species/photos", json=[{"common_name": "Mystery bird"}])
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_stock_photos_looks_up_each_species_concurrently(monkeypatch):
    calls = []

    async def fake_search(query):
        calls.append(query)
        return None

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    from app.models.species import SpeciesRef
    from app.services import species as species_service

    results = asyncio.run(
        species_service.get_stock_photos(
            [
                SpeciesRef(scientific_name="Turdus migratorius", common_name="American Robin"),
                SpeciesRef(scientific_name="Corvus brachyrhynchos", common_name="American Crow"),
            ]
        )
    )
    assert sorted(calls) == ["Corvus brachyrhynchos", "Turdus migratorius"]
    assert len(results) == 2
