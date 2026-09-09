-- 0001_baseline.sql
-- Roadmap step 3: the schema every feature builds on.
-- See docs/features/database.md. Apply with backend/scripts/migrate.sh.

create extension if not exists postgis;      -- location columns + distance queries
create extension if not exists pg_trgm;      -- fuzzy species-name search (Bird information page)

create table if not exists users (
    id                uuid primary key default gen_random_uuid(),
    auth_provider_id  text not null unique,  -- subject id from Auth0 / Supabase Auth
    email             text,
    created_at        timestamptz not null default now()
);

create table if not exists species (
    id               uuid primary key default gen_random_uuid(),
    scientific_name  text not null,
    common_name      text,
    taxon_group      text,                   -- e.g. "owls", "waterfowl"
    ebird_code       text unique,            -- eBird speciesCode
    inat_taxon_id    text unique,            -- iNaturalist taxon id
    created_at       timestamptz not null default now()
);

create table if not exists observations (
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
create index if not exists observations_user_idx
    on observations (user_id, observed_at desc);

create table if not exists life_list_entries (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references users(id) on delete cascade,
    species_id         uuid not null references species(id),
    first_observed_at  timestamptz not null,
    observation_id     uuid references observations(id),
    unique (user_id, species_id)            -- one row per species per user
);
