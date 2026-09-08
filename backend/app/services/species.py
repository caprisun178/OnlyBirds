"""Species search — thin business layer over the iNaturalist taxa DAO.

Normalizes iNat taxon records into `SpeciesRef` so callers never see raw iNat
JSON.
"""

from __future__ import annotations

from app.dao import inaturalist
from app.models.species import SpeciesRef


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
