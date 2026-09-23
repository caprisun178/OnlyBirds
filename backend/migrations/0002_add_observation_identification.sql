-- 0002_add_observation_identification.sql
-- Add Observation: describe & guess identification, plus richer field notes.
-- See docs/features/add-observation.md. Apply with backend/scripts/migrate.sh.

-- 1. richer observation record
alter table observations add column if not exists location_name   text;         -- free-text place name / reverse-geocoded label
alter table observations add column if not exists sex             text
    check (sex in ('male', 'female', 'unknown'));
alter table observations add column if not exists life_stage      text
    check (life_stage in ('adult', 'juvenile', 'fledgling', 'unknown'));
alter table observations add column if not exists detection_type  text
    check (detection_type in ('sight', 'sound'));
alter table observations add column if not exists status          text not null default 'logged'
    check (status in ('draft', 'identifying', 'confirmed', 'logged'));
alter table observations alter column lat drop not null;   -- optional until a map picker exists
alter table observations alter column lng drop not null;

