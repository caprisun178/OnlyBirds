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
