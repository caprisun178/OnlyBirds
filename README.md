# Only Birds — iNaturalist + eBird + Life List

A cross-platform (web + mobile) application that combines species observation logging (à la iNaturalist) and bird-sighting data (à la eBird) into a unified personal life list.

## Tech Stack

| Layer | Technology |
|---|---|
| Web frontend | React |
| Mobile frontend | React Native |
| Backend | Python — FastAPI |
| Database | PostgreSQL + PostGIS |
| Auth | Hosted provider (Auth0 or Supabase Auth) |
| Hosting | TBD |

## Why a backend server

The FastAPI backend sits between the frontends and the external APIs for three reasons:

1. **Secret management** — the eBird API requires an API key that cannot be exposed in a client app.
2. **Schema normalization** — iNaturalist and eBird return different JSON shapes for what is conceptually the same thing (a sighting of a species by a person at a place/time). The backend translates both into one internal `Observation` model.
3. **Life list ownership** — the life list is derived from a user's own observation history and needs to persist independently of either external API, so it lives in our own database.

## Architecture

```
┌─────────────┐     ┌─────────────┐
│  React Web  │     │React Native │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                  │  HTTPS/JSON
          ┌───────▼────────┐
          │ FastAPI backend │
          │  Auth layer     │
          │  Life-list      │
          │   service       │
          │  Adapter layer  │
          └───┬─────────┬───┘
              │         │
      ┌───────▼──┐   ┌──▼──────────┐    ┌──────────────┐
      │PostgreSQL│   │ iNaturalist │    │  eBird API   │
      │ +PostGIS │   │   API v1    │    │    2.0       │
      └──────────┘   └─────────────┘    └──────────────┘
```

### Frontend layering (DAO / Services / Presenters)

```
/src
  /dao          → raw API access only, no logic (talks to our FastAPI backend)
  /services     → business logic; transforms DAO output into UI-ready shape
  /presenters   → smart components — own state, event handlers (onClick/onSubmit), render JSX
  /components   → pure, reusable, presentational only — no state, no DAO/Service imports
  /models       → shared data shapes
```

**Rules:**
- The folder path indicates the layer — no `DAO`/`Service` suffix in filenames (e.g. `dao/observation.js`, `services/observation.js`).
- Layer identity at the import site comes from named exports, not filenames: `export const observationDAO = {...}` / `export const observationService = {...}`.
- `/components` must never import from `/services` or `/dao` — only `/presenters` may. (Consider an ESLint import-restriction rule to enforce this.)

Example:

```js
// dao/observation.js
export const observationDAO = {
  getAll: (userId) => apiClient.get(`/users/${userId}/observations`),
  create: (payload) => apiClient.post(`/observations`, payload),
};

// services/observation.js
import { observationDAO } from '../dao/observation';

export const observationService = {
  async logObservation(userId, input) {
    return observationDAO.create(input);
  },
};

// presenters/AddObservation.jsx
import { observationService } from '../services/observation';
// owns useState, defines handleSubmit, renders <form> with components from /components
```

## External APIs

### eBird API 2.0 (bird sightings)

- Get a free API key: https://ebird.org/api/keygen
- Docs: https://documenter.getpostman.com/view/664302/S1ENwy59
- Python wrapper: `pip install ebird-api` — https://github.com/ProjectBabbler/ebird-api

```python
# dao/ebird.py
import os
from ebird.api import get_nearby_observations

EBIRD_API_KEY = os.environ["EBIRD_API_KEY"]

def get_nearby_bird_sightings(lat, lng, dist_km=25, days_back=7):
    return get_nearby_observations(EBIRD_API_KEY, lat, lng, dist=dist_km, back=days_back)
```

### iNaturalist API v1 (species / observation data)

- Docs: https://api.inaturalist.org/v1/docs/
- No auth required for reads. OAuth2 only needed if writing observations on a user's behalf.

```python
# dao/inaturalist.py
import httpx

INAT_BASE = "https://api.inaturalist.org/v1"

async def search_species(query: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{INAT_BASE}/taxa", params={"q": query})
        return resp.json()
```

### Image identification (computer vision) — important caveat

iNaturalist's full species-classification model is **not** publicly available. Their own forum staff have confirmed there is no supported public API for it — the endpoint their apps use internally is undocumented and not meant for third-party use. Do not build core functionality on it.

Usable alternatives:

- **Self-host a subset of their approach**: `inatVisionAPI` (https://github.com/inaturalist/inatVisionAPI) is iNaturalist's own open-sourced Flask + TensorFlow server.
- **Public "small" model weights** (~500 taxa + taxonomy + geographic prior): https://github.com/inaturalist/model-files — suitable for on-device/small-scale use.
- **De-scope for MVP**: ship with manual species tagging first, add CV as a stretch goal once the core observation/life-list flow works.

## Database schema (starting point)

- `users` — id, email, auth provider id
- `species` — id, scientific_name, common_name, taxon_group, source_ids (iNaturalist taxon_id / eBird species_code)
- `observations` — id, user_id, species_id, lat, lng, observed_at, source (inat/ebird/manual), source_observation_id, photo_url, notes
- `life_list_entries` — id, user_id, species_id, first_observed_at, observation_id

## Getting the backend running locally

```bash
pip install fastapi uvicorn ebird-api httpx python-dotenv
cp .env.example .env   # add your EBIRD_API_KEY
uvicorn main:app --reload
```

Visit `localhost:8000/docs` to confirm both external API calls return data.

## Roadmap

1. Scaffold FastAPI backend, deploy a "hello world" endpoint
2. Get one real call working against each external API (prove connectivity)
3. Set up Postgres schema, basic `/observations` and `/life-list` endpoints
4. Scaffold React app hitting our own API
5. CV integration (stretch goal)
