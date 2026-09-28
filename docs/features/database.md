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
| eBird API 2.0 | Yes | regions, region checklists, taxonomy, recent + notable sightings | [eBird API](../ebird-api.md) |
| iNaturalist API v1 | No | taxon search, recent sightings in a bounding box | <https://api.inaturalist.org/v1/docs/> |
| Macaulay Library (Cornell) | Yes (Cornell account) | species photos and audio | via eBird / Cornell |
| eBird Status & Trends | product download | migration and abundance maps | <https://science.ebird.org/en/status-and-trends> |

All external calls happen in `backend/app/dao/` **only** — see
[Contributing → Backend conventions](../contributing.md#backend-conventions).

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

2. **Run every pending migration** with the helper script:

    ```bash
    export DATABASE_URL="postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
    ./backend/scripts/migrate.sh
    ```

    `DATABASE_URL` also lives in `backend/.env`. The script applies each
    `backend/migrations/*.sql` file in order and records it in a
    `schema_migrations` table, so re-running it only applies what's new. It needs
    the `psql` client installed; on Windows run it through Git Bash or WSL.

    No `psql`? Paste each file into the Supabase **SQL Editor** in number order.

3. **Commit the `.sql` file.** It is the permanent record of the change. Never
   edit a migration that is already merged — add a new one.

!!! tip "Rebuild from scratch"
    Drop and recreate the database (or, on Supabase, use a fresh project), then
    run `./backend/scripts/migrate.sh` again.

!!! note "When we outgrow this"
    Once the schema stabilises we will switch to Alembic (SQLAlchemy's migration
    tool). The `.sql` files convert directly into Alembic revisions, so nothing
    here is wasted.

## Baseline schema — `0001_baseline.sql`

The schema every feature builds on — it matches the core data model in the root
`README.md`. Committed as `backend/migrations/0001_baseline.sql`.

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
```



## Which feature changes which part of the schema

| Feature | New tables | Changed tables |
|---|---|---|
| [Life List page](life-list.md) | `region_checklists` | — |
| [Add Observation](add-observation.md) | — | `observations` (+ `location_name`, `sex`, `life_stage`, `status`; `region`/`geom` still to come) |
| [User profiles](user-profiles.md) | — | `users` (+ `username`, `avatar_url`, `default_region`) |
| [Stickers](stickers.md) | `stickers`, `user_stickers`, `groups` | — |
| [Pinned birds](pinned-birds.md) | `pinned_birds`, `notifications` | — |
| [Bird information page](bird-info.md) | `species_content` | `species` (+ search index) |
| [Explore map](explore-map.md) | `sighting_cache` | needs `observations.geom` from Add Observation |
