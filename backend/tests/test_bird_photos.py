import asyncio
import json

from app.dao import bird_photos, commons

# Captured before conftest's autouse fixture monkeypatches _save_cache_file
# to a no-op for every test (so tests don't spam the real cache file on
# disk) — the one test below that specifically exercises persistence needs
# the real implementation back.
_real_save_cache_file = bird_photos._save_cache_file


async def _no_op_sleep(*_args):
    """Replaces `bird_photos.asyncio.sleep` in the retry-backoff tests — a
    plain lambda calling `asyncio.sleep` would recurse into itself, since
    patching `bird_photos.asyncio.sleep` patches the same shared `asyncio`
    module object the test file's own `import asyncio` refers to."""

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


def test_a_new_lookup_writes_through_to_the_cache_file(monkeypatch, tmp_path):
    # Regression: the cache used to be in-memory only — a species resolved
    # once still had to be re-fetched from Commons after every server
    # restart, which is slow (a real, reported "it took a while to load"
    # complaint). A genuine cache miss should now also persist to disk.
    cache_file = tmp_path / "species_photo_cache.json"
    monkeypatch.setattr(bird_photos, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(bird_photos, "_cache", {})
    monkeypatch.setattr(bird_photos, "_save_cache_file", _real_save_cache_file)

    async def fake_search(query):
        return {"media_url": "https://upload.wikimedia.org/real-robin.jpg", "artist": "Jane Birder"}

    monkeypatch.setattr(commons, "search_photo", fake_search)

    asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))

    assert cache_file.exists()
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["Turdus migratorius"]["media_url"] == "https://upload.wikimedia.org/real-robin.jpg"


