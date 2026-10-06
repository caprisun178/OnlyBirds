"""Species search — proves connectivity to iNaturalist (roadmap step 2)."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.dao.wikipedia import WikipediaUnavailable
from app.models.species import SpeciesPhoto, SpeciesProfile, SpeciesRef
from app.services import species as species_service

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/profile", response_model=SpeciesProfile)
async def get_species_profile(
    scientific_name: str = Query(min_length=1, description="e.g. 'Poecile atricapillus'"),
):
    """The Bird Info page — see docs/features/bird-info.md. Query-param, not
    a path segment (`/species/{code}`), since most of this app's real entry
    points only ever have a scientific name on hand, never an eBird code.
    """
    try:
        return await species_service.get_profile(scientific_name)
    except WikipediaUnavailable as exc:
        raise HTTPException(status_code=502, detail=f"Wikipedia error: {exc}") from exc


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
