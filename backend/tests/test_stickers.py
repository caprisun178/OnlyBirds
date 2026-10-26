import asyncio
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
    catalog_codes = {sticker["code"] for sticker in catalog.json()}
    assert catalog_codes >= {"first_bird", "first_owl"}
    assert "all_eagles" not in catalog_codes
    artwork = {
        "first_bird": "/static/stickers/first_bird.png",
        "first_owl": "/static/stickers/night_owl.png",
        "first_eagle": "/static/stickers/eagle_eye.png",
    }
    catalog_images = {sticker["code"]: sticker["image_url"] for sticker in catalog.json()}
    assert {code: catalog_images[code] for code in artwork} == artwork
    for image_url in artwork.values():
        image = client.get(image_url)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")

    # The wizard submits species names without a sticker/taxonomy group.
    species = {"scientific_name": "Tyto alba", "common_name": "Barn Owl"}
    client.post("/observations", json=observation("u1", species, "2026-05-01T08:00:00+00:00"))

    shelf = client.get("/users/u1/stickers")
    assert shelf.status_code == 200
    shelf_data = shelf.json()
    earned = {sticker["code"] for sticker in shelf_data["earned"]}
    assert earned >= {"first_bird", "first_owl"}
    shelf_images = {sticker["code"]: sticker["image_url"] for sticker in shelf_data["earned"] + shelf_data["locked"]}
    assert {code: shelf_images[code] for code in artwork} == artwork
    first_owl = next(sticker for sticker in shelf_data["earned"] if sticker["code"] == "first_owl")
    assert first_owl["progress"] == 1
    assert first_owl["target"] == 1


@pytest.mark.parametrize(
    ("scientific_name", "common_name", "expected_missing_stickers"),
    [
        ("Tyto alba", "Barn Owl", {"first_owl", "first_raptor"}),
        ("Haliaeetus leucocephalus", "Bald Eagle", {"first_eagle", "first_raptor"}),
    ],
)
def test_repeated_logged_sighting_backfills_missing_group_stickers(
    client, isolated_stickers, scientific_name, common_name, expected_missing_stickers
):
    from app.models.observation import ObservationCreate
    from app.services.observation import observation_repo

    asyncio.run(
        observation_repo.add(
            ObservationCreate(
                user_id="u1",
                observed_at=datetime.fromisoformat("2026-05-01T08:00:00+00:00"),
                source="manual",
                species={"scientific_name": scientific_name, "common_name": common_name},
            )
        )
    )
    asyncio.run(isolated_stickers.award("u1", "first_bird"))

    response = client.post(
        "/observations",
        json=observation(
            "u1",
            {"scientific_name": scientific_name, "common_name": common_name},
            "2026-05-02T08:00:00+00:00",
        ),
    )

    assert response.status_code == 201
    assert {sticker["code"] for sticker in response.json()["stickers_earned"]} == expected_missing_stickers
    earned = {sticker["code"] for sticker in client.get("/users/u1/stickers").json()["earned"]}
    assert earned == {"first_bird"} | expected_missing_stickers


def test_repeated_observation_does_not_duplicate_awards(client, isolated_stickers):
    species = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    payload = observation("u1", species, "2026-05-01T08:00:00+00:00")
    client.post("/observations", json=payload)
    client.post("/observations", json={**payload, "observed_at": "2026-05-02T08:00:00+00:00"})

    awards = asyncio.run(isolated_stickers.list_awards("u1"))
    assert [award.sticker_code for award in awards] == ["first_bird"]


def test_only_logged_observations_update_stickers(client, isolated_stickers):
    species = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    payload = observation("u1", species, "2026-05-01T08:00:00+00:00")

    draft = client.post("/observations", json={**payload, "status": "draft"})
    assert draft.status_code == 201
    assert client.get("/users/u1/life-list").json() == []
    assert asyncio.run(isolated_stickers.list_awards("u1")) == []

    logged = client.post("/observations", json={**payload, "status": "logged"})
    assert logged.status_code == 201
    shelf = client.get("/users/u1/stickers").json()
    assert "first_bird" in {sticker["code"] for sticker in shelf["earned"]}
    award = next(a for a in asyncio.run(isolated_stickers.list_awards("u1")) if a.sticker_code == "first_bird")
    assert award.observation_id == logged.json()["id"]


