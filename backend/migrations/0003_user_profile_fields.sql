-- 0003_user_profile_fields.sql

-- Adds profile fields to p users. See docs/features/user-profiles.md.
-- Used "if not exists" as a safety net in case of overlap
-- with another in-flight branch .

alter table users add column if not exists username       text unique;
alter table users add column if not exists avatar_url     text;
alter table users add column if not exists default_region text not null default 'world';  -- eBird regionCode

