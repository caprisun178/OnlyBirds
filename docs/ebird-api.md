# eBird API

How the backend talks to eBird — auth, where the calls live, what's wired up
today versus only planned, and how failures behave. For the API *we* expose,
see [Backend API](backend.md).

## Get a key

Free, from <https://ebird.org/api/keygen> — full steps in
[Environment Setup](index.md#2-get-an-ebird-api-key). It goes in `backend/.env`
as `EBIRD_API_KEY`, never in client code or version control.

## Auth & base config

| Setting | Value | Defined in |
|---|---|---|
| Base URL | `https://api.ebird.org/v2` | `Settings.ebird_base_url`, `backend/app/config.py` |
| Auth header | `X-eBirdApiToken: <EBIRD_API_KEY>` | `backend/app/dao/ebird.py` (`_client()`) |
| Timeout | `Settings.http_timeout_seconds` (default `15.0`) | `backend/app/config.py` |
| Full API reference | <https://documenter.getpostman.com/view/664302/S1ENwy59> | — |

The key is **optional** at the process level — the server still starts and
serves iNaturalist-only results without one. `GET /health` reports whether
it's set via `ebird_key_configured`.

## Where calls live

Per the [dao/services/routers layering rule](contributing.md#backend-conventions),
all eBird HTTP calls live in `backend/app/dao/ebird.py` and nowhere else.
`app/services/adapters.py` maps raw eBird JSON into our own `Observation` /
`SpeciesRef` models before anything downstream sees it — routers and other
services never see eBird's field names directly.

```text
routers/sightings.py  →  services/sightings.py  →  dao/ebird.py  →  api.ebird.org
                              │
                              └─▶ services/adapters.py (from_ebird)
```

## Endpoints in use today

Only one eBird endpoint is actually called right now:

| Endpoint | dao function | Params | Used by |
|---|---|---|---|
| `GET /data/obs/geo/recent` | `get_nearby_bird_sightings()` in `dao/ebird.py` | `lat`, `lng`, `dist` (km), `back` (days) | `GET /sightings/nearby` |

## Endpoints referenced by planned features

These appear in the [feature docs](features/overview.md) as design intent but
have **no `dao/ebird.py` function yet** — don't assume they're implemented:

| Endpoint | Purpose | Planned for |
|---|---|---|
| `GET /ref/taxonomy/ebird` | canonical species names / codes | [Bird info](features/bird-info.md), [Life List](features/life-list.md) |
| `GET /ref/region/list/{type}/{parentCode}` | region picker options | [Life List](features/life-list.md) |
| `GET /product/spplist/{regionCode}` | species checklist for a region | [Life List](features/life-list.md) |
| `GET /data/obs/{regionCode}/recent` | recent sightings in a region | [Explore map](features/explore-map.md) |
| `GET /data/obs/{regionCode}/recent/notable` | notable (rare) sightings in a region | [Explore map](features/explore-map.md) |

When you implement one, add it to `dao/ebird.py`, move its row up into the
table above, and follow [Adding a new call](#adding-a-new-call) below.

## Request / response shape

A raw eBird sighting looks like this (from the `EBIRD_RECORD` fixture in
`backend/tests/test_adapters.py`):

```json
{
  "speciesCode": "compoo",
  "comName": "Common Poorwill",
  "sciName": "Phalaenoptilus nuttallii",
  "locName": "Desert NWR",
  "obsDt": "2026-05-01 06:30",
  "subId": "S12345678",
  "lat": 36.4,
  "lng": -115.35
}
```

`adapters.from_ebird()` maps it to an `Observation` with `source = "ebird"`,
`source_observation_id = subId`, and `species.source_ids = {"ebird": speciesCode}`
— see [Architecture](architecture.md) for the full model shapes.

## Error & failure behavior

These two failure modes look similar but behave very differently — know which
one you're hitting:

- **No key configured.** `dao/ebird.py` raises `EBirdConfigError` before any
  HTTP call is made. `services/sightings.py` catches *only* this exception and
  returns an empty eBird list — the request still succeeds with iNaturalist
  results only.
- **Key present but invalid, rate-limited, or eBird is down.** The `httpx`
  call raises `httpx.HTTPError` (via `raise_for_status()`), which is **not**
  caught in `services/sightings.py`. It propagates up to
  `routers/sightings.py`, which turns it into `HTTP 502` with
  `"Upstream API error: ..."` — the whole `/sightings/nearby` request fails,
  including its iNaturalist half.

So an invalid key doesn't degrade gracefully like a missing one does — it
breaks the endpoint. If you see "eBird requests return 403 / empty", the key
is missing or wrong in `backend/.env`; restart uvicorn after editing it.

## No caching or rate-limiting yet

Every call to `GET /sightings/nearby?source=ebird` hits eBird live — there's
no retry, backoff, or response cache in the codebase today. The
`sighting_cache` and `region_checklists` tables described in
[Database & migrations](features/database.md) and
[Explore map](features/explore-map.md) are designed to change that, but
aren't built yet. Until they land, avoid tight loops against live eBird
endpoints (including while manually testing) — batch or space out requests.

## Testing offline

`backend/tests/test_adapters.py` asserts `from_ebird()` mapping against a
canned payload — no test hits the live API, and `python -m pytest` must
always pass with no key set. There's no `httpx`-level mock (e.g. `respx`) in
use yet; when you add a new `dao/ebird.py` call, add a similar canned-fixture
adapter test rather than calling eBird from a test.

## Adding a new call

1. Add the function to `backend/app/dao/ebird.py`, using the existing
   `_client()` helper for auth/timeout.
2. Map its response shape in `app/services/adapters.py` (or a new adapter) so
   downstream code only ever sees our own models.
3. Call it from `app/services/`, never directly from `app/routers/`.
4. Add a canned-payload test under `backend/tests/`.
5. Move its row from "planned" to "in use today" in this page.
