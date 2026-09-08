"""Species search — proves connectivity to iNaturalist (roadmap step 2)."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.species import SpeciesRef
from app.services import species as species_service

router = APIRouter(prefix="/species", tags=["species"])


@router.get("/search", response_model=list[SpeciesRef])
async def search_species(q: str = Query(min_length=1, description="Name fragment")):
    try:
        return await species_service.search(q)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"iNaturalist error: {exc}") from exc
