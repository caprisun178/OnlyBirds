# Contributing

## Backend conventions

- **Folder = layer.** `app/dao/` is raw data access only; `app/services/` is
  business logic; `app/routers/` is the HTTP surface. `dao/` must never import
  from `services/`.
- Keep external-API quirks inside `app/dao/` and `app/services/adapters.py`.
  Everything else deals in `app/models/` types.
- New persistence goes behind the `ObservationRepo` protocol in
  `app/dao/observation_repo.py`, not inline in a service.
- Add a test under `backend/tests/` for every endpoint or adapter change. Tests
  must stay offline — use canned payloads, not live calls.

Run before pushing:

```bash
cd backend
python -m pytest
```

## Frontend layering

From the root `README.md` — the same DAO / Services / Presenters split as the
backend:

```text
frontend/src/
  Dao/          raw API access only, no logic (talks to our FastAPI backend)
  Services/     business logic; transforms DAO output into UI-ready shape
  Presenters/   smart components — own state, handlers, render JSX
  Components/   pure, presentational only — no state, no DAO/Service imports
  Models/       shared data shapes
```

Rules:

- The folder path indicates the layer — no `DAO` / `Service` suffix in
  filenames (`Dao/observations.js`, `Services/observations.js`).
- Layer identity at the import site comes from **named exports**, not filenames:
  `export const observationDAO = {...}` / `export const observationService = {...}`.
- `Components/` must never import from `Services/` or `Dao/` — only
  `Presenters/` may. (An ESLint `import/no-restricted-paths` rule should enforce
  this once tooling is set up.)

## Documentation

This site is MkDocs + Material.

```bash
pip install -r docs/requirements.txt
mkdocs serve      # live preview at http://127.0.0.1:8000
mkdocs build      # render to ./site
```

Pages live in `docs/`; the nav is defined in `mkdocs.yml`. Keep
[Environment Setup](index.md) accurate whenever setup steps change.

## Roadmap

1. Scaffold FastAPI backend, hello-world endpoint *(done)*
2. One real call against each external API *(done — `/species/search`, `/sightings/nearby`)*
3. Postgres + PostGIS schema; back `/observations` and `/life-list` with it
4. Scaffold the React app against our own API
5. CV integration (stretch goal)
