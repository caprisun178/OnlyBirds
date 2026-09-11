# Only Birds — iNaturalist + eBird + Life List

A cross-platform application that combines species observation logging (à la
iNaturalist) with bird-sighting data (à la eBird) into one personal life list.

> **New here?** → [Set up & test your changes](docs/setup-and-test.md) — clone to
> open PR in six steps.

## Documentation

The full docs are a MkDocs site under [`docs/`](docs/):

```bash
pip install -r docs/requirements.txt
mkdocs serve          # http://127.0.0.1:8000
```

| Page | What's in it |
|---|---|
| [Set up & test your changes](docs/setup-and-test.md) | the short contributor path: run the backend, branch, test, open a PR |
| [Environment Setup](docs/index.md) | prerequisites, env vars, editor setup, troubleshooting |
| [Architecture](docs/architecture.md) | why there's a backend, the request flow, the layer rules |
| [Features](docs/features/overview.md) | one page per feature — screens, data, SQL, API, code layout, build order |
| [Database & migrations](docs/features/database.md) | where data lives, SQL conventions, the baseline schema, running a migration |
| [Backend API](docs/backend.md) | the endpoints the apps call |
| [Deployment](docs/deployment.md) | Supabase + Render setup, secrets, going to production |
| [Contributing](docs/contributing.md) | branch & PR workflow, backend conventions, the styling standard |

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python — FastAPI |
| Database | PostgreSQL + PostGIS (Supabase) |
| Auth | Supabase Auth (token verification is a follow-up) |
| Web frontend | HTML + CSS — shared design system in `frontend/styles/base.css` |
| Mobile | planned; approach TBD |
| Hosting | backend on **Render**; database, auth, and file storage on **Supabase** |

## Why a backend server

The FastAPI backend sits between the frontends and the external APIs for three
reasons:

1. **Secret management** — the eBird API key cannot ship in a client app.
2. **Schema normalization** — iNaturalist and eBird return different JSON for the
   same concept (a sighting of a species by someone at a place and time). The
   backend translates both into one internal `Observation`.
3. **Life-list ownership** — the life list is derived from a user's own
   observation history and must persist independently of either external API, so
   it lives in our own database.

## External APIs

Called only from `backend/app/dao/`; see [Architecture](docs/architecture.md) for
how they're normalized.

- **eBird API 2.0** — sightings, regions, taxonomy. Free key:
  <https://ebird.org/api/keygen>
- **iNaturalist API v1** — taxon search, observations. No key for reads.

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
