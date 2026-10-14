"""`POST /species/photos` — backs Explore Map's species-filter suggestions.
Mocked at `commons.search_photo` (same layer `test_bird_photos.py` mocks at),
per docs/ebird-api.md's "no test hits a live API" rule.

`GET /species/profile` — the Bird Info page's full profile, and (see
`test_profile_accepts_common_name_and_family_overrides` on) Test Your
Skill's reveal, which already knows a species' common name/family from its
own question and shouldn't depend on a taxonomy lookup that's often empty
for anything outside this app's own logged history (most of the quiz's
"world" pool).
"""

import asyncio

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


def test_profile_assembles_taxonomy_media_and_wikipedia_text(client, monkeypatch):
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


def test_profile_accepts_common_name_and_family_overrides_without_a_taxonomy_lookup(client, monkeypatch):
    # Test Your Skill's actual use: it already knows the common name/family
    # from the question's own choices, and the species is very often NOT in
    # our `species` table at all (most of the quiz's "world" pool is wider
    # than anything any user has logged via eBird) — get_taxonomy() would
    # come back empty, but the override means that never matters.
    async def fake_summary(title):
        assert title == "Zimmer's_Woodcreeper"
        return {"extract": "A woodcreeper.", "source_url": "https://en.wikipedia.org/wiki/zw"}

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)

    resp = client.get(
        "/species/profile",
        params={
            "scientific_name": "Dendroplex kienerii",
            "common_name": "Zimmer's Woodcreeper",
            "family": "Ovenbirds and Woodcreepers",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["common_name"] == "Zimmer's Woodcreeper"
    assert body["family"] == "Ovenbirds and Woodcreepers"
    assert body["about"] == "A woodcreeper."
    # get_taxonomy() was never consulted — confirmed by never seeding it,
    # unlike the taxonomy-lookup tests above which explicitly seed first.
    assert asyncio.run(species_repo.species_repo.get_taxonomy("Dendroplex kienerii")) is None


def test_get_profile_does_not_lose_photo_and_audio_when_wikipedia_fails(monkeypatch):
    # Regression: all three lookups (content/photo/audio) run inside one
    # asyncio.gather() in get_profile() — an uncaught exception from the
    # Wikipedia-sourced content fetch would otherwise cancel the other two,
    # even though they have nothing to do with Wikipedia. Real, observed
    # case: a burst of profile lookups hit Wikipedia's 429 during testing.
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
    assert profile.photo_url == "https://upload.wikimedia.org/jay.jpg"
    assert profile.audio_url == "https://upload.wikimedia.org/jay.ogg"
    assert profile.about is None


def test_get_profile_falls_back_to_stale_content_cache_on_a_transient_wikipedia_failure(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.species import SpeciesContent

    stale = SpeciesContent(
        scientific_name="Cyanocitta cristata",
        about="stale but real text",
        about_source_url="https://en.wikipedia.org/wiki/stale",
        fetched_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    asyncio.run(species_repo.species_repo.upsert_content(stale))

    async def fake_summary(title):
        raise wikipedia.WikipediaUnavailable("429 Too Many Requests")

    monkeypatch.setattr(wikipedia, "get_summary", fake_summary)
    monkeypatch.setattr(bird_photos, "_cache", {})

    from app.services import species as species_service

    profile = asyncio.run(species_service.get_profile("Cyanocitta cristata", "Blue Jay"))
    assert profile.about == "stale but real text"


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
