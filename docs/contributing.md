# Contributing

## Branch & PR workflow

`main` is protected. It always builds, always passes tests, and is what Render
deploys. You never commit to it directly — every change lands through a
reviewed, tested pull request.

### One feature at a time

```bash
git checkout main && git pull                 # start from the latest main
git checkout -b working/<you>/<feature>       # e.g. working/sam/pinned-birds
# ...build it...
git push -u origin working/<you>/<feature>
```

Keep branches small — one [feature page](features/overview.md) per branch. Claim
the feature in the table on that overview page so two people don't build the
same thing.

### Test it on your branch, not on main

1. **Your own database.** Never point your branch at the shared/production
   Supabase. Run a local one:

    ```bash
    docker run --name onlybirds-db -d -p 5432:5432 \
      -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=onlybirds \
      postgis/postgis:16-3.4
    # backend/.env
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/onlybirds
    ```

    …or make a second **free personal Supabase project**. Apply migrations with
    `./backend/scripts/migrate.sh`.

2. **Run the backend and click through the feature**
   (`python -m uvicorn main:app --reload`, then `/docs`).

3. **Run the tests**: `cd backend && python -m pytest`. Add tests for anything
   you changed; they must pass offline.

4. **Open a draft PR early.** GitHub Actions (`.github/workflows/ci.yml`) runs
   the tests and a strict docs build on every push. Fix red before asking for
   review.

5. Fill in the PR checklist (it appears automatically). When CI is green, a Code
   Owner has approved, and you have manually verified the feature, mark the PR
   **Ready** and merge (squash).

### After merge — updating production

Merging to `main` triggers a Render deploy of the new code. If your PR added a
migration, apply it to the production database **once**, right after the deploy:

```bash
DATABASE_URL="<production URI>" ./backend/scripts/migrate.sh
```

Then smoke-test the live URL (`/health` and your feature). See
[Deployment](deployment.md).

### Migration number clashes

Two branches can both add `0002_*.sql`. Before merging, pull `main` and, if your
number is taken, rename your file to the next free number and re-run
`migrate.sh` against your dev database. Never edit a migration that is already
on `main`.

### Enable the protection (repo admin, one-time)

GitHub → **Settings → Branches → Add branch ruleset** (or *Add rule*) for `main`:

- Require a pull request before merging — **1 approval**, **Require review from
  Code Owners**
- Require status checks to pass — select **`backend tests`** and
  **`docs build (strict)`**
- Require branches to be up to date before merging
- Block force pushes and deletions
- Apply to administrators too

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

JavaScript logic under `frontend/src/` uses the same layer split as the
backend. Markup and styling follow the [Styling standard](#styling-standard)
below.

```text
frontend/src/
  Dao/          raw API access only, no logic (talks to our FastAPI backend)
  Services/     business logic; transforms DAO output into UI-ready shape
  Presenters/   wire a screen together — state, handlers, render the markup
  Components/   reusable markup blocks — no state, no DAO/Service imports
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

## Styling standard

There is one shared stylesheet: `frontend/styles/base.css` — plain CSS, no
build step. It defines the design tokens (`--ob-*` variables) and the shared
`.ob-*` classes (buttons, cards, tags, form fields, alerts, layout helpers).
Every HTML page links it before its own `styles.css`:

```html
<link rel="stylesheet" href="../styles/base.css" />
<link rel="stylesheet" href="styles.css" />
```

- Write markup with `.ob-*` classes; a reusable block gets at most one layout
  class of its own (`.ob-species-card`) in a small CSS file beside it.
- In any CSS, use tokens — `var(--ob-space-4)`, `var(--ob-color-brand)` — never
  raw `px` or hex. Need a new value? Add a token to `base.css`.
- Class names: `ob-` prefix, BEM-style — block `.ob-card`, element
  `.ob-card__title`, variant `.ob-btn--primary`.
- Don't restyle an `.ob-*` class for a one-off; add a variant to `base.css`.
- A page's `styles.css` is for that page's layout only; it must not redefine
  `.ob-*` classes.

Full catalogue, folder structure, and a worked example:
[`frontend/styles/README.md`](https://github.com/caprisun178/OnlyBirds/blob/main/frontend/styles/README.md).

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
