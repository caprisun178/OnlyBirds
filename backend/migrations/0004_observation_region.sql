-- 0004_observation_region.sql
-- Completes Add Observation's schema (docs/features/database.md flagged
-- "region/geom still to come") and is the prerequisite Pinned Birds
-- (docs/features/pinned-birds.md) needs to match a new sighting's location
-- against a user's watched region. Backfilled going forward only — existing
-- rows keep `region = null`; `app/services/observation.py#log_observation()`
-- computes it for every new insert via `ebird.region_for_point()`.

alter table observations add column if not exists region text;
create index if not exists observations_region_idx on observations (region);
