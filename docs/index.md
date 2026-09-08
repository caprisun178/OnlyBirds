# Environment Setup

Everything a new contributor needs to get **Only Birds** running locally. If you
only touch the API, you can stop after [Run the tests](#4-run-the-tests).

## Repository layout

```text
OnlyBirds/
├── backend/        FastAPI service (Python) — the API the apps talk to
│   ├── app/        dao / services / models / routers
│   └── tests/      pytest, no network
├── frontend/       React (web) + React Native (mobile) — layered stubs, no build tooling yet
├── docs/           this MkDocs site
└── mkdocs.yml
```

The backend is the only part that runs today. The frontend currently holds the
DAO / service / presenter skeleton described in
[Contributing](contributing.md#frontend-layering); wiring is still to come.

## Prerequisites

| Tool | Version | Needed for | Notes |
|---|---|---|---|
| Git | any recent | cloning | |
| Python | 3.13+ (3.13.14 known good) | backend | `python --version` |
| eBird API key | — | live bird sightings | free, see step 2. iNaturalist needs no key. |
| Node.js | 20+ | frontend | not required yet — no `package.json` in `frontend/` |
| PostgreSQL + PostGIS | 16 | persistence | **optional**, only once roadmap step 3 lands; the base server uses an in-memory store |

!!! note "Windows"
    Commands are shown for both PowerShell and bash. On Windows, prefer
    `python -m <tool>` (e.g. `python -m uvicorn`) so you don't depend on the
    Scripts directory being on `PATH` — see [Troubleshooting](#troubleshooting).

## 1. Clone

```bash
git clone <your-fork-or-origin-url> OnlyBirds
cd OnlyBirds
```

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

## 5. Front-end setup

Not runnable yet. `frontend/src/` contains the layered skeleton
(`Dao/`, `Services/`, `Presenters/`, `Components/`, `Models/`, `Pages/`) and the
rules in [Contributing](contributing.md#frontend-layering). Once build tooling is
added the flow will be the usual `npm install` / `npm run dev` (web) and Expo
for React Native — this page will be updated then.

## Environment variables

Set in `backend/.env` (copied from `backend/.env.example`):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `EBIRD_API_KEY` | for eBird data | _unset_ | eBird API 2.0 token; sent server-side as `X-eBirdApiToken` |
| `CORS_ORIGINS` | no | `http://localhost:3000,http://localhost:5173,http://localhost:8081` | comma-separated allowed browser / Metro origins |
| `DATABASE_URL` | no (roadmap step 3) | _unset_ | Postgres connection string; unused by the in-memory base server |

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
