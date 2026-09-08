"""Nearby sightings — normalized feed from eBird + iNaturalist (roadmap step 2)."""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.observation import Observation
from app.services import sightings as sightings_service

router = APIRouter(prefix="/sightings", tags=["sightings"])


@router.get("/nearby", response_model=list[Observation])
async def nearby_sightings(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: int = Query(default=25, ge=1, le=200),
    days_back: int = Query(default=7, ge=1, le=30),
    source: str = Query(default="all", pattern="^(all|ebird|inat)$"),
):
    try:
        return await sightings_service.nearby(
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            days_back=days_back,
            include_ebird=source in ("all", "ebird"),
            include_inat=source in ("all", "inat"),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc
