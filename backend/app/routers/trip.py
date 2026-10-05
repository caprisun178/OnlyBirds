"""Plan a Trip — see docs/features/plan-a-trip.md."""

from datetime import date

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.observation import Observation
from app.models.trip import TripPlan
from app.services import trip as trip_service

router = APIRouter(prefix="/trip", tags=["trip"])


@router.get("/plan", response_model=TripPlan)
async def plan(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    start_date: date = Query(),
    end_date: date = Query(),
    radius_km: int = Query(default=25, ge=1, le=200),
    user_id: str | None = Query(default=None),
):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    try:
        return await trip_service.plan_trip(
            lat=lat,
            lng=lng,
            start_date=start_date,
            end_date=end_date,
            radius_km=radius_km,
            user_id=user_id,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc


@router.get("/hotspot-sightings", response_model=list[Observation])
async def hotspot_sightings(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    start_date: date = Query(),
    end_date: date = Query(),
    radius_km: int = Query(default=2, ge=1, le=50),
    loc_id: str | None = Query(default=None),
):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    try:
        return await trip_service.hotspot_sightings(
            lat=lat,
            lng=lng,
            start_date=start_date,
            end_date=end_date,
            radius_km=radius_km,
            hotspot_loc_id=loc_id,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc
