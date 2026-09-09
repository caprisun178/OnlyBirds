# Environment Setup

Everything a new contributor needs to get **Only Birds** running locally. If you
only touch the API, you can stop after [Run the tests](#4-run-the-tests).

## Repository layout

```text
OnlyBirds/
├── backend/        FastAPI service (Python) — the API the apps talk to
│   ├── app/        dao / services / models / routers
│   ├── migrations/ numbered .sql files
│   ├── scripts/    migrate.sh
│   └── tests/      pytest, no network
├── frontend/
│   ├── home/       landing page (static HTML/CSS)
│   └── src/        app skeleton — dao / services / presenters / components / styles
├── docs/           this MkDocs site
├── render.yaml     Render deployment blueprint
└── mkdocs.yml
```

The backend runs and is deployed. The frontend has a static landing page
(`frontend/home/`) and the shared design system (`frontend/src/styles/`); the
app screens come next. Layer rules are in
[Contributing](contributing.md#frontend-layering).

## Prerequisites

| Tool | Version | Needed for | Notes |
|---|---|---|---|
| Git | any recent | cloning | |
| Python | 3.13+ (3.13.14 known good) | backend | `python --version` |
| eBird API key | — | live bird sightings | free, see step 2. iNaturalist needs no key. |
| Node.js | — | frontend | not required — the frontend is plain HTML/CSS |
| PostgreSQL + PostGIS | 16 | persistence | needed to run migrations; the base server still runs on an in-memory store — see [Deployment](deployment.md) |
| `psql` client | any | migrations | only if you run `backend/scripts/migrate.sh`; otherwise use the Supabase SQL editor |

!!! note "Windows"
    Commands are shown for both PowerShell and bash. On Windows, prefer
    `python -m <tool>` (e.g. `python -m uvicorn`) so you don't depend on the
    Scripts directory being on `PATH` — see [Troubleshooting](#troubleshooting).

## 1. Clone

```bash
git clone <your-fork-or-origin-url> OnlyBirds
cd OnlyBirds
```

To just run things locally, `main` is fine. To contribute, branch off
`dev/current` — see [Contributing](contributing.md#branch--pr-workflow).

## 2. Get an eBird API key

1. Sign in at <https://ebird.org> (free account).
2. Request a key at <https://ebird.org/api/keygen>.
3. Keep it handy for step 3 — it goes in `backend/.env` and **never** in client
   code or version control.

## 3. Back-end setup

=== "Windows (PowerShell)"

    ```powershell
    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env
    # open .env and set EBIRD_API_KEY=...
    python -m uvicorn main:app --reload
    ```

=== "macOS / Linux (bash)"

    ```bash
    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    # edit .env and set EBIRD_API_KEY=...
    uvicorn main:app --reload
    ```

Then check it's alive:

- Interactive API docs: <http://localhost:8000/docs>
- Health probe: <http://localhost:8000/health> → `{"status":"ok", ...,
  "ebird_key_configured": true}`
- Live iNaturalist call (no key needed):
  <http://localhost:8000/species/search?q=raven>
- Live eBird call (needs the key):
  `http://localhost:8000/sightings/nearby?lat=47.66&lng=-122.31&source=ebird`

!!! tip "Without an eBird key"
    The server still starts. `/sightings/nearby` just returns iNaturalist
    results only, and `ebird_key_configured` is `false`.

## 4. Run the tests

```bash
cd backend
python -m pytest        # or: pytest
```

The suite uses FastAPI's `TestClient` and never hits the network, so it passes
offline and without any API key.

## 5. Front-end

The landing page is plain HTML/CSS — open `frontend/home/index.html`, or serve
it:

```bash
cd frontend/home
python -m http.server 4173      # http://localhost:4173
```

Shared styles and the `.ob-*` component classes live in `frontend/src/styles/`;
the rules are in [Contributing](contributing.md#styling-standard). App logic
under `frontend/src/` (`Dao/`, `Services/`, `Presenters/`, `Components/`) follows
the [layering rules](contributing.md#frontend-layering); the screens themselves
are still to come.

## Environment variables

Set in `backend/.env` (copied from `backend/.env.example`):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `EBIRD_API_KEY` | for eBird data | _unset_ | eBird API 2.0 token; sent server-side as `X-eBirdApiToken` |
| `CORS_ORIGINS` | no | `http://localhost:3000,http://localhost:5173,http://localhost:8081` | comma-separated allowed web origins |
| `DATABASE_URL` | for migrations | _unset_ | Postgres connection string (Supabase). Used by `scripts/migrate.sh`; the base server still runs without it. See [Deployment](deployment.md). |

`.env` is git-ignored. Never commit real keys.

## Editor setup (optional)

- **VS Code**: Python + Pylance extensions. Select the `backend/.venv`
  interpreter so imports like `app.main` resolve.
- Run/debug config: module `uvicorn`, args `main:app --reload`, working
  directory `backend/`.

## Troubleshooting

??? warning "`WARNING: The script uvicorn.exe is installed in '...' which is not on PATH`"
    Harmless. Invoke tools through Python instead:
    `python -m uvicorn main:app --reload`, `python -m pytest`.

??? warning "`ModuleNotFoundError: No module named 'app'`"
    Run from inside `backend/`. `main:app` (the shim) and `app.main:app` both
    work from that directory.

??? warning "eBird requests return 403 / empty"
    `EBIRD_API_KEY` is missing or invalid in `backend/.env`. Restart uvicorn
    after editing `.env`. iNaturalist endpoints are unaffected (no key).

??? warning "`[Errno 48] Address already in use` / port 8000 taken"
    `python -m uvicorn main:app --reload --port 8001`.

??? warning "PowerShell: `running scripts is disabled on this system`"
    Allow venv activation for your user:
    `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
