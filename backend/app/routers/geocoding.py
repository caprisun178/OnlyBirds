"""Location-picker endpoints for Add Observation — address search and
reverse-geocode, both proxying Nominatim (OpenStreetMap) server-side so the
API key-less usage-policy header lives in one place.

    GET /geocode/search?q=            free text -> candidate places
    GET /geocode/reverse?lat=&lng=    a point -> its readable place name
"""

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.models.geocoding import PlaceResult
from app.services import geocoding as geocoding_service

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("/search", response_model=list[PlaceResult])
async def search(q: str = Query(min_length=1)):
    try:
        return await geocoding_service.search_places(q)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding error: {exc}") from exc


@router.get("/reverse", response_model=PlaceResult | None)
async def reverse(lat: float, lng: float):
    try:
        return await geocoding_service.reverse_geocode(lat, lng)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding error: {exc}") from exc
