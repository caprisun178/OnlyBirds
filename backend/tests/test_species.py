"""`POST /species/photos` — backs Explore Map's species-filter suggestions.
Mocked at `commons.search_photo` (same layer `test_bird_photos.py` mocks at),
per docs/ebird-api.md's "no test hits a live API" rule.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from app.dao import bird_photos, commons, species_repo, wikipedia


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


def test_get_about_fetches_by_common_name_first(monkeypatch):
    calls = []

    async def fake_summary(title):
        calls.append(title)
        return {"extract": "A small songbird.", "content_url": "https://en.wikipedia.org/wiki/x"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Poecile atricapillus", "Black-capped Chickadee"))
    assert result == {"about": "A small songbird.", "about_source_url": "https://en.wikipedia.org/wiki/x"}
    assert calls == ["Black-capped Chickadee"]  # scientific-name fallback never needed


def test_get_about_falls_back_to_scientific_name(monkeypatch):
    calls = []

    async def fake_summary(title):
        calls.append(title)
        if title == "Black-capped Chickadee":
            return None  # no such article under the common name
        return {"extract": "A small songbird.", "content_url": "https://en.wikipedia.org/wiki/x"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Poecile atricapillus", "Black-capped Chickadee"))
    assert result["about"] == "A small songbird."
    assert calls == ["Black-capped Chickadee", "Poecile atricapillus"]


def test_get_about_returns_nulls_when_wikipedia_has_nothing_under_either_name(monkeypatch):
    async def fake_summary(title):
        return None

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Fictional birdus", "Fictional Bird"))
    assert result == {"about": None, "about_source_url": None}


def test_get_about_uses_the_cache_instead_of_refetching(monkeypatch):
    calls = []

    async def fake_summary(title):
        calls.append(title)
        return {"extract": "fresh", "content_url": "https://en.wikipedia.org/wiki/x"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)
    asyncio.run(
        species_repo.species_content_repo.upsert("Poecile atricapillus", "cached text", "https://en.wikipedia.org/wiki/cached")
    )

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Poecile atricapillus", "Black-capped Chickadee"))
    assert result == {"about": "cached text", "about_source_url": "https://en.wikipedia.org/wiki/cached"}
    assert calls == []  # never re-fetched


def test_get_about_refetches_once_the_cache_is_stale(monkeypatch):
    async def fake_summary(title):
        return {"extract": "fresh", "content_url": "https://en.wikipedia.org/wiki/fresh"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    async def seed_stale_cache():
        await species_repo.species_content_repo.upsert("Poecile atricapillus", "stale text", "https://en.wikipedia.org/wiki/stale")
        entry = await species_repo.species_content_repo.get("Poecile atricapillus")
        entry["fetched_at"] = datetime.now(timezone.utc) - timedelta(days=31)

    asyncio.run(seed_stale_cache())

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Poecile atricapillus", "Black-capped Chickadee"))
    assert result == {"about": "fresh", "about_source_url": "https://en.wikipedia.org/wiki/fresh"}


def test_get_about_falls_back_to_nulls_on_a_transient_wikipedia_failure(monkeypatch):
    async def fake_summary(title):
        raise wikipedia.WikipediaUnavailable("429 Too Many Requests")

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Fictional birdus", "Fictional Bird"))
    assert result == {"about": None, "about_source_url": None}


def test_get_about_falls_back_to_stale_cache_on_a_transient_wikipedia_failure(monkeypatch):
    async def seed_stale_cache():
        await species_repo.species_content_repo.upsert("Poecile atricapillus", "stale but real text", "https://en.wikipedia.org/wiki/stale")
        entry = await species_repo.species_content_repo.get("Poecile atricapillus")
        entry["fetched_at"] = datetime.now(timezone.utc) - timedelta(days=31)

    asyncio.run(seed_stale_cache())

    async def fake_summary(title):
        raise wikipedia.WikipediaUnavailable("429 Too Many Requests")

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    result = asyncio.run(species_service.get_about("Poecile atricapillus", "Black-capped Chickadee"))
    assert result == {"about": "stale but real text", "about_source_url": "https://en.wikipedia.org/wiki/stale"}


def test_get_about_does_not_cache_a_transient_failure_as_permanently_empty(monkeypatch):
    calls = []

    async def fake_summary(title):
        calls.append(title)
        raise wikipedia.WikipediaUnavailable("429 Too Many Requests")

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    asyncio.run(species_service.get_about("Fictional birdus", "Fictional Bird"))
    assert asyncio.run(species_repo.species_content_repo.get("Fictional birdus")) is None  # never written


def test_get_profile_does_not_lose_photo_and_audio_when_wikipedia_fails(monkeypatch):
    # The real bug this guards: all three lookups share one asyncio.gather()
    # — an uncaught exception from `about` used to cancel photo/audio too,
    # even though they have nothing to do with Wikipedia.
    async def fake_search_photo(query, *, exclude_media_urls=frozenset()):
        return {"media_url": "https://upload.wikimedia.org/jay.jpg", "artist": "Jane Birder"}

    async def fake_search_audio(query):
        return {"media_url": "https://upload.wikimedia.org/jay.ogg", "artist": "John Birder"}

    async def fake_summary(title):
        raise wikipedia.WikipediaUnavailable("429 Too Many Requests")

    monkeypatch.setattr(commons, "search_photo", fake_search_photo)
    monkeypatch.setattr(commons, "search_audio", fake_search_audio)
    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    profile = asyncio.run(species_service.get_profile("Cyanocitta cristata", "Blue Jay", "Crows, Jays, and Magpies"))
    assert profile["photo_url"] == "https://upload.wikimedia.org/jay.jpg"
    assert profile["audio_url"] == "https://upload.wikimedia.org/jay.ogg"
    assert profile["about"] is None


def test_get_profile_assembles_photo_audio_about_and_habitat(monkeypatch):
    async def fake_search_photo(query, *, exclude_media_urls=frozenset()):
        return {"media_url": "https://upload.wikimedia.org/jay.jpg", "artist": "Jane Birder"}

    async def fake_search_audio(query):
        return {"media_url": "https://upload.wikimedia.org/jay.ogg", "artist": "John Birder"}

    async def fake_summary(title):
        return {"extract": "A loud, intelligent songbird.", "content_url": "https://en.wikipedia.org/wiki/blue_jay"}

    monkeypatch.setattr(commons, "search_photo", fake_search_photo)
    monkeypatch.setattr(commons, "search_audio", fake_search_audio)
    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    from app.services import species as species_service

    profile = asyncio.run(species_service.get_profile("Cyanocitta cristata", "Blue Jay", "Crows, Jays, and Magpies"))
    assert profile["scientific_name"] == "Cyanocitta cristata"
    assert profile["common_name"] == "Blue Jay"
    assert profile["family"] == "Crows, Jays, and Magpies"
    assert profile["habitat"] == ["backyard", "woodland"]  # from app/data/birds.py's curated set
    assert profile["photo_url"] == "https://upload.wikimedia.org/jay.jpg"
    assert profile["audio_url"] == "https://upload.wikimedia.org/jay.ogg"
    assert profile["about"] == "A loud, intelligent songbird."
    assert profile["about_source_url"] == "https://en.wikipedia.org/wiki/blue_jay"


def test_get_profile_reports_no_habitat_for_a_species_outside_the_curated_set(monkeypatch):
    from app.services import species as species_service

    profile = asyncio.run(species_service.get_profile("Dendroplex kienerii", "Zimmer's Woodcreeper", None))
    assert profile["habitat"] is None


def test_species_profile_endpoint_assembles_the_full_bundle(client, monkeypatch):
    async def fake_summary(title):
        return {"extract": "A small songbird.", "content_url": "https://en.wikipedia.org/wiki/x"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    resp = client.get(
        "/species/profile",
        params={"scientific_name": "Poecile atricapillus", "common_name": "Black-capped Chickadee"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["about"] == "A small songbird."
    assert body["photo_url"].startswith("https://placehold.co/")  # no_live_media_lookups stubs Commons to nothing
    assert body["audio_url"] is None
