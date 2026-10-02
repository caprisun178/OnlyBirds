"""Species search — thin business layer over the iNaturalist taxa DAO.

Normalizes iNat taxon records into `SpeciesRef` so callers never see raw iNat
JSON.
"""

from __future__ import annotations

import asyncio

from app.dao import bird_photos, inaturalist
from app.models.species import SpeciesPhoto, SpeciesRef


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
