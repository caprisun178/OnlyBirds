# Deployment

How Only Birds is hosted, and how to stand up your own copy. The stack is chosen
to be **managed** — no servers to patch, no Docker to learn.

| Concern | Service | Notes |
|---|---|---|
| Postgres + PostGIS | **Supabase** | also provides Auth and file Storage in the same project |
| Auth | Supabase Auth | wired up with the [User profiles](features/user-profiles.md) feature |
| Photo / avatar files | Supabase Storage | wired up with [Add Observation](features/add-observation.md) |
| Backend API (FastAPI) | **Render** web service | auto-deploys from `main`; see `render.yaml` |
| Web frontend | static host (Vercel / Netlify / GitHub Pages) | the landing page (`frontend/home/`) is plain HTML/CSS and can deploy now; app screens later |
| Mobile | Expo EAS | *not yet* |

!!! note "Render tracks `main` only"
    Feature work merges to `dev/current` first; a **release PR `dev/current` →
    `main`** is what ships. See
    [Contributing → Branch & PR workflow](contributing.md#branch-pr-workflow).

!!! danger "Secrets"
    The database password, `EBIRD_API_KEY`, and the Supabase service key live in
    exactly two places: your local `backend/.env` (git-ignored) and the hosting
    dashboard's environment settings. Never put them in a commit, an issue, a PR,
    or a chat message. `render.yaml` and `.env.example` only carry variable
    *names* and non-secret defaults.

## 1. Database — Supabase

1. <https://supabase.com> → **New project**. Choose the region closest to your
   users. Set a strong database password and store it in a password manager.
2. **Database → Extensions** → enable `postgis` and `pg_trgm`.
   (Migration `0001_baseline.sql` also does this, so this step is belt-and-braces.)
3. **Project Settings → Database → Connection string → URI**. This is your
   `DATABASE_URL`:

    ```text
    postgresql://postgres:[YOUR-PASSWORD]@db.<project-ref>.supabase.co:5432/postgres
    ```

    Use the **direct connection** (port 5432) for the Render service — it is a
    long-running process, not serverless. Put the real string in `backend/.env`
    locally; put it in Render in step 3.

## 2. Create the tables — migrations

Migrations are plain numbered `.sql` files in `backend/migrations/`. See
[Database & migrations](features/database.md) for how to write them; each
feature page has the SQL for its own tables.

**Run them** with the helper script (needs the `psql` client installed):

=== "macOS / Linux"

    ```bash
    export DATABASE_URL="postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
    ./backend/scripts/migrate.sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:DATABASE_URL = "postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
    bash backend/scripts/migrate.sh    # via Git Bash / WSL
    ```

The script tracks what it has applied in a `schema_migrations` table, so it is
safe to run again after you add a new file.

**No `psql`?** Open Supabase → **SQL Editor**, paste the contents of each
`backend/migrations/*.sql` file in number order, and run them one at a time.

## 3. Backend — Render

1. <https://render.com> → **New → Blueprint** → connect this repo. Render reads
   `render.yaml` and creates the `onlybirds-api` web service.
2. Open the service → **Environment** and fill the values marked `sync: false`:

    | Variable | Value |
    |---|---|
    | `EBIRD_API_KEY` | your eBird key |
    | `DATABASE_URL` | the Supabase URI from step 1 |
    | `CORS_ORIGINS` | leave the default until the web app exists, then add its URL |

3. Deploy. Render gives you `https://onlybirds-api.onrender.com` (name may vary).
   Check:
    - `GET /health` → `{"status":"ok", "ebird_key_configured": true}`
    - `GET /docs` → the interactive API

!!! note "Free tier cold starts"
    The free web service sleeps after 15 minutes idle; the next request takes
    ~30 s to wake it. Fine while building. Upgrade the plan (or add a keep-warm
    ping) before a demo.

## 4. Auth and Storage

Do these when you start the features that need them:

- **Auth** ([User profiles](features/user-profiles.md)) — Supabase →
  **Authentication** → enable the Email provider. The backend will verify tokens
  with `SUPABASE_JWT_SECRET` (Project Settings → API). Until then the server
  trusts `auth_provider_id` as passed.
- **Storage** ([Add Observation](features/add-observation.md)) — Supabase →
  **Storage** → create buckets `photos` and `avatars`. The backend issues signed
  upload URLs using `SUPABASE_SERVICE_ROLE_KEY` (secret).

## 5. Frontend

- **Landing page** — `frontend/home/` is static HTML/CSS. Point a static host
  (Vercel / Netlify / GitHub Pages) at that folder; no build step. Deploy from
  `main`.
- **App screens** — plain JS/HTML (`frontend/src/`), no build step, built on
  the shared design system (`frontend/styles/base.css`). Point the same kind
  of static host at `frontend/src/` once there's a screen worth deploying;
  hardcode the Render API URL in `Dao/apiClient.js` (no env-var injection
  without a build step), and wire up `SUPABASE_URL` + `SUPABASE_ANON_KEY` (the
  anon key is public) the same way once Auth lands.
- **Mobile** — Expo EAS Build, later, same API base URL.

Add each deployed web origin to `CORS_ORIGINS` on the Render service.

## Environment variables — full list

| Variable | Used by | Set where | Secret? |
|---|---|---|---|
| `EBIRD_API_KEY` | backend | `backend/.env`, Render | **yes** |
| `DATABASE_URL` | backend, `migrate.sh` | `backend/.env`, Render | **yes** |
| `CORS_ORIGINS` | backend | `backend/.env`, Render | no |
| `SUPABASE_URL` | backend, frontend | dashboards | no (public) |
| `SUPABASE_JWT_SECRET` | backend | Render | **yes** |
| `SUPABASE_SERVICE_ROLE_KEY` | backend | Render | **yes** |
| `SUPABASE_ANON_KEY` | frontend | Vercel | no (public) |
