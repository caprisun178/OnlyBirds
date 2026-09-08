"""Raw access to the iNaturalist API v1 — no business logic.

No auth required for reads. OAuth2 would only be needed to write observations on
a user's behalf, which the base server does not do.

Docs: https://api.inaturalist.org/v1/docs/
"""

import httpx

from app.config import get_settings


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.inat_base_url,
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"},
    )


async def search_species(query: str, per_page: int = 20) -> list[dict]:
    """Taxon autocomplete — returns the raw `results` array from /taxa."""
    async with _client() as client:
        resp = await client.get("/taxa", params={"q": query, "per_page": per_page})
        resp.raise_for_status()
        return resp.json().get("results", [])


async def get_taxon(taxon_id: int | str) -> dict | None:
    async with _client() as client:
        resp = await client.get(f"/taxa/{taxon_id}")
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


async def get_nearby_observations(
    lat: float,
    lng: float,
    radius_km: int = 25,
    per_page: int = 30,
) -> list[dict]:
    """Recent research-grade observations near a point."""
    params = {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "per_page": per_page,
        "order_by": "observed_on",
        "order": "desc",
    }
    async with _client() as client:
        resp = await client.get("/observations", params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])
