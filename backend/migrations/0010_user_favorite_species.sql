-- 0010_user_favorite_species.sql
-- One favorite bird per user, shown on the user Profile screen. Stored as the
-- species' scientific_name, the same identity key pins and the Bird Info
-- page use, so it is not a foreign key to `species` (a bird may never have
-- been logged, so it may have no row there). Apply with
-- backend/scripts/migrate.sh.

alter table users add column if not exists favorite_species text;  -- null = no favorite chosen
