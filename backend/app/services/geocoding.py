"""Address search and reverse-geocode for the Add Observation location picker.

Normalizes Nominatim's raw JSON into `PlaceResult` so callers never see OSM's
field names (`lat`/`lon` as strings, etc.) directly.
"""

from __future__ import annotations

from app.dao import nominatim
from app.models.geocoding import PlaceResult


def _to_place(raw: dict) -> PlaceResult:
    return PlaceResult(
        display_name=raw["display_name"],
        lat=float(raw["lat"]),
        lng=float(raw["lon"]),
    )


async def search_places(query: str) -> list[PlaceResult]:
    results = await nominatim.search(query)
    return [_to_place(r) for r in results]


async def reverse_geocode(lat: float, lng: float) -> PlaceResult | None:
    result = await nominatim.reverse(lat, lng)
    return _to_place(result) if result else None
