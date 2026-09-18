import pytest
from fastapi.testclient import TestClient

from app.dao.observation_repo import InMemoryObservationRepo
from app.main import app


@pytest.fixture(autouse=True)
def no_live_photo_lookups(monkeypatch):
    """Keep the suite offline (see docs/ebird-api.md's "no test hits the live
    API" rule) and each test's candidate photos deterministic. Individual
    tests can still monkeypatch `commons.search_photo` themselves to exercise
    the lookup path — see test_bird_photos.py."""
    async def _no_photo(*args, **kwargs):
        return None

    monkeypatch.setattr("app.dao.commons.search_photo", _no_photo)
    monkeypatch.setattr("app.dao.bird_photos._cache", {})


@pytest.fixture()
def client(monkeypatch):
    # Isolate each test from the process-wide in-memory store.
    fresh = InMemoryObservationRepo()
    monkeypatch.setattr("app.dao.observation_repo.observation_repo", fresh)
    monkeypatch.setattr("app.services.observation.observation_repo", fresh)
    with TestClient(app) as c:
        yield c
