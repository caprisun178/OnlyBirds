# Database & migrations

Every feature page has a **Database changes (SQL)** section. This page explains
how to apply that SQL, the conventions all of it follows, and the baseline
schema those changes build on.

If you have never run a database migration before, read
[How to apply a migration](#how-to-apply-a-migration) first — it is three
commands.

## Where our data lives

Only Birds has **three** places data can sit. Every feature page's
"Where the data comes from and where it goes" table points at one of them:

| Store | What goes here | Example |
|---|---|---|
| **Our Postgres database** | Anything a user creates or owns, and anything we must keep even if an external API disappears. | a logged observation, a life-list entry, a pinned bird |
| **A cache table** (also in Postgres) | Copies of external data we fetch a lot and that changes slowly. Safe to delete and re-fetch. Every cache table has a `fetched_at` column. | a region's species checklist, a species' photos |
| **An external API, live** | Data we read on demand and never store. | the list of eBird regions in the region picker |

Rule of thumb: **if the user typed it or earned it, it goes in a real table. If
eBird or iNaturalist owns it, it goes in a cache table or stays remote.**

## The external APIs

| API | Needs a key? | What we use it for | Docs |
|---|---|---|---|
| eBird API 2.0 | Yes — `EBIRD_API_KEY` in `backend/.env` | regions, region checklists, taxonomy, recent + notable sightings | <https://documenter.getpostman.com/view/664302/S1ENwy59> |
| iNaturalist API v1 | No | taxon search, recent sightings in a bounding box | <https://api.inaturalist.org/v1/docs/> |
| Macaulay Library (Cornell) | Yes (Cornell account) | species photos and audio | via eBird / Cornell |
| eBird Status & Trends | product download | migration and abundance maps | <https://science.ebird.org/en/status-and-trends> |

All external calls happen in `backend/app/dao/` **only**. Never call eBird or
iNaturalist from a router, a service, or the frontend.

## Conventions

All SQL on the feature pages follows these, so copy the style when you add more:

- **snake_case** names. Tables are plural (`observations`); a table that links
  two things names both (`user_stickers`).
- **Primary keys** are `uuid primary key default gen_random_uuid()` — except
  cache tables keyed by an external code (e.g. `region_checklists.region_code`).
- **Timestamps** are `timestamptz` (never bare `timestamp`), default `now()`.
- **Scores / confidence** use `numeric`, not `float`.
- **Foreign keys** always say what happens on delete — usually
  `on delete cascade` for rows owned by a user.
- **Enums** are `text` + a `check (col in (...))` constraint, not Postgres
  `enum` types (easier to extend later).
- **Locations** we query by distance or bounding box use PostGIS
  `geography(point, 4326)`, kept alongside plain `lat` / `lng` for display.
- **Nested / variable data** (a list of candidates, a media list) is `jsonb`.

## How to apply a migration

We do not use an ORM or a migration framework yet. A migration is just a
numbered `.sql` file you run with `psql`.

1. **Create the file.** Paste the SQL from the feature page into a new file
   under `backend/migrations/`, named `NNNN_<feature>.sql`:

    ```text
    backend/migrations/0003_pinned_birds.sql
    ```

    Look in the folder for the highest number and add one.

2. **Run it** against your local database:

    === "macOS / Linux"

        ```bash
        psql "$DATABASE_URL" -f backend/migrations/0003_pinned_birds.sql
        ```

    === "Windows (PowerShell)"

        ```powershell
        psql $env:DATABASE_URL -f backend/migrations/0003_pinned_birds.sql
        ```

    `DATABASE_URL` lives in `backend/.env`, e.g.
    `postgresql://postgres:postgres@localhost:5432/onlybirds`.

3. **Commit the `.sql` file.** It is the permanent record of the change. Never
   edit a migration that is already merged — add a new one.

!!! tip "Rebuild from scratch"
    ```bash
    dropdb onlybirds && createdb onlybirds
    for f in backend/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
    ```

!!! note "When we outgrow this"
    Once the schema stabilises we will switch to Alembic (SQLAlchemy's migration
    tool). The `.sql` files convert directly into Alembic revisions, so nothing
    here is wasted.

## Baseline schema — `0001_baseline.sql`

Roadmap step 3. This formalises the "starting point" bullets in the root
`README.md` and is what every feature change builds on.

```sql
-- 0001_baseline.sql
create extension if not exists postgis;      -- location columns + distance queries

create table users (
    id                uuid primary key default gen_random_uuid(),
    auth_provider_id  text not null unique,  -- subject id from Auth0 / Supabase
    email             text,
    created_at        timestamptz not null default now()
);

create table species (
    id               uuid primary key default gen_random_uuid(),
    scientific_name  text not null,
    common_name      text,
    taxon_group      text,                   -- e.g. "owls", "waterfowl"
    ebird_code       text unique,            -- eBird speciesCode
    inat_taxon_id    text unique,            -- iNaturalist taxon id
    created_at       timestamptz not null default now()
);

create table observations (
    id                     uuid primary key default gen_random_uuid(),
    user_id                uuid not null references users(id) on delete cascade,
    species_id             uuid references species(id),
    lat                    double precision not null,
    lng                    double precision not null,
    observed_at            timestamptz not null,
    source                 text not null default 'manual'
                             check (source in ('manual', 'inat', 'ebird')),
    source_observation_id  text,             -- id in eBird / iNat, if imported
    photo_url              text,
    notes                  text,
    created_at             timestamptz not null default now()
);
create index observations_user_idx on observations (user_id, observed_at desc);

create table life_list_entries (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references users(id) on delete cascade,
    species_id         uuid not null references species(id),
    first_observed_at  timestamptz not null,
    observation_id     uuid references observations(id),
    unique (user_id, species_id)            -- one row per species per user
);
```

## Which feature changes which part of the schema

| Feature | New tables | Changed tables |
|---|---|---|
| [Life List page](life-list.md) | `region_checklists` | — |
| [Add Observation](add-observation.md) | `identifications` | `observations` (+ `region`, `geom`, `status`) |
| [User profiles](user-profiles.md) | — | `users` (+ `username`, `avatar_url`, `default_region`) |
| [Stickers](stickers.md) | `stickers`, `user_stickers`, `groups` | — |
| [Pinned birds](pinned-birds.md) | `pinned_birds`, `notifications` | — |
| [Bird information page](bird-info.md) | `species_content` | `species` (+ search index) |
| [Explore map](explore-map.md) | `sighting_cache` | needs `observations.geom` from Add Observation |
