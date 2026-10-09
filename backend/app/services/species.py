"""Species search — thin business layer over the iNaturalist taxa DAO.

Normalizes iNat taxon records into `SpeciesRef` so callers never see raw iNat
JSON.

Also assembles the species "profile" bundle (photo + audio + About text +
habitat) — see docs/features/bird-info.md. Built out first for Test Your
Skill's post-answer reveal (both modes show a full profile, not just
whichever medium the question itself used — see TestYourSkill.js), but
deliberately layered as a general `get_profile()` here rather than
quiz-specific, so the full bird-info.md Species Page can reuse it unchanged
later instead of duplicating this assembly.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.dao import bird_audio, bird_photos, inaturalist, species_repo, wikipedia
from app.data.birds import BIRDS
from app.models.species import SpeciesPhoto, SpeciesRef

# Wikipedia summaries change rarely but not never — see bird-info.md's note
# on `fetched_at`.
_ABOUT_CACHE_MAX_AGE = timedelta(days=30)

# Only the original hand-curated describe & guess set (`app/data/birds.py`)
# has a habitat tag at all — most of the eBird-backed species a quiz/profile
# lookup can ask about (thousands of species, vs. this set's few dozen)
# simply have none. `get_profile()` treats a miss here as "not available,"
# not an error — same honest-about-gaps approach as `about`/`about_source_url`
# being nullable.
_HABITAT_BY_SCIENTIFIC_NAME = {b["scientific_name"]: b["habitat"] for b in BIRDS.values()}


def _to_ref(taxon: dict) -> SpeciesRef:
    return SpeciesRef(
        id=None,
        scientific_name=taxon.get("name"),
        common_name=taxon.get("preferred_common_name"),
        taxon_group=taxon.get("iconic_taxon_name"),
        source_ids={"inat": str(taxon["id"])} if taxon.get("id") is not None else {},
    )


async def search(query: str) -> list[SpeciesRef]:
    results = await inaturalist.search_species(query)
    return [_to_ref(t) for t in results]


async def get_stock_photos(species: list[SpeciesRef]) -> list[SpeciesPhoto]:
    """A guaranteed-non-blank photo for each given species, looked up
    concurrently (`bird_photos.get_stock_photo()`, cached there — see that
    module's docstring). Entries with no scientific name are skipped: there's
    nothing to look up by, and the caller already has nothing to show for
    them anyway.
    """
    named = [s for s in species if s.scientific_name]
    results = await asyncio.gather(
        *(bird_photos.get_stock_photo(s.scientific_name, s.common_name or s.scientific_name) for s in named)
    )
    return [
        SpeciesPhoto(scientific_name=s.scientific_name, photo_url=r["photo_url"], photo_attribution=r["attribution"])
        for s, r in zip(named, results)
    ]


async def get_about(scientific_name: str, common_name: str) -> dict:
    """The cached (or freshly-fetched) Wikipedia summary for a species.
    Returns `{about, about_source_url}` — both `None` if Wikipedia has
    nothing under either name (not an error; see `wikipedia.py`'s own
    docstring on why a common-name-first, scientific-name-fallback lookup
    still sometimes comes up empty).

    Cached in `species_content` (`species_repo.py`) rather than re-fetched
    every call — unlike Commons, Wikipedia's summary endpoint has no
    "try a different one" use case, so a flat time-based refresh
    (`_ABOUT_CACHE_MAX_AGE`) is enough.

    A transient `WikipediaUnavailable` (rate limit, network error — real,
    observed case: a burst of profile lookups hit Wikipedia's 429 right as
    this was being tested) falls back to whatever's cached, even if stale,
    rather than caching the failure itself as a permanent "nothing found."
    Deliberately swallowed here rather than left to propagate: `get_profile()`
    below fetches photo/audio/about concurrently with `asyncio.gather()`, and
    an uncaught exception from any one of those would cancel the other two
    — a Wikipedia hiccup has no business taking down an otherwise-working
    photo and audio lookup.
    """
    cached = await species_repo.species_content_repo.get(scientific_name)
    if cached and cached["fetched_at"] >= datetime.now(timezone.utc) - _ABOUT_CACHE_MAX_AGE:
        return {"about": cached["about"], "about_source_url": cached["about_source_url"]}

    try:
        result = await wikipedia.get_summary(common_name)
        if result is None and common_name != scientific_name:
            result = await wikipedia.get_summary(scientific_name)
    except wikipedia.WikipediaUnavailable:
        if cached:
            return {"about": cached["about"], "about_source_url": cached["about_source_url"]}
        return {"about": None, "about_source_url": None}

    about = result["extract"] if result else None
    about_source_url = result["content_url"] if result else None
    await species_repo.species_content_repo.upsert(scientific_name, about, about_source_url)
    return {"about": about, "about_source_url": about_source_url}


async def get_profile(scientific_name: str, common_name: str, family: str | None = None) -> dict:
    """The full species profile bundle: photo, audio, About text, and
    habitat (where known) — everything Test Your Skill's post-answer reveal
    shows for a species (see docs/features/bird-info.md). Photo and audio
    reuse their own already-built, already-cached lookups unchanged; only
    `about` is new work here.
    """
    photo, audio, about = await asyncio.gather(
        bird_photos.get_stock_photo(scientific_name, common_name),
        bird_audio.get_audio({"scientific_name": scientific_name}),
        get_about(scientific_name, common_name),
    )
    return {
        "scientific_name": scientific_name,
        "common_name": common_name,
        "family": family,
        "habitat": sorted(_HABITAT_BY_SCIENTIFIC_NAME.get(scientific_name, ())) or None,
        "photo_url": photo["photo_url"],
        "photo_attribution": photo["attribution"],
        "audio_url": audio["audio_url"] if audio else None,
        "audio_attribution": audio["attribution"] if audio else None,
        "about": about["about"],
        "about_source_url": about["about_source_url"],
    }
