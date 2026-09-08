import pytest
from fastapi.testclient import TestClient

from app.dao.observation_repo import InMemoryObservationRepo
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    # Isolate each test from the process-wide in-memory store.
    fresh = InMemoryObservationRepo()
    monkeypatch.setattr("app.dao.observation_repo.observation_repo", fresh)
    monkeypatch.setattr("app.services.observation.observation_repo", fresh)
    with TestClient(app) as c:
        yield c
