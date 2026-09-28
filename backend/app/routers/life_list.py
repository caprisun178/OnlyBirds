"""Life-list endpoints — derived from the user's stored observations, plus
the region checklist ("completion view") built from eBird's region hierarchy
and species-list APIs. See docs/features/life-list.md.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.dao.ebird import EBirdConfigError
from app.models.life_list import LifeListEntry, RegionChecklistResponse, RegionOption
from app.services import life_list as life_list_service

router = APIRouter(tags=["life-list"])


@router.get("/users/{user_id}/life-list", response_model=list[LifeListEntry])
async def get_life_list(user_id: str):
    return await life_list_service.get_life_list(user_id)


@router.get("/regions", response_model=list[RegionOption])
async def list_regions(
    parent: str = Query(..., description="e.g. 'world' or a country/region code"),
    type: str = Query(..., description="country | subnational1 | subnational2"),
):
    try:
        return await life_list_service.get_region_children(parent, type)
    except EBirdConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"eBird error: {exc}") from exc


@router.get("/regions/{region_code}/checklist", response_model=RegionChecklistResponse)
async def region_checklist(region_code: str, user_id: str | None = None):
    try:
        return await life_list_service.get_region_checklist(region_code, user_id)
    except EBirdConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"eBird error: {exc}") from exc
