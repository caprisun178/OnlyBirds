import asyncio
from datetime import datetime, timezone

from app.dao.species_repo import InMemorySpeciesRepo
from app.models.species import SpeciesContent


def test_get_content_returns_none_for_an_unseen_species():
    repo = InMemorySpeciesRepo()
    assert asyncio.run(repo.get_content("Poecile atricapillus")) is None


def test_upsert_then_get_content_round_trips():
    repo = InMemorySpeciesRepo()
    content = SpeciesContent(
        scientific_name="Poecile atricapillus",
        about="A small songbird.",
        about_source_url="https://en.wikipedia.org/wiki/x",
        sex_differences="Sexes look alike.",
        migration="Non-migratory.",
        habitat="Forests.",
        fetched_at=datetime.now(timezone.utc),
    )
    asyncio.run(repo.upsert_content(content))

    result = asyncio.run(repo.get_content("Poecile atricapillus"))
    assert result.about == "A small songbird."
    assert result.sex_differences == "Sexes look alike."
    assert result.migration == "Non-migratory."
    assert result.habitat == "Forests."


def test_get_content_is_case_insensitive():
    repo = InMemorySpeciesRepo()
    asyncio.run(repo.upsert_content(SpeciesContent(scientific_name="Poecile atricapillus", about="x")))

    assert asyncio.run(repo.get_content("POECILE ATRICAPILLUS")) is not None
    assert asyncio.run(repo.get_content("poecile atricapillus")) is not None


def test_upsert_content_overwrites_the_previous_entry():
    repo = InMemorySpeciesRepo()
    asyncio.run(repo.upsert_content(SpeciesContent(scientific_name="Poecile atricapillus", about="Old text.")))
    asyncio.run(repo.upsert_content(SpeciesContent(scientific_name="Poecile atricapillus", about="New text.")))

    result = asyncio.run(repo.get_content("Poecile atricapillus"))
    assert result.about == "New text."


def test_upsert_content_accepts_a_fully_null_entry_when_wikipedia_has_nothing():
    repo = InMemorySpeciesRepo()
    asyncio.run(repo.upsert_content(SpeciesContent(scientific_name="Fictional birdus")))

    result = asyncio.run(repo.get_content("Fictional birdus"))
    assert result.about is None
    assert result.habitat is None


def test_get_taxonomy_returns_none_until_seeded():
    repo = InMemorySpeciesRepo()
    assert asyncio.run(repo.get_taxonomy("Poecile atricapillus")) is None


def test_seed_taxonomy_then_get_taxonomy_round_trips():
    repo = InMemorySpeciesRepo()
    repo._seed_taxonomy("Poecile atricapillus", "Black-capped Chickadee", "Paridae")

    result = asyncio.run(repo.get_taxonomy("Poecile atricapillus"))
    assert result["common_name"] == "Black-capped Chickadee"
    assert result["family"] == "Paridae"


def test_seed_taxonomy_defaults_family_to_none():
    repo = InMemorySpeciesRepo()
    repo._seed_taxonomy("Poecile atricapillus", "Black-capped Chickadee")

    result = asyncio.run(repo.get_taxonomy("Poecile atricapillus"))
    assert result["family"] is None
