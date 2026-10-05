# Contributing

New to the repo? [Set up & test your changes](setup-and-test.md) is the quick
version. This page is the full reference. If a term is unfamiliar, look for a
box like this one:

??? info "What's a box like this for?"
    This page assumes you might be new to some of these tools — Git, Docker,
    databases. Whenever a term shows up for the first time, there's a
    collapsible box like this one explaining it in plain terms. Already know
    it? Skip right past.

## Branch & PR workflow

??? info "What's a \"branch\", and what's a \"PR\"?"
    Git (the version-control tool this project uses) lets many people work on
    the same code at once without overwriting each other. A **branch** is your
    own private copy of the codebase where you can make changes safely — other
    people don't see them until you're ready. A **pull request** (PR) is how
    you ask for your branch's changes to be reviewed and merged into
    everyone else's code. Nothing you do on your own branch can break anything
    for anyone else until a PR merges it in.

There are three tiers of branch. You never commit to `main` or `dev/current`
directly — every change lands through a reviewed, CI-green pull request (CI —
short for **Continuous Integration** — is the automated checks, like running
the tests, that happen every time you push).

| Branch | What it is |
|---|---|
| `main` | **The live app.** What's actually running for real users. "Protected" means GitHub won't let anyone push to it directly — changes only arrive as a reviewed release PR from `dev/current`. |
| `dev/current` | **The shared work-in-progress branch.** Also protected. Every feature branch merges here first, so this is where everyone's changes meet and get tested together before they ever reach `main`. |
| `working/<you>/<feature>` | **Your branch.** Where you actually make changes. Branch it off `dev/current`, build one feature on it, then open a PR to merge it back into `dev/current`. |

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

??? info "What do these git commands do?"
    - `git checkout dev/current` — switch your local folder to look like the
      `dev/current` branch.
    - `git pull` — download the latest changes for the branch you're on.
    - `git checkout -b <name>` — create a brand-new branch with that name, and
      switch to it, in one step.
    - `git push -u origin <name>` — upload your new branch to GitHub for the
      first time (`-u` remembers the link, so a plain `git push` works after
      this).

Keep branches small — one [feature page](features/overview.md) per branch. Claim
the feature in the table on that overview page (its own quick PR into
`dev/current`) so two people don't build the same thing.

### Test it on your branch

