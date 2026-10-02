from datetime import datetime, timezone

import pytest

from app.dao.sticker_repo import InMemoryStickerRepo
from app.models.life_list import LifeListEntry
from app.models.species import SpeciesRef
from app.services.stickers import _group_progress


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
    shelf_data = shelf.json()
    earned = {sticker["code"] for sticker in shelf_data["earned"]}
    assert earned >= {"first_bird", "first_owl"}
    first_owl = next(sticker for sticker in shelf_data["earned"] if sticker["code"] == "first_owl")
    assert first_owl["progress"] == 1
    assert first_owl["target"] is None


def test_repeated_observation_does_not_duplicate_awards(client, isolated_stickers):
    species = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    payload = observation("u1", species, "2026-05-01T08:00:00+00:00")
    client.post("/observations", json=payload)
    client.post("/observations", json={**payload, "observed_at": "2026-05-02T08:00:00+00:00"})

    awards = isolated_stickers.list_awards("u1")
    assert [award.sticker_code for award in awards] == ["first_bird"]


def test_only_logged_observations_update_stickers(client, isolated_stickers):
    species = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    payload = observation("u1", species, "2026-05-01T08:00:00+00:00")

    draft = client.post("/observations", json={**payload, "status": "draft"})
    assert draft.status_code == 201
    assert client.get("/users/u1/life-list").json() == []
    assert isolated_stickers.list_awards("u1") == []

    logged = client.post("/observations", json={**payload, "status": "logged"})
    assert logged.status_code == 201
    shelf = client.get("/users/u1/stickers").json()
    assert "first_bird" in {sticker["code"] for sticker in shelf["earned"]}
    award = next(a for a in isolated_stickers.list_awards("u1") if a.sticker_code == "first_bird")
    assert award.observation_id == logged.json()["id"]


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


def test_eagle_set_progress_completes_only_after_every_species():
    def entry(code: str) -> LifeListEntry:
        return LifeListEntry(
            user_id="u1",
            species=SpeciesRef(
                scientific_name=code,
                common_name=code,
                source_ids={"ebird": code},
            ),
            first_observed_at=datetime.now(timezone.utc),
        )

    first_progress = _group_progress("eagles", [entry("baldeag")])
    complete_progress = _group_progress("eagles", [entry("baldeag"), entry("goleag")])

    assert first_progress == (1, 2, False)
    assert complete_progress == (2, 2, True)


def test_all_eagles_award_and_progress_are_updated(client, isolated_stickers):
    for code, common_name, date in [
        ("baldeag", "Bald Eagle", "2026-05-01"),
        ("goleag", "Golden Eagle", "2026-05-02"),
    ]:
        response = client.post(
            "/observations",
            json=observation(
                "u1",
                {
                    "scientific_name": common_name,
                    "common_name": common_name,
                    "source_ids": {"ebird": code},
                },
                f"{date}T08:00:00+00:00",
            ),
        )
        assert response.status_code == 201

    shelf = client.get("/users/u1/stickers").json()
    earned = {sticker["code"] for sticker in shelf["earned"]}
    all_eagles = next(sticker for sticker in shelf["earned"] if sticker["code"] == "all_eagles")
    assert {"first_eagle", "all_eagles"} <= earned
    assert (all_eagles["progress"], all_eagles["target"]) == (2, 2)


def test_count_milestone_shows_progress_and_awards_at_threshold(client, isolated_stickers):
    for number in range(25):
        response = client.post(
            "/observations",
            json=observation(
                "u1",
                {
                    "scientific_name": f"Species {number}",
                    "common_name": f"Bird {number}",
                },
                f"2026-06-{number + 1:02d}T08:00:00+00:00",
            ),
        )
        assert response.status_code == 201

    shelf = client.get("/users/u1/stickers").json()
    earned = {sticker["code"] for sticker in shelf["earned"]}
    species_100 = next(sticker for sticker in shelf["locked"] if sticker["code"] == "species_100")
    assert "species_25" in earned
    assert (species_100["progress"], species_100["target"]) == (25, 100)