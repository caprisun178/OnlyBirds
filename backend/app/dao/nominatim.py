"""
==============================
Nominatim (OpenStreetMap) geocoding
Description:
Raw access to OSM's free, keyless geocoding API — no business logic. Backs
the Add Observation location picker's address search and reverse-geocode
(pin -> readable place name). No auth needed, but their usage policy caps
the public instance at ~1 request/second and requires a real User-Agent —
fine here since it's one manual search per user action, never a loop.

Docs: https://nominatim.org/release-docs/latest/api/Overview/
Usage policy: https://operations.osmfoundation.org/policies/nominatim/
=============================
"""

import httpx

from app.config import get_settings

_BASE_URL = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"}


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        timeout=settings.http_timeout_seconds,
        headers=_HEADERS,
    )


async def search(query: str, limit: int = 5) -> list[dict]:
    """Forward geocode: free-text address/place name -> candidate matches."""
    async with _client() as client:
        resp = await client.get(
            "/search", params={"q": query, "format": "json", "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()


async def reverse(lat: float, lng: float) -> dict | None:
    """Reverse geocode: a point -> its readable place name."""
    async with _client() as client:
        resp = await client.get(
            "/reverse", params={"lat": lat, "lon": lng, "format": "json"}
        )
        resp.raise_for_status()
        body = resp.json()
        return None if "error" in body else body
