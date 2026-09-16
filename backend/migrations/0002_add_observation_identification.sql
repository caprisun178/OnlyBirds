-- 0002_add_observation_identification.sql
-- Add Observation: describe & guess identification, plus richer field notes.
-- See docs/features/add-observation.md. Apply with backend/scripts/migrate.sh.

-- 1. richer observation record
alter table observations add column if not exists location_name text;         -- free-text place name (map picker is a later iteration)
alter table observations add column if not exists sex          text
    check (sex in ('male', 'female', 'unknown'));
alter table observations add column if not exists life_stage   text
    check (life_stage in ('adult', 'juvenile', 'fledgling', 'unknown'));
alter table observations add column if not exists status       text not null default 'logged'
    check (status in ('draft', 'identifying', 'confirmed', 'logged'));
alter table observations alter column lat drop not null;   -- optional until a map picker exists
alter table observations alter column lng drop not null;

-- 2. how the species was identified, and whether the guess was right
create table if not exists identifications (
    id                   uuid primary key default gen_random_uuid(),
    observation_id       uuid references observations(id) on delete cascade,
    method               text not null check (method in ('photo', 'describe')),
    input                jsonb not null default '{}',   -- {text, hints}
    candidates           jsonb not null default '[]',   -- [{species_code, common_name, confidence, photo_url}]
    target_species_code  text,                          -- known only when the text named a species outright
    chosen_species_code  text,                          -- the candidate the user picked
    outcome              text not null default 'unconfirmed'
                           check (outcome in ('correct', 'incorrect', 'unconfirmed')),
    created_at           timestamptz not null default now()
);
create index if not exists identifications_observation_idx on identifications (observation_id);
