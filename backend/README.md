# Only Birds — backend

FastAPI service that sits between the frontends and the external APIs
(iNaturalist v1, eBird 2.0), normalizes both into one internal `Observation`
model, and owns the derived per-user life list. See the root `README.md` for the
product rationale and full architecture.

## Layout

```
backend/
  app/
    main.py              FastAPI app factory, CORS, router wiring
    config.py            Settings (env / .env)
    dao/                 raw data access, no business logic
      ebird.py             eBird 2.0 REST calls (API key stays here)
      inaturalist.py       iNaturalist v1 REST calls (no auth needed)
      observation_repo.py  in-memory store for user observations (Protocol seam
                           for the Postgres impl in roadmap step 3)
    services/            business logic
      adapters.py          external JSON -> internal Observation
      sightings.py         fan out to both APIs, return one sorted feed
      species.py           iNat taxa search -> SpeciesRef
      observation.py       log / list user observations
      life_list.py         derive the life list from observation history
    models/              Pydantic shapes (Observation, SpeciesRef, LifeListEntry, User)
    routers/             HTTP endpoints
  tests/                 pytest (TestClient; no network)
```

The `dao` / `services` split and the "layer identity comes from named exports,
folder path indicates the layer" convention mirror the frontend rules in the
root README.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` , `/health` | liveness + whether the eBird key is configured |
| GET | `/species/search?q=` | iNaturalist taxon autocomplete (proves iNat connectivity) |
| GET | `/sightings/nearby?lat=&lng=&radius_km=&days_back=&source=` | normalized eBird + iNat feed (proves eBird connectivity) |
| GET | `/users/{user_id}/observations` | user's observations, newest first |
| POST | `/observations` | log an observation |
| GET | `/observations/{id}` | fetch one observation |
| GET | `/users/{user_id}/life-list` | life list derived from stored observations |

Interactive docs at `/docs`.

## Run locally (Windows / PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then add your EBIRD_API_KEY
uvicorn main:app --reload
```

macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate`, then
`cp .env.example .env`.

Visit `http://localhost:8000/docs`. `/species/search?q=raven` works with no key;
`/sightings/nearby` returns iNat results with no key and adds eBird results once
`EBIRD_API_KEY` is set.

## Tests

```powershell
pip install -r requirements.txt
pytest
```

Tests use FastAPI's `TestClient` and never hit the network — the external DAOs
are exercised only through the adapter unit tests with canned payloads.

## Not done yet (later roadmap steps)

- PostgreSQL + PostGIS persistence (swap `InMemoryObservationRepo`; the
  `ObservationRepo` Protocol is the injection point).
- Auth-provider token verification (`User.auth_provider_id` is currently trusted
  as passed).
- Resolving external `source_ids` into our own `species` rows so cross-source
  dedupe in the life list is id-based rather than name-based.