1. **Get your own database — never the shared one.** If your change touches
   the database (see [Database & migrations](features/database.md)), you need
   somewhere to run it. Never point your branch at the shared or production
   Supabase — if your half-finished change breaks it, it breaks everyone's
   work. Pick whichever of these is easiest for you; you only need one:

    === "Docker (fully local)"

        ```bash
        docker run --name onlybirds-db -d -p 5432:5432 \
          -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=onlybirds \
          postgis/postgis:16-3.4
        # backend/.env
        DATABASE_URL=postgresql://postgres:postgres@localhost:5432/onlybirds
        ```

    === "Supabase or Neon (no install, free)"

        Make a free personal project at
        [supabase.com](https://supabase.com) or [neon.tech](https://neon.tech),
        then copy the connection string it gives you into
        `backend/.env` as `DATABASE_URL`.

    ??? info "What's Docker? "
        **Docker** is a tool that runs a small,
        disposable, pre-packaged copy of a program (here, Postgres, the
        database software this project uses) on your machine, without you
        having to install and configure that program yourself. You don't need
        to learn Docker beyond this one command — if that still sounds like a
        hassle, use the Supabase/Neon tab instead; it needs no local install
        at all.

    Either way, load the database's structure into it — this project doesn't
    use an ORM, so a **migration** is just a plain `.sql` file that describes
    one change to the database's structure (e.g. "add this table"). Run every
    migration that exists so far with:

    ```bash
    ./backend/scripts/migrate.sh
    ```

2. **Run the backend and click through the feature.**

    ```bash
    python -m uvicorn main:app --reload
    ```

    Then open <http://localhost:8000/docs> in a browser — this is an
    auto-generated page (from the FastAPI framework) that lets you call every
    API endpoint by hand and see the response, without writing any code.

3. **Run the automated tests.**

    ```bash
    cd backend
    python -m pytest
    ```

    Add a test for anything you changed. "Offline" means the tests must pass
    with no internet connection and no API key — they use canned, fake
    responses instead of calling eBird or iNaturalist for real.

4. **Open a draft PR into `dev/current` early.** A **draft PR** is a pull
   request marked "not ready for review yet" — GitHub still runs every check
   on it, so you get early warning if something's broken, without asking
   anyone to look at it yet. CI (the automated checks, defined in
   `.github/workflows/ci.yml`) runs the tests and a strict docs build on every
   push — a red ❌ means something failed; fix it before asking for review.

5. Fill in the PR checklist (it appears automatically in the PR description).
   Once CI is green ✅, a reviewer has approved your PR, and you've personally
   clicked through the feature to confirm it works, mark the PR **Ready for
   review** and **squash-merge** it into `dev/current`. "Squash-merge" means
   all of your branch's commits get combined into a single, clean commit on
   `dev/current` — so `dev/current`'s history stays readable even if your own
   branch had a messy "fix typo" / "fix typo again" history.

### Releasing to `main`


When `dev/current` holds a batch of features that are tested and stable, someone
opens a **release PR: `dev/current` → `main`**. It needs green CI and approval
from a **Code Owner** (a person GitHub is configured to always require a
review from, for changes to `main` — see `.github/CODEOWNERS`). This one uses
a **merge commit, not squash** — unlike step 5 above, every individual commit
is kept, so `dev/current` can **fast-forward** afterwards (catch up to `main`
by simply moving its pointer forward, since `main` now contains everything
`dev/current` had, with nothing rewritten). Merging it:

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

Migration files are numbered in the order they should run (`0001_...`,
`0002_...`), so two branches can accidentally both add a `0002_*.sql` — a
clash. Before merging, pull `dev/current`; if your number is already taken,
rename your file to the next free number and re-run `migrate.sh` against your
own dev database (never edit a migration that's already on `dev/current` —
add a new one instead, even to fix a mistake in an earlier one).

### Branch protection (repo admin, one-time)

!!! note "Only for whoever administers this repo"
    You won't touch this as a regular contributor — it's a one-time GitHub
    configuration step. Skip ahead to [Backend conventions](#backend-conventions).

GitHub → **Settings → Branches**. Add a rule for **both** `main` and
`dev/current`:

- Require a pull request before merging
- Require status checks to pass — **`backend tests`** and **`docs build (strict)`**
- Require branches to be up to date before merging
- Block force pushes and deletions

On **`main`** only, also require **1 approval** and **Require review from Code
Owners** — that's the production gate.

## Backend conventions

- **Folder = layer.** `app/dao/` (DAO — Data Access Object; the only code
  allowed to talk to the database or an external API) is raw data access only;
  `app/services/` is business logic; `app/routers/` is the HTTP surface.
  `dao/` must never import from `services/`.
- Keep external-API quirks inside `app/dao/` and `app/services/adapters.py`.
  Everything else deals in `app/models/` types.
- New persistence goes behind the `ObservationRepo` protocol (Python's version
  of an interface — a contract describing what methods a class must have,
  without saying how) in `app/dao/observation_repo.py`, not inline in a
  service.
- Add a test under `backend/tests/` for every endpoint or adapter change. Tests
  must stay offline — use canned payloads, not live calls.

### `dao/` file header

Every file under `app/dao/` starts with this header instead of a plain
docstring — a description plus a running changeLog, so a file's history is
visible without leaving the editor. When you create a new `dao/` file, add
one; when you meaningfully change an existing one, append a new changeLog
line (don't edit or remove earlier ones).

```python
"""
==============================
<Name> script library
Description:
<what this file does, and anything a reader needs to know before touching it>

=============================
changeLog
=============================
MM/DD/YYYY ... <your initials> ... <what changed>
=============================
"""
```

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
- Class names: `ob-` prefix, BEM-style (a naming convention — **B**lock,
  **E**lement, **M**odifier — that avoids CSS clashes without needing a build
  tool) — block `.ob-card`, element `.ob-card__title`, variant
  `.ob-btn--primary`.
- Don't restyle an `.ob-*` class for a one-off; add a variant to `base.css`.
- A page's `styles.css` is for that page's layout only; it must not redefine
  `.ob-*` classes.

Full catalogue, folder structure, and a worked example:
[`frontend/styles/README.md`](https://github.com/caprisun178/OnlyBirds/blob/main/frontend/styles/README.md).

## Documentation

This site (the one you're reading) is built from the Markdown files in
`docs/` by a tool called MkDocs, using the "Material" theme.

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
