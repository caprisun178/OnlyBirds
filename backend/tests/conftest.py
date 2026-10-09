import pytest
from fastapi.testclient import TestClient

from app.dao.notification_repo import InMemoryNotificationRepo
from app.dao.observation_repo import InMemoryObservationRepo
from app.dao.pin_repo import InMemoryPinRepo
from app.dao.species_repo import InMemorySpeciesContentRepo
from app.dao.user_repo import InMemoryUserRepo
from app.main import app




@pytest.fixture(autouse=True)
def no_live_media_lookups(monkeypatch):
    """Keep the suite offline (see docs/ebird-api.md's "no test hits the live
    API" rule) and each test's candidate photos/audio deterministic.
    Individual tests can still monkeypatch `commons.search_photo` /
    `commons.search_audio` themselves to exercise the lookup path — see
    test_bird_photos.py and test_bird_audio.py."""
    async def _no_media(*args, **kwargs):
        return None

    monkeypatch.setattr("app.dao.commons.search_photo", _no_media)
    monkeypatch.setattr("app.dao.commons.search_audio", _no_media)
    monkeypatch.setattr("app.dao.wikipedia.get_summary", _no_media)
    monkeypatch.setattr("app.dao.bird_photos._cache", {})
    monkeypatch.setattr("app.dao.bird_audio._cache", {})
    monkeypatch.setattr("app.dao.species_repo.species_content_repo", InMemorySpeciesContentRepo())
    # bird_photos' cache now writes through to a real file on disk (see its
    # module docstring) — tests exercise cache-miss paths constantly, which
    # would otherwise spam the real species_photo_cache.json with test
    # fixture junk (or fail outright in a read-only CI checkout).
    monkeypatch.setattr("app.dao.bird_photos._save_cache_file", lambda: None)


@pytest.fixture()
def client(monkeypatch):
    # `log_observation()` calls `ebird.region_for_point()` — which calls
    # `get_hotspots_near()` — for every observation logged with lat/lng,
    # which is most of the ones posted through this `client`. A real
    # `EBIRD_API_KEY` happens to be set in this repo's `.env` (pydantic
    # settings loads it by default), so without this default, a plain
    # `POST /observations` test would silently make a real, slow eBird call
    # — the same offline-tests rule `no_live_media_lookups` above exists
    # for. Scoped to this fixture (not a separate blanket autouse one)
    # deliberately: test_ebird.py tests `get_hotspots_near()` itself
    # directly and never uses `client`, so it's never affected; tests that
    # *do* use `client` and want real `get_hotspots_near()` behavior
    # (test_trip.py's `_stub_sources()`, etc.) already monkeypatch it
    # themselves, which simply overrides this default.
    async def _no_hotspots(lat, lng, dist_km=25):
        return []

    monkeypatch.setattr("app.dao.ebird.get_hotspots_near", _no_hotspots)

    # Isolate each test from the process-wide in-memory stores.
    fresh = InMemoryObservationRepo()
    monkeypatch.setattr("app.dao.observation_repo.observation_repo", fresh)
    monkeypatch.setattr("app.services.observation.observation_repo", fresh)
    monkeypatch.setattr("app.services.sightings.observation_repo", fresh)
    fresh_users = InMemoryUserRepo()
    monkeypatch.setattr("app.dao.user_repo.user_repo", fresh_users)
    monkeypatch.setattr("app.services.user.user_repo", fresh_users)
    fresh_pins = InMemoryPinRepo()
    monkeypatch.setattr("app.dao.pin_repo.pin_repo", fresh_pins)
    monkeypatch.setattr("app.services.pins.pin_repo", fresh_pins)
    fresh_notifications = InMemoryNotificationRepo()
    monkeypatch.setattr("app.dao.notification_repo.notification_repo", fresh_notifications)
    monkeypatch.setattr("app.services.pins.notification_repo", fresh_notifications)
    monkeypatch.setattr("app.services.notifications.notification_repo", fresh_notifications)
    with TestClient(app) as c:
        yield c