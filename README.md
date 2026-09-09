# Only Birds — iNaturalist + eBird + Life List

A cross-platform application that combines species observation logging (à la
iNaturalist) with bird-sighting data (à la eBird) into one personal life list.

## Documentation

Full docs are a MkDocs site under [`docs/`](docs/). Read it locally with:

```bash
pip install -r docs/requirements.txt
mkdocs serve          # http://127.0.0.1:8000
```

| Page | What's in it |
|---|---|
| [Environment Setup](docs/index.md) | everything a new contributor needs to run the backend and docs locally |
| [Architecture](docs/architecture.md) | why there's a backend, the request flow, the layer rules |
| [Features](docs/features/overview.md) | one page per feature — screens, data sources, SQL, API, code layout, build order |
| [Database & migrations](docs/features/database.md) | where data lives, the SQL conventions, the baseline schema, how to run a migration |
| [Backend API](docs/backend.md) | the endpoints the apps call |
| [Deployment](docs/deployment.md) | Supabase + Render setup, secrets, going to production |
| [Contributing](docs/contributing.md) | branch & PR workflow, backend conventions, the frontend styling standard |

## Tech stack

| Layer | Technology |
|---|---|
| Web frontend | HTML + CSS, no framework — shared design system in [`frontend/styles/base.css`](frontend/styles/base.css) |
| Mobile | planned; approach TBD |
| Backend | Python — FastAPI |
| Database | PostgreSQL + PostGIS (Supabase) |
| Auth | Supabase Auth (token verification is a follow-up) |
| Hosting | Backend on Render; database, auth, and file storage on Supabase |

## Why a backend server

The FastAPI backend sits between the frontends and the external APIs for three
reasons:

1. **Secret management** — the eBird API key cannot ship in a client app.
2. **Schema normalization** — iNaturalist and eBird return different JSON for
   the same concept (a sighting of a species by someone at a place and time).
   The backend translates both into one internal `Observation`.
3. **Life-list ownership** — the life list is derived from a user's own
   observation history and must persist independently of either external API,
   so it lives in our own database.

## Repository layout

```text
OnlyBirds/
├── backend/            FastAPI service (Python)
│   ├── app/            routers / services / dao / models
│   ├── migrations/     numbered .sql files (see docs/features/database.md)
│   ├── scripts/        migrate.sh
│   └── tests/          pytest, offline
├── frontend/
│   ├── styles/         shared design system — base.css + its guide
│   ├── home/           landing page (static HTML/CSS, deploys on its own)
│   └── src/            app logic skeleton (dao / services / …)
├── docs/               the MkDocs site
├── render.yaml         Render deployment blueprint
└── .github/            CI workflow + PR template
```

## Quick start

**Backend** (full instructions: [Environment Setup](docs/index.md)):

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows; use bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env                                # then add EBIRD_API_KEY
python -m uvicorn main:app --reload                   # http://localhost:8000/docs
python -m pytest                                      # offline, no key needed
```

**Database** — create a Supabase project, then apply migrations
([Deployment](docs/deployment.md) has the detail):

```bash
export DATABASE_URL="postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
./backend/scripts/migrate.sh
```

**Landing page** — open `frontend/home/index.html`, or `cd frontend/home &&
python -m http.server 4173`.

## Core data model

The baseline is `backend/migrations/0001_baseline.sql`; features extend it (see
[Database & migrations](docs/features/database.md)).

- `users` — `id`, `auth_provider_id`, `email`
- `species` — `id`, `scientific_name`, `common_name`, `taxon_group`,
  `ebird_code`, `inat_taxon_id`
- `observations` — `id`, `user_id`, `species_id`, `lat`, `lng`, `observed_at`,
  `source` (`manual` / `inat` / `ebird`), `source_observation_id`, `photo_url`,
  `notes`
- `life_list_entries` — `id`, `user_id`, `species_id`, `first_observed_at`,
  `observation_id`

## External APIs

Both are called only from `backend/app/dao/`. See
[Architecture](docs/architecture.md) for how they're normalized.

- **eBird API 2.0** — bird sightings, regions, taxonomy. Free key:
  <https://ebird.org/api/keygen> · docs:
  <https://documenter.getpostman.com/view/664302/S1ENwy59>
- **iNaturalist API v1** — taxon search, observations. No key for reads. Docs:
  <https://api.inaturalist.org/v1/docs/>

### Computer vision — important caveat

iNaturalist's full species-classification model is **not** publicly available —
their staff have confirmed there is no supported public API. Do not build core
functionality on it. MVP ships **manual + describe-and-guess** identification
(see [Add Observation](docs/features/add-observation.md)); automatic photo ID is
a later stretch goal behind the same endpoint, via a self-hosted
[`inatVisionAPI`](https://github.com/inaturalist/inatVisionAPI) or the public
["small" model weights](https://github.com/inaturalist/model-files).

## Status

- Backend runs and is deployed on Render; eBird + iNaturalist calls work.
- Supabase database is set up and the baseline migration exists — but the app
  still uses an in-memory store; moving `/observations` and `/life-list` onto
  Postgres is the current work.
- Frontend is early: a landing page and the shared design system.

Roadmap and the branch/PR workflow are in [Contributing](docs/contributing.md).
