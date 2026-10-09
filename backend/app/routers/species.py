"""Species search — proves connectivity to iNaturalist (roadmap step 2)."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.species import SpeciesPhoto, SpeciesRef
from app.services import species as species_service

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/search", response_model=list[SpeciesRef])
async def search_species(q: str = Query(min_length=1, description="Name fragment")):
    try:
        return await species_service.search(q)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"iNaturalist error: {exc}") from exc


@router.post("/photos", response_model=list[SpeciesPhoto])
async def get_species_photos(species: list[SpeciesRef]):
    """A guaranteed-non-blank photo per given species — backs Explore Map's
    species-filter suggestions, most of which (eBird sightings) never carry
    their own `photo_url`. POST (not GET) since this takes a batch of
    name pairs, not a single query string; see
    `services/species.py#get_stock_photos`'s docstring for the lookup
    itself.
    """
    return await species_service.get_stock_photos(species)


@router.get("/profile")
async def get_species_profile(
    scientific_name: str = Query(),
    common_name: str = Query(),
    family: str | None = Query(default=None),
):
    """Photo + audio + About text + habitat for one species — see
    docs/features/bird-info.md. First real caller: Test Your Skill's
    post-answer reveal. Query-param, not `/species/{code}`, since most
    callers only ever have a scientific name on hand, never an eBird code
    (see bird-info.md's own note on this).
    """
    return await species_service.get_profile(scientific_name, common_name, family)
