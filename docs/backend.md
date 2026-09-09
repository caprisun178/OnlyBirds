# Backend API

Base URL in development: `http://localhost:8000`. Interactive docs (OpenAPI) at
`/docs`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | name, version, link to `/docs` |
| `GET` | `/health` | `status`, `version`, `ebird_key_configured` |
| `GET` | `/species/search?q=` | iNaturalist taxon autocomplete → `SpeciesRef[]` |
| `GET` | `/sightings/nearby` | normalized eBird + iNaturalist feed → `Observation[]` |
| `GET` | `/users/{user_id}/observations` | that user's observations, newest first |
| `POST` | `/observations` | log an observation (`ObservationCreate`) → `201` |
| `GET` | `/observations/{id}` | one observation, or `404` |
| `GET` | `/users/{user_id}/life-list` | life list derived from stored observations |

### `GET /sightings/nearby`

| Query param | Type | Default | Notes |
|---|---|---|---|
| `lat` | float | — | required, −90…90 |
| `lng` | float | — | required, −180…180 |
| `radius_km` | int | 25 | 1…200 |
| `days_back` | int | 7 | 1…30 (eBird only) |
| `source` | enum | `all` | `all` \| `ebird` \| `inat` |

With no `EBIRD_API_KEY` configured, eBird results are silently omitted.

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
```

## Running & testing

See [Environment Setup](index.md#3-back-end-setup). In short, from `backend/`:

```bash
python -m uvicorn main:app --reload   # serve
python -m pytest                       # test (offline, no key)
```

## Known limitations

- Observations live in an in-memory store — they reset on restart. Moving to
  Postgres is in progress; see [Deployment](deployment.md).
- `user_id` / `auth_provider_id` are trusted as passed; no token verification.
- Cross-source species dedupe in the life list is name-based until external
  `source_ids` are resolved to our own `species` rows.
