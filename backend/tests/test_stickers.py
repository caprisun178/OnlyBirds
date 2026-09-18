from datetime import datetime, timezone

import pytest

from app.dao.sticker_repo import InMemoryStickerRepo


@pytest.fixture()
def isolated_stickers(monkeypatch):
    repo = InMemoryStickerRepo()
    monkeypatch.setattr("app.services.stickers.sticker_repo", repo)
    return repo


def observation(user_id: str, species: dict, observed_at: str) -> dict:
    return {
        "user_id": user_id,
        "lat": 47.6,
        "lng": -122.33,
        "observed_at": observed_at,
        "source": "manual",
        "species": species,
    }


def test_catalog_and_first_bird_award(client, isolated_stickers):
    catalog = client.get("/stickers")
    assert catalog.status_code == 200
    assert {sticker["code"] for sticker in catalog.json()} >= {"first_bird", "first_owl"}

    species = {"scientific_name": "Strix varia", "common_name": "Barred Owl", "taxon_group": "owls"}
    client.post("/observations", json=observation("u1", species, "2026-05-01T08:00:00+00:00"))

    shelf = client.get("/users/u1/stickers")
    assert shelf.status_code == 200
    earned = {sticker["code"] for sticker in shelf.json()["earned"]}
    assert earned >= {"first_bird", "first_owl"}


def test_repeated_observation_does_not_duplicate_awards(client, isolated_stickers):
    species = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    payload = observation("u1", species, "2026-05-01T08:00:00+00:00")
    client.post("/observations", json=payload)
    client.post("/observations", json={**payload, "observed_at": "2026-05-02T08:00:00+00:00"})

    awards = isolated_stickers.list_awards("u1")
    assert [award.sticker_code for award in awards] == ["first_bird"]


def test_first_eagle_does_not_require_complete_set(client, isolated_stickers):
    species = {
        "scientific_name": "Haliaeetus leucocephalus",
        "common_name": "Bald Eagle",
        "source_ids": {"ebird": "baldeag"},
    }
    client.post("/observations", json=observation("u1", species, "2026-05-01T08:00:00+00:00"))

    earned = {sticker["code"] for sticker in client.get("/users/u1/stickers").json()["earned"]}
    assert "first_eagle" in earned
    assert "all_eagles" not in earned