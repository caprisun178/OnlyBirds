# Contributing

## Branch & PR workflow

New to the repo? [Set up & test your changes](setup-and-test.md) is the quick
version. This section is the full reference — branch tiers, releases, protection.

There are three tiers of branch. You never commit to `main` or `dev/current`
directly — every change lands through a reviewed, CI-green pull request.

| Branch | What it is |
|---|---|
| `main` | **Production.** Protected. Render deploys from it. The only thing that merges in is a release PR from `dev/current`. |
| `dev/current` | **Integration.** A mirror of `main` that all feature work flows through. Protected; CI runs on it. |
| `working/<you>/<feature>` | Your workspace. Branched **off `dev/current`**, one feature, merged back into `dev/current`. |

```text
working/<you>/<feature> ──PR──▶ dev/current ──release PR──▶ main ──▶ Render deploy
        ▲                                                              │
        └────────── branch from dev/current ◀── main merged back ──────┘
```

### Start a feature

```bash
git checkout dev/current && git pull          # start from the latest dev/current
git checkout -b working/<you>/<feature>       # e.g. working/sam/pinned-birds
# ...build it...
git push -u origin working/<you>/<feature>
```

Keep branches small — one [feature page](features/overview.md) per branch. Claim
the feature in the table on that overview page (its own quick PR into
`dev/current`) so two people don't build the same thing.

### Test it on your branch

1. **Your own database.** Never point your branch at the shared / production
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

4. **Open a draft PR into `dev/current` early.** CI
   (`.github/workflows/ci.yml`) runs the tests and a strict docs build on every
   push. Fix red before asking for review.

5. Fill in the PR checklist (it appears automatically). When CI is green, a
   reviewer has approved, and you have manually verified the feature, mark the
   PR **Ready** and **squash-merge into `dev/current`**.

### Releasing to `main`

When `dev/current` holds a batch of features that are tested and stable, someone
opens a **release PR: `dev/current` → `main`**. It needs green CI and a Code
Owner approval. Use a **merge commit, not squash**, so `dev/current` can
fast-forward afterwards. Merging it:

1. triggers the Render deploy of `main`;
2. if any migration is new, apply it to the **production** database once, right
   after the deploy:

    ```bash
    DATABASE_URL="<production URI>" ./backend/scripts/migrate.sh
    ```

3. smoke-test the live URL (`/health` and the new features) — see
   [Deployment](deployment.md).

Then bring `dev/current` back in line with `main` so they stay identical:

```bash
git checkout dev/current && git pull
git merge --ff-only origin/main
git push
```

### Migration number clashes

Two branches can both add `0002_*.sql`. Before merging, pull `dev/current`; if
your number is taken, rename your file to the next free number and re-run
`migrate.sh` against your dev database. Never edit a migration that is already on
`dev/current`.

### Branch protection (repo admin, one-time)

GitHub → **Settings → Branches**. Add a rule for **both** `main` and
`dev/current`:

- Require a pull request before merging
- Require status checks to pass — **`backend tests`** and **`docs build (strict)`**
- Require branches to be up to date before merging
- Block force pushes and deletions

On **`main`** only, also require **1 approval** and **Require review from Code
Owners** — that's the production gate.

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

JavaScript under `frontend/src/` uses the same layer split as the backend.
Markup and styling follow the [Styling standard](#styling-standard) below.

```text
frontend/
  styles/         the shared design system — base.css + its guide
  src/
    Dao/          raw API access only, no logic (talks to our FastAPI backend)
    Services/     business logic; transforms DAO output into UI-ready shape
    Presenters/   wire a screen together — call a service, render, handle events
    Components/   reusable markup blocks — no state, no DAO/Service imports
    Models/       shared data shapes
```

Rules:

- The folder path indicates the layer — no `DAO` / `Service` suffix in
  filenames (`Dao/observations.js`, `Services/observations.js`).
- Layer identity at the import site comes from **named exports**, not filenames:
  `export const observationDAO = {...}` / `export const observationService = {...}`.
- `Components/` must never import from `Services/` or `Dao/` — only
  `Presenters/` may.

**Building an actual screen** — a full walkthrough with which classes and
objects to use: [Building a screen](frontend-screens.md).

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

1. Scaffold FastAPI backend, hello-world endpoint — **done**
2. One real call against each external API — **done** (`/species/search`, `/sightings/nearby`)
3. Postgres + PostGIS: baseline migration + Supabase project — **done**; backing
   `/observations` and `/life-list` with it — **in progress**
4. Backend deployed on Render, CI + branch protection in place — **done**
5. Build the features in [`docs/features/`](features/overview.md), one PR each
6. Frontend: landing page — **done**; app screens on the shared design system — **next**
7. Computer-vision photo identification — stretch goal
