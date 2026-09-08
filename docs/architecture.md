# Architecture

## Why a backend at all

The FastAPI service sits between the frontends and the external APIs for three
reasons (from the root `README.md`):

1. **Secret management** — the eBird API key must not ship in a client app.
2. **Schema normalization** — iNaturalist and eBird return different JSON for the
   same concept (a sighting of a species by someone at a place and time). The
   backend translates both into one internal `Observation`.
3. **Life-list ownership** — the life list is derived from a user's own
   observation history and persists independently of either external API.

## Request flow

```text
React Web / React Native
        │  HTTPS / JSON
        ▼
┌─────────────────────────────┐
│ FastAPI backend             │
│  routers/   HTTP surface    │
│  services/  business logic  │
│   ├─ adapters   ext → Observation
│   ├─ sightings  fan-out + merge
│   ├─ species    iNat taxa search
│   ├─ observation  log / list
│   └─ life_list    derive from history
│  dao/       raw data access │
└───┬──────────────┬──────────┘
    │              │
    ▼              ▼
in-memory      iNaturalist v1 + eBird 2.0
observation
store
(→ Postgres,
 roadmap 3)
```

## Backend layers

| Folder | Responsibility | Rule |
|---|---|---|
| `app/routers/` | HTTP endpoints, request validation, status codes | no external-API calls, no persistence details |
| `app/services/` | business logic; the adapter layer lives here | may call `dao/`, never imported by `dao/` |
| `app/dao/` | raw calls to eBird, iNaturalist, and the observation store | no business logic, no knowledge of HTTP |
| `app/models/` | shared Pydantic shapes | imported anywhere |

`app/dao/observation_repo.py` defines an `ObservationRepo` `Protocol` with an
`InMemoryObservationRepo` implementation. Roadmap step 3 swaps in a
PostgreSQL + PostGIS implementation behind the same protocol.

## Data model

Pydantic models in `app/models/`, mirroring the README's starting schema:

- `SpeciesRef` — `scientific_name`, `common_name`, `taxon_group`, `source_ids`
  (`{"inat": ..., "ebird": ...}`)
- `Observation` — `user_id`, `species` / `species_id`, `lat`, `lng`,
  `observed_at`, `source` (`inat` / `ebird` / `manual`), `source_observation_id`,
  `photo_url`, `notes`
- `LifeListEntry` — `user_id`, `species`, `first_observed_at`, `observation_id`
- `User` — `auth_provider_id`, `email` (token verification not implemented yet)

## Normalization

`app/services/adapters.py` converts each external record into `Observation`:

- `from_ebird()` — maps `sciName` / `comName` / `speciesCode`, `obsDt`,
  `lat` / `lng`, `subId`.
- `from_inaturalist()` — maps `taxon.*`, `time_observed_at` / `observed_on`,
  `geojson` coordinates (`[lng, lat]`), first photo, `description`.

The life list (`app/services/life_list.py`) then collapses observations to one
entry per species, keyed by our `species_id` → an external source id → the
scientific name, dated to the earliest sighting.
