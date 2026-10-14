"""Species search — thin business layer over the iNaturalist taxa DAO.

Normalizes iNat taxon records into `SpeciesRef` so callers never see raw iNat
JSON.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.dao import bird_audio, bird_photos, inaturalist, wikipedia
from app.dao.species_repo import species_repo
from app.models.species import SpeciesContent, SpeciesPhoto, SpeciesProfile, SpeciesRef

_CONTENT_STALE_AFTER = timedelta(days=30)  # Wikipedia summaries change rarely, but not never


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


async def get_profile(scientific_name: str) -> SpeciesProfile:
    """Assembles the Bird Info page's full profile — see
    docs/features/bird-info.md. Taxonomy (common name/family) is gracefully
    omitted when the species isn't in our own `species` table yet; About/
    sex-differences/migration/habitat are independently nullable (an
    article might cover one and not another — not an error, see
    species_repo.py's module docstring). Photo/audio reuse the existing
    Commons-backed daos unchanged.
    """
    taxonomy = await species_repo.get_taxonomy(scientific_name)
    common_name = taxonomy["common_name"] if taxonomy else None
    family = taxonomy["family"] if taxonomy else None

    content = await _get_or_fetch_content(scientific_name, common_name)

    photo, audio = await asyncio.gather(
        bird_photos.get_stock_photo(scientific_name, common_name or scientific_name),
        bird_audio.get_audio({"scientific_name": scientific_name}),
    )

    return SpeciesProfile(
        scientific_name=scientific_name,
        common_name=common_name,
        family=family,
        photo_url=photo["photo_url"],
        photo_attribution=photo["attribution"],
        audio_url=audio["audio_url"] if audio else None,
        audio_attribution=audio["attribution"] if audio else None,
        about=content.about,
        about_source_url=content.about_source_url,
        sex_differences=content.sex_differences,
        migration=content.migration,
        habitat=content.habitat,
    )


async def _get_or_fetch_content(scientific_name: str, common_name: str | None) -> SpeciesContent:
    cached = await species_repo.get_content(scientific_name)
    if cached and cached.fetched_at and datetime.now(timezone.utc) - cached.fetched_at < _CONTENT_STALE_AFTER:
        return cached

    # Common name first (Wikipedia article titles for birds are almost
    # always the common name, not the binomial — see bird-info.md's note);
    # only fall back to the scientific name if that comes back empty. Once
    # a title resolves, sections are pulled from that same title — not
    # re-guessed independently, which could pick a different (wrong) title
    # than the one that actually worked for the summary.
    title = (common_name or scientific_name).replace(" ", "_")
    summary = await wikipedia.get_summary(title) if common_name else None
    if summary is None:
        title = scientific_name.replace(" ", "_")
        summary = await wikipedia.get_summary(title)

    sections = await wikipedia.get_sections(title)

    fresh = SpeciesContent(
        scientific_name=scientific_name,
        about=summary["extract"] if summary else None,
        about_source_url=summary["source_url"] if summary else None,
        sex_differences=sections.get("sex_differences"),
        migration=sections.get("migration"),
        habitat=sections.get("habitat"),
        fetched_at=datetime.now(timezone.utc),
    )
    return await species_repo.upsert_content(fresh)


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
