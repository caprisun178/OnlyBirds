"""Raw access to the eBird API 2.0 — no business logic.

We call the REST endpoint directly with httpx (async, one fewer dependency)
rather than the `ebird-api` wrapper suggested in the README. The API key is read
from settings and sent as the `X-eBirdApiToken` header; it never leaves the
backend.

Docs: https://documenter.getpostman.com/view/664302/S1ENwy59
"""

import httpx

from app.config import get_settings


class EBirdConfigError(RuntimeError):
    """Raised when the eBird API key is not configured."""


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    if not settings.ebird_api_key:
        raise EBirdConfigError("EBIRD_API_KEY is not set")
    return httpx.AsyncClient(
        base_url=settings.ebird_base_url,
        headers={"X-eBirdApiToken": settings.ebird_api_key},
        timeout=settings.http_timeout_seconds,
    )


async def get_nearby_bird_sightings(
    lat: float,
    lng: float,
    dist_km: int = 25,
    days_back: int = 7,
) -> list[dict]:
    """Recent bird observations within `dist_km` of a point."""
    params = {"lat": lat, "lng": lng, "dist": dist_km, "back": days_back}
    async with _client() as client:
        resp = await client.get("/data/obs/geo/recent", params=params)
        resp.raise_for_status()
        return resp.json()
