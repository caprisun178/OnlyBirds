-- 0012_user_display_name.sql
-- A free-text name the user picks for their Profile ("Sarah P."), separate
-- from `username`: not unique, not part of any URL, and can change without
-- breaking /users/{username} links. Null = fall back to the username. Apply
-- with backend/scripts/migrate.sh.

alter table users add column if not exists display_name text;
