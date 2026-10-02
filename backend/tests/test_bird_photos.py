import asyncio

from app.dao import bird_photos, commons

BIRD = {
    "code": "blujay",
    "common_name": "Blue Jay",
    "scientific_name": "Cyanocitta cristata",
    "photo_url": "https://placehold.co/320x220/3aa0ff/ffffff?text=Blue+Jay",
}


def test_uses_commons_result_when_found(monkeypatch):
    async def fake_search(query):
        assert query == "Cyanocitta cristata"
        return {
            "media_url": "https://upload.wikimedia.org/real-blue-jay.jpg",
            "artist": "Jane Birder",
            "license": "CC BY-SA 3.0",
        }

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    photo = asyncio.run(bird_photos.get_photo(BIRD))
    assert photo["photo_url"] == "https://upload.wikimedia.org/real-blue-jay.jpg"
    assert photo["attribution"] == "Jane Birder / Wikimedia Commons (CC BY-SA 3.0)"


def test_falls_back_to_placeholder_when_commons_has_nothing(monkeypatch):
    async def fake_search(query):
        return None

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    photo = asyncio.run(bird_photos.get_photo(BIRD))
    assert photo["photo_url"] == BIRD["photo_url"]
    assert photo["attribution"] is None


def test_caches_after_first_lookup(monkeypatch):
    calls = []

    async def fake_search(query):
        calls.append(query)
        return {"media_url": "https://upload.wikimedia.org/real-blue-jay.jpg"}

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    async def _lookup_twice():
        await bird_photos.get_photo(BIRD)
        await bird_photos.get_photo(BIRD)

    asyncio.run(_lookup_twice())

    assert calls == ["Cyanocitta cristata"]  # second call was served from cache


def test_get_stock_photo_uses_commons_result_when_found(monkeypatch):
    async def fake_search(query):
        assert query == "Turdus migratorius"
        return {"media_url": "https://upload.wikimedia.org/real-robin.jpg", "artist": "Jane Birder"}

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    photo = asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))
    assert photo["photo_url"] == "https://upload.wikimedia.org/real-robin.jpg"
    assert photo["attribution"] == "Jane Birder / Wikimedia Commons"


def test_get_stock_photo_falls_back_to_a_generated_placeholder(monkeypatch):
    # Unlike get_photo(), there's no birds.py entry to fall back to — the
    # whole point is this never returns nothing, so a Life List card never
    # renders with no image at all.
    async def fake_search(query):
        return None

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    photo = asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))
    assert photo["photo_url"] == "https://placehold.co/320x220/5b7a99/ffffff?text=American%20Robin"
    assert photo["attribution"] is None


def test_transient_commons_failure_falls_back_but_is_not_cached(monkeypatch):
    # A rate limit or network blip shouldn't permanently deny a species a
    # real photo — only a genuine "nothing found" (Commons returning None)
    # gets cached; CommonsUnavailable should let the next call retry.
    calls = {"n": 0}

    async def flaky_search(query):
        calls["n"] += 1
        if calls["n"] == 1:
            raise commons.CommonsUnavailable("429 Too Many Requests")
        return {"media_url": "https://upload.wikimedia.org/real-robin.jpg"}

    monkeypatch.setattr(commons, "search_photo", flaky_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    first = asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))
    assert first["photo_url"] == "https://placehold.co/320x220/5b7a99/ffffff?text=American%20Robin"

    second = asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))
    assert second["photo_url"] == "https://upload.wikimedia.org/real-robin.jpg"
    assert calls["n"] == 2  # not cached after the failure, so it retried
