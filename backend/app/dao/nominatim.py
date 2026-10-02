"""
==============================
Nominatim (OpenStreetMap) geocoding
Description:
Raw access to OSM's free, keyless geocoding API — no business logic. Backs
the Add Observation location picker's address search and reverse-geocode
(pin -> readable place name), and Explore Map's place search. No auth
needed, but their usage policy caps the public instance at ~1 request/second
and requires a real User-Agent.

That "~1 request/second" ceiling used to be a non-issue when this was one
manual search per user action. It stopped being one once Explore Map's
search grew live-as-you-type suggestions (a request per debounced
keystroke, not per click) — real, measured slowness followed, partly
Nominatim's own response time and partly this module reopening a fresh
TCP+TLS connection to it on every single call. `_get_client()`/`search()`'s
cache below address both: a shared persistent connection avoids repeating
the handshake, and a short cache means retyping/pausing/re-searching the
same string doesn't hit Nominatim (or the usage-policy ceiling) again at
all.

Docs: https://nominatim.org/release-docs/latest/api/Overview/
Usage policy: https://operations.osmfoundation.org/policies/nominatim/
=============================
"""

import time

import httpx

from app.config import get_settings

_BASE_URL = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "OnlyBirds/0.1 (+https://github.com/)"}

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """A single shared, persistent client — reused across every call instead
    of opening (and immediately closing) a fresh TCP+TLS connection per
    request, the same way `app/dao/db.py#get_pool()` reuses one Postgres
    connection pool instead of reconnecting per query.
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=settings.http_timeout_seconds,
            headers=_HEADERS,
        )
    return _client


_SEARCH_CACHE_TTL_SECONDS = 60
_SEARCH_CACHE_MAX_ENTRIES = 200  # crude bound: a hobby-scale cache, not worth a real LRU — just clear it if it ever gets this big
_search_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}


async def search(query: str, limit: int = 5) -> list[dict]:
    """Forward geocode: free-text address/place name -> candidate matches.

    Cached briefly per exact (query, limit) — live-as-you-type search
    legitimately re-requests the same string (pause then resume typing,
    backspace back to an earlier prefix, reopen a just-used search), and
    each cache hit is also one fewer request against Nominatim's ~1 req/sec
    usage-policy ceiling, not just a latency win.
    """
    cache_key = (query.strip().lower(), limit)
    cached = _search_cache.get(cache_key)
    if cached is not None and (time.monotonic() - cached[0]) < _SEARCH_CACHE_TTL_SECONDS:
        return cached[1]

    client = _get_client()
    resp = await client.get(
        "/search", params={"q": query, "format": "json", "limit": limit}
    )
    resp.raise_for_status()
    results = resp.json()

    if len(_search_cache) >= _SEARCH_CACHE_MAX_ENTRIES:
        _search_cache.clear()
    _search_cache[cache_key] = (time.monotonic(), results)
    return results


async def reverse(lat: float, lng: float) -> dict | None:
    """Reverse geocode: a point -> its readable place name."""
    client = _get_client()
    resp = await client.get(
        "/reverse", params={"lat": lat, "lon": lng, "format": "json"}
    )
    resp.raise_for_status()
    body = resp.json()
    return None if "error" in body else body
