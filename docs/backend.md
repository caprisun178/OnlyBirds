# Backend API

Base URL in development: `http://localhost:8000`. Interactive docs (OpenAPI) at
`/docs`.

## Endpoints

The core, cross-feature endpoints — the ones most things end up calling.
Geocoding (`/geocode/search`, `/geocode/reverse`), identification
(`/identify/...`), photo uploads (`/uploads/photos`), and user accounts
(`/users`, `/users/{username}`) are documented on their own feature pages
([Add Observation](features/add-observation.md),
[User profiles](features/user-profiles.md)) instead of duplicated here.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | name, version, link to `/docs` |
| `GET` | `/health` | `status`, `version`, `ebird_key_configured` |
| `GET` | `/species/search?q=` | iNaturalist taxon autocomplete → `SpeciesRef[]` |
| `POST` | `/species/photos` | body `SpeciesRef[]` (only `scientific_name`/`common_name` used) → `SpeciesPhoto[]`, a guaranteed real-or-placeholder photo per species — backs Explore Map's species-filter suggestions |
| `GET` | `/sightings/nearby` | normalized eBird + iNaturalist + our own logged observations → `Observation[]` |
| `GET` | `/users/{user_id}/observations` | that user's observations, newest first |
| `POST` | `/observations` | log an observation (`ObservationCreate`) → `201` |
| `GET` | `/observations/{id}` | one observation, or `404` |
| `PATCH` | `/observations/{id}` | edit an observation (`ObservationUpdate` — every field optional, only what's sent gets touched), or `404` |
| `GET` | `/users/{user_id}/life-list` | life list derived from stored observations |

### `GET /sightings/nearby`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `lat` | float | — | required, −90…90 |
| `lng` | float | — | required, −180…180 |
| `radius_km` | int | 25 | 1…200 |
| `days_back` | int | 7 | 1…30 — applies to eBird, our own, **and** iNaturalist (see note below) |
| `source` | enum | `all` | `all` \| `ebird` \| `inat` \| `manual` (our own logged observations) |

With no `EBIRD_API_KEY` configured, eBird results are silently omitted — see
[eBird API](ebird-api.md) for auth, endpoints, and failure behavior. Our own
observations (`source=manual`) come from `observations` directly — no
external call, no key needed — filtered by radius via
`dao/observation_repo.py#list_near` (haversine in Python; there's no
PostGIS geom column yet, see [Explore map](features/explore-map.md)), and
scoped to `status = 'logged'` rows from any user, not just the caller.

!!! note "iNaturalist results had no date filtering at all — a real bug"
    `dao/inaturalist.py#get_nearby_observations()` sorted results
    newest-first (`order_by=observed_on&order=desc`) but never actually
    excluded anything by date — so a "Since: Last 7 days" request could
    still surface an iNaturalist sighting from 8 months ago, as long as it
    ranked within the first page of results (a real report: a February
    sighting showing up with "Last 7 days" selected in October). Fixed by
    passing `days_back` through as iNaturalist's own `d1` date-range param —
    `app/services/sightings.py#_safe_inat()` now forwards it instead of
    dropping it. Verified live: the same area/radius returns iNat sightings
    for `days_back=30` that correctly disappear at `days_back=7`.
    `tests/test_inaturalist.py` and `tests/test_sightings.py` cover it.

## Examples

```bash
curl 'http://localhost:8000/health'

curl 'http://localhost:8000/species/search?q=raven'

curl 'http://localhost:8000/sightings/nearby?lat=47.66&lng=-122.31&radius_km=10'

curl -X POST 'http://localhost:8000/observations' \
  -H 'Content-Type: application/json' \
  -d '{
        "user_id": "u1",
        "lat": 47.6, "lng": -122.33,
        "observed_at": "2026-05-01T08:00:00+00:00",
        "source": "manual",
        "species": {"scientific_name": "Corvus corax", "common_name": "Common Raven"}
      }'

curl 'http://localhost:8000/users/u1/life-list'

curl -X PATCH 'http://localhost:8000/observations/<id>' \
  -H 'Content-Type: application/json' \
  -d '{"notes": "Loud calling from the fence"}'
```

## Running & testing

See [Environment Setup](index.md#3-back-end-setup). In short, from `backend/`:

```bash
python -m uvicorn main:app --reload   # serve
python -m pytest                       # test (offline, no key)
```

## Known limitations

- Observations persist in Postgres (Neon) once `DATABASE_URL` is set —
  `PostgresObservationRepo` is used automatically
  (`app/dao/observation_repo.py`); without it (tests, or a fresh clone with
  no database configured yet), they fall back to an in-memory store that
  resets on restart. See [Deployment](deployment.md).
- `user_id` / `auth_provider_id` are trusted as passed; no token verification.
- Cross-source species dedupe in the life list is name-based until external
  `source_ids` are resolved to our own `species` rows.
