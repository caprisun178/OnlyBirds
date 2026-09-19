import pytest
from fastapi.testclient import TestClient

from app.dao.observation_repo import InMemoryObservationRepo
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
    monkeypatch.setattr("app.dao.bird_photos._cache", {})
    monkeypatch.setattr("app.dao.bird_audio._cache", {})


@pytest.fixture()
def client(monkeypatch):
    # Isolate each test from the process-wide in-memory store.
    fresh = InMemoryObservationRepo()
    monkeypatch.setattr("app.dao.observation_repo.observation_repo", fresh)
    monkeypatch.setattr("app.services.observation.observation_repo", fresh)
    with TestClient(app) as c:
        yield c
