import asyncio

from app.dao import bird_audio, commons

BIRD = {
    "code": "blujay",
    "common_name": "Blue Jay",
    "scientific_name": "Cyanocitta cristata",
}


def test_uses_commons_result_when_found(monkeypatch):
    async def fake_search(query):
        assert query == "Cyanocitta cristata"
        return {
            "media_url": "https://upload.wikimedia.org/blue-jay-call.mp3",
            "artist": "Jane Birder",
            "license": "CC BY-SA 3.0",
        }

    monkeypatch.setattr(commons, "search_audio", fake_search)
    monkeypatch.setattr(bird_audio, "_cache", {})

    audio = asyncio.run(bird_audio.get_audio(BIRD))
    assert audio["audio_url"] == "https://upload.wikimedia.org/blue-jay-call.mp3"
    assert audio["attribution"] == "Jane Birder / Wikimedia Commons (CC BY-SA 3.0)"


def test_returns_none_when_commons_has_nothing(monkeypatch):
    async def fake_search(query):
        return None

    monkeypatch.setattr(commons, "search_audio", fake_search)
    monkeypatch.setattr(bird_audio, "_cache", {})

    audio = asyncio.run(bird_audio.get_audio(BIRD))
    assert audio is None  # no placeholder to fall back to, unlike photos


def test_caches_after_first_lookup(monkeypatch):
    calls = []

    async def fake_search(query):
        calls.append(query)
        return {"media_url": "https://upload.wikimedia.org/blue-jay-call.mp3"}

    monkeypatch.setattr(commons, "search_audio", fake_search)
    monkeypatch.setattr(bird_audio, "_cache", {})

    async def _lookup_twice():
        await bird_audio.get_audio(BIRD)
        await bird_audio.get_audio(BIRD)

    asyncio.run(_lookup_twice())

    assert calls == ["Cyanocitta cristata"]  # second call was served from cache


def test_caches_a_miss_too_so_it_does_not_refetch(monkeypatch):
    calls = []

    async def fake_search(query):
        calls.append(query)
        return None

    monkeypatch.setattr(commons, "search_audio", fake_search)
    monkeypatch.setattr(bird_audio, "_cache", {})

    async def _lookup_twice():
        await bird_audio.get_audio(BIRD)
        await bird_audio.get_audio(BIRD)

    asyncio.run(_lookup_twice())

    assert calls == ["Cyanocitta cristata"]
