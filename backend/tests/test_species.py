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


def test_profile_assembles_taxonomy_media_and_wikipedia_text(client, monkeypatch):
    from app.dao import species_repo, wikipedia

    species_repo.species_repo._seed_taxonomy("Poecile atricapillus", "Black-capped Chickadee")

    async def fake_summary(title):
        assert title == "Black-capped_Chickadee"  # common name tried first
        return {"extract": "A small chickadee.", "source_url": "https://en.wikipedia.org/wiki/X"}

    async def fake_sections(title):
        return {"sex_differences": "Sexes look alike.", "habitat": "Forests.", "migration": "Non-migratory."}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)
    monkeypatch.setattr(wikipedia, "get_sections", fake_sections)

    resp = client.get("/species/profile", params={"scientific_name": "Poecile atricapillus"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["common_name"] == "Black-capped Chickadee"
    assert body["about"] == "A small chickadee."
    assert body["about_source_url"] == "https://en.wikipedia.org/wiki/X"
    assert body["sex_differences"] == "Sexes look alike."
    assert body["habitat"] == "Forests."
    assert body["migration"] == "Non-migratory."
    assert body["photo_url"].startswith("https://placehold.co/")  # no Commons mock configured here


def test_profile_gracefully_omits_taxonomy_for_an_unknown_species(client):
    # Default test settings have no Wikipedia mock override beyond the
    # autouse "nothing found" default — this exercises a species that was
    # never logged via eBird (e.g. iNaturalist-only), so get_taxonomy()
    # finds nothing. Should not error.
    resp = client.get("/species/profile", params={"scientific_name": "Imaginarius birdus"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["common_name"] is None
    assert body["family"] is None
    assert body["about"] is None
    assert body["sex_differences"] is None


def test_profile_falls_back_to_scientific_name_when_common_name_article_missing(client, monkeypatch):
    from app.dao import species_repo, wikipedia

    species_repo.species_repo._seed_taxonomy("Nonexistarius articlus", "Not A Real Wikipedia Page")

    calls = []

    async def fake_summary(title):
        calls.append(title)
        if title == "Nonexistarius_articlus":
            return {"extract": "Found via scientific name.", "source_url": "https://en.wikipedia.org/wiki/Y"}
        return None  # the common-name title 404s

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    resp = client.get("/species/profile", params={"scientific_name": "Nonexistarius articlus"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["about"] == "Found via scientific name."
    assert calls == ["Not_A_Real_Wikipedia_Page", "Nonexistarius_articlus"]


def test_profile_caches_content_and_does_not_refetch_wikipedia_when_fresh(client, monkeypatch):
    from app.dao import wikipedia

    calls = []

    async def fake_summary(title):
        calls.append(title)
        return {"extract": "Fetched once.", "source_url": "https://en.wikipedia.org/wiki/Z"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    first = client.get("/species/profile", params={"scientific_name": "Cardinalis cardinalis"})
    second = client.get("/species/profile", params={"scientific_name": "Cardinalis cardinalis"})
    assert first.json()["about"] == "Fetched once."
    assert second.json()["about"] == "Fetched once."
    assert len(calls) == 1  # the second request used the cache, not a second Wikipedia call


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
