-- 0011_user_favorite_common_name.sql
-- The display name for users.favorite_species (0010), saved alongside it the
-- same way pinned_birds keeps common_name next to scientific_name, so the
-- Profile card can show "Black-capped Chickadee" without a lookup. Apply with
-- backend/scripts/migrate.sh.

alter table users add column if not exists favorite_common_name text;  -- null = none known