def test_save_merges_with_disk_instead_of_overwriting(monkeypatch, tmp_path):
    # Regression — a real incident, not a hypothetical: two server
    # processes alive at once (the dev `--reload` watcher's old worker not
    # actually dying before a new one starts — a known issue in this
    # environment), each with their own in-memory `_cache` loaded from disk
    # at different times. The one loaded earlier (fewer entries) writing
    # last used to silently erase everything a *different* process had
    # since saved — confirmed live: a cache that had grown to 62 species
    # dropped back to 16 after exactly this. A save must never destroy an
    # entry it doesn't know about.
    cache_file = tmp_path / "species_photo_cache.json"
    # Simulates another process having already saved a species this one's
    # own (smaller) in-memory `_cache` has never heard of.
    cache_file.write_text(
        json.dumps({"Cyanocitta cristata": {"media_url": "https://upload.wikimedia.org/real-bluejay.jpg"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bird_photos, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(bird_photos, "_cache", {"Turdus migratorius": {"media_url": "https://upload.wikimedia.org/real-robin.jpg"}})
    monkeypatch.setattr(bird_photos, "_save_cache_file", _real_save_cache_file)

    bird_photos._save_cache_file()

    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["Cyanocitta cristata"]["media_url"] == "https://upload.wikimedia.org/real-bluejay.jpg"  # not lost
    assert saved["Turdus migratorius"]["media_url"] == "https://upload.wikimedia.org/real-robin.jpg"  # this process's own entry
    # The merge result is also reflected back into this process's own
    # in-memory cache, so a later lookup in the same process benefits too.
    assert bird_photos._cache["Cyanocitta cristata"]["media_url"] == "https://upload.wikimedia.org/real-bluejay.jpg"


def test_cache_file_is_loaded_back_on_a_fresh_lookup(monkeypatch, tmp_path):
    # The other half of the round trip: an entry already on disk should be
    # served without ever calling Commons again — this is the whole point
    # (survives a restart, not just repeat calls within one process).
    cache_file = tmp_path / "species_photo_cache.json"
    cache_file.write_text(
        json.dumps({"Turdus migratorius": {"media_url": "https://upload.wikimedia.org/real-robin.jpg"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bird_photos, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(bird_photos, "_cache", bird_photos._load_cache_file())

    async def fail_if_called(query):
        raise AssertionError("should have been served from the loaded cache, not Commons")

    monkeypatch.setattr(commons, "search_photo", fail_if_called)

    photo = asyncio.run(bird_photos.get_stock_photo("Turdus migratorius", "American Robin"))
    assert photo["photo_url"] == "https://upload.wikimedia.org/real-robin.jpg"


def test_load_cache_file_handles_a_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bird_photos, "_CACHE_FILE", tmp_path / "does-not-exist.json")
    assert bird_photos._load_cache_file() == {}


def test_load_cache_file_handles_a_corrupt_file(tmp_path, monkeypatch):
    cache_file = tmp_path / "species_photo_cache.json"
    cache_file.write_text("not valid json{{{", encoding="utf-8")
    monkeypatch.setattr(bird_photos, "_CACHE_FILE", cache_file)
    assert bird_photos._load_cache_file() == {}


def test_get_stock_photo_passes_through_flagged(monkeypatch):
    async def fake_search(query):
        return {"media_url": "https://upload.wikimedia.org/maybe-a-map.jpg", "flagged": True}

    monkeypatch.setattr(commons, "search_photo", fake_search)
    monkeypatch.setattr(bird_photos, "_cache", {})

    photo = asyncio.run(bird_photos.get_stock_photo("Ammodramus maritimus", "Seaside Sparrow"))
    assert photo["flagged"] is True


def test_get_stock_photo_treats_missing_flagged_key_as_false(monkeypatch):
    # Cache entries written before `flagged` existed don't have the key at
    # all — must not crash, must read as "not flagged" (see get_stock_photo()'s
    # own docstring note on this).
    monkeypatch.setattr(bird_photos, "_cache", {"Cyanocitta cristata": {"media_url": "https://upload.wikimedia.org/old-entry.jpg"}})

    photo = asyncio.run(bird_photos.get_stock_photo("Cyanocitta cristata", "Blue Jay"))
    assert photo["flagged"] is False


def test_get_different_stock_photo_updates_the_cache(monkeypatch):
    monkeypatch.setattr(bird_photos, "_cache", {"Ammodramus maritimus": {"media_url": "https://upload.wikimedia.org/the-map.jpg", "flagged": True}})
    monkeypatch.setattr(bird_photos, "_save_cache_file", lambda: None)

    async def fake_search(query, *, exclude_media_urls=frozenset()):
        assert exclude_media_urls == frozenset({"https://upload.wikimedia.org/the-map.jpg"})
        return {"media_url": "https://upload.wikimedia.org/a-real-photo.jpg", "artist": "Jane Birder", "flagged": False}

    monkeypatch.setattr(commons, "search_photo", fake_search)

    result = asyncio.run(
        bird_photos.get_different_stock_photo(
            "Ammodramus maritimus", "Seaside Sparrow", "https://upload.wikimedia.org/the-map.jpg"
        )
    )
    assert result["photo_url"] == "https://upload.wikimedia.org/a-real-photo.jpg"
    assert result["changed"] is True
    assert bird_photos._cache["Ammodramus maritimus"]["media_url"] == "https://upload.wikimedia.org/a-real-photo.jpg"


def test_get_different_stock_photo_retries_once_on_transient_failure(monkeypatch):
    # Real, observed case: a burst of quiz traffic rate-limited Commons right
    # as someone clicked "try another photo," and the first attempt's
    # CommonsUnavailable got reported as "no other photo exists" even though
    # Commons had several — this call has no other fallback (unlike
    # get_question()'s own retry-across-species loop), so it needs its own.
    monkeypatch.setattr(bird_photos, "_cache", {"Charadrius semipalmatus": {"media_url": "https://upload.wikimedia.org/flock-shot.jpg"}})
    monkeypatch.setattr(bird_photos, "_save_cache_file", lambda: None)
    monkeypatch.setattr(bird_photos.asyncio, "sleep", _no_op_sleep)

    calls = []

    async def fake_search(query, *, exclude_media_urls=frozenset()):
        calls.append(query)
        if len(calls) == 1:
            raise commons.CommonsUnavailable("429 Too Many Requests")
        return {"media_url": "https://upload.wikimedia.org/a-better-photo.jpg", "artist": "Jane Birder", "flagged": False}

    monkeypatch.setattr(commons, "search_photo", fake_search)

    result = asyncio.run(
        bird_photos.get_different_stock_photo(
            "Charadrius semipalmatus", "Semipalmated Plover", "https://upload.wikimedia.org/flock-shot.jpg"
        )
    )
    assert len(calls) == 2
    assert result["changed"] is True
    assert result["photo_url"] == "https://upload.wikimedia.org/a-better-photo.jpg"


def test_get_different_stock_photo_gives_up_after_two_transient_failures(monkeypatch):
    monkeypatch.setattr(bird_photos, "_cache", {"Charadrius semipalmatus": {"media_url": "https://upload.wikimedia.org/flock-shot.jpg"}})
    monkeypatch.setattr(bird_photos.asyncio, "sleep", _no_op_sleep)

    async def fake_search(query, *, exclude_media_urls=frozenset()):
        raise commons.CommonsUnavailable("429 Too Many Requests")

    monkeypatch.setattr(commons, "search_photo", fake_search)

    result = asyncio.run(
        bird_photos.get_different_stock_photo(
            "Charadrius semipalmatus", "Semipalmated Plover", "https://upload.wikimedia.org/flock-shot.jpg"
        )
    )
    assert result["changed"] is False
    assert result["photo_url"] == "https://upload.wikimedia.org/flock-shot.jpg"


def test_get_different_stock_photo_reports_unchanged_when_nothing_else_exists(monkeypatch):
    monkeypatch.setattr(bird_photos, "_cache", {"Ammodramus maritimus": {"media_url": "https://upload.wikimedia.org/only-one.jpg", "artist": "Jane Birder"}})

    async def fake_search(query, *, exclude_media_urls=frozenset()):
        return None  # Commons has nothing left once the current photo is excluded

    monkeypatch.setattr(commons, "search_photo", fake_search)

    result = asyncio.run(
        bird_photos.get_different_stock_photo(
            "Ammodramus maritimus", "Seaside Sparrow", "https://upload.wikimedia.org/only-one.jpg"
        )
    )
    assert result["changed"] is False
    assert result["photo_url"] == "https://upload.wikimedia.org/only-one.jpg"
