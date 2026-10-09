import asyncio
from datetime import datetime, timezone

from app.dao.species_repo import InMemorySpeciesContentRepo


def test_get_returns_none_for_an_unseen_species():
    repo = InMemorySpeciesContentRepo()
    assert asyncio.run(repo.get("Poecile atricapillus")) is None


def test_upsert_then_get_round_trips():
    repo = InMemorySpeciesContentRepo()
    asyncio.run(repo.upsert("Poecile atricapillus", "A small songbird.", "https://en.wikipedia.org/wiki/x"))

    result = asyncio.run(repo.get("Poecile atricapillus"))
    assert result["about"] == "A small songbird."
    assert result["about_source_url"] == "https://en.wikipedia.org/wiki/x"
    assert isinstance(result["fetched_at"], datetime)
    assert result["fetched_at"].tzinfo is not None


def test_upsert_overwrites_the_previous_entry():
    repo = InMemorySpeciesContentRepo()
    asyncio.run(repo.upsert("Poecile atricapillus", "Old text.", "https://old.example/"))
    asyncio.run(repo.upsert("Poecile atricapillus", "New text.", "https://new.example/"))

    result = asyncio.run(repo.get("Poecile atricapillus"))
    assert result["about"] == "New text."


def test_upsert_accepts_null_about_when_wikipedia_has_nothing():
    repo = InMemorySpeciesContentRepo()
    asyncio.run(repo.upsert("Fictional birdus", None, None))

    result = asyncio.run(repo.get("Fictional birdus"))
    assert result["about"] is None
    assert result["about_source_url"] is None
    # A cached "nothing found" still has a fetch timestamp, so it won't be
    # re-queried on every call — only once `_ABOUT_CACHE_MAX_AGE` elapses.
    assert result["fetched_at"] <= datetime.now(timezone.utc)