def test_first_eagle_does_not_require_complete_set(client, isolated_stickers):
    species = {"scientific_name": "Haliaeetus leucocephalus", "common_name": "Bald Eagle"}
    client.post("/observations", json=observation("u1", species, "2026-05-01T08:00:00+00:00"))

    shelf = client.get("/users/u1/stickers").json()
    earned = {sticker["code"] for sticker in shelf["earned"]}
    assert {"first_eagle", "first_raptor", "first_bird"} <= earned
    assert "all_eagles" not in {sticker["code"] for sticker in shelf["locked"]}
    first_eagle = next(sticker for sticker in shelf["earned"] if sticker["code"] == "first_eagle")
    assert (first_eagle["progress"], first_eagle["target"]) == (1, 1)


def test_any_eagle_subspecies_earns_eagle_eye(client, isolated_stickers):
    response = client.post(
        "/observations",
        json=observation(
            "u1",
            {"scientific_name": "Aquila testii", "common_name": "Test Eagle"},
            "2026-05-01T08:00:00+00:00",
        ),
    )

    assert response.status_code == 201
    earned = {sticker["code"] for sticker in response.json()["stickers_earned"]}
    assert {"first_eagle", "first_raptor"} <= earned

    shelf = client.get("/users/u1/stickers").json()
    assert "all_eagles" not in {
        sticker["code"] for sticker in shelf["earned"] + shelf["locked"]
    }
    first_eagle = next(sticker for sticker in shelf["earned"] if sticker["code"] == "first_eagle")
    assert (first_eagle["progress"], first_eagle["target"]) == (1, 1)


@pytest.mark.parametrize(
    ("common_name", "expected_stickers"),
    [
        ("Turkey Vulture", {"first_bird", "first_raptor"}),
        ("Barn Owl", {"first_bird", "first_owl", "first_raptor"}),
        ("Test Eagle", {"first_bird", "first_eagle", "first_raptor"}),
        ("Peregrine Falcon", {"first_bird", "first_raptor"}),
        ("Red-tailed Hawk", {"first_bird", "first_raptor"}),
    ],
)
def test_raptor_categories_award_bird_of_prey(
    client, isolated_stickers, common_name, expected_stickers
):
    response = client.post(
        "/observations",
        json=observation(
            "u1",
            {"scientific_name": f"Test species for {common_name}", "common_name": common_name},
            "2026-05-01T08:00:00+00:00",
        ),
    )

    assert response.status_code == 201
    earned = {sticker["code"] for sticker in response.json()["stickers_earned"]}
    assert earned == expected_stickers


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

def test_logging_returns_newly_earned_stickers(client, isolated_stickers):
    owl = {"scientific_name": "Strix varia", "common_name": "Barred Owl", "taxon_group": "owls"}

    first = client.post("/observations", json=observation("u1", owl, "2026-05-01T08:00:00+00:00")).json()
    again = client.post("/observations", json=observation("u1", owl, "2026-05-02T08:00:00+00:00")).json()

    assert {s["code"] for s in first["stickers_earned"]} >= {"first_bird", "first_owl"}
    assert all(s["name"] for s in first["stickers_earned"])
    assert again["stickers_earned"] == []  # same species again: nothing new


def test_each_earned_sticker_adds_one_notification(client, isolated_stickers):
    owl = {"scientific_name": "Strix varia", "common_name": "Barred Owl", "taxon_group": "owls"}
    earned = client.post("/observations", json=observation("u1", owl, "2026-05-01T08:00:00+00:00")).json()
    client.post("/observations", json=observation("u1", owl, "2026-05-02T08:00:00+00:00"))

    notes = [n for n in client.get("/users/u1/notifications").json() if n["kind"] == "sticker_awarded"]

    assert sorted(n["payload"]["sticker_code"] for n in notes) == sorted(s["code"] for s in earned["stickers_earned"])
    assert all(n["payload"]["name"] for n in notes)


def test_earned_stickers_do_not_leak_between_tests_part_1(client):
    bird = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
    client.post("/observations", json=observation("u1", bird, "2026-05-01T08:00:00+00:00"))
    assert client.get("/users/u1/stickers").json()["earned"]


def test_earned_stickers_do_not_leak_between_tests_part_2(client):
    # Runs after part 1 with the default (conftest) sticker repo: must start empty.
    assert client.get("/users/u1/stickers").json()["earned"] == []


def test_a_sticker_failure_does_not_fail_logging(client, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("relation user_stickers does not exist")

    monkeypatch.setattr("app.services.stickers.evaluate_stickers", broken)
    bird = {"scientific_name": "Corvus corax", "common_name": "Common Raven"}

    r = client.post("/observations", json=observation("u1", bird, "2026-05-01T08:00:00+00:00"))

    assert r.status_code == 201
    assert r.json()["stickers_earned"] == []
