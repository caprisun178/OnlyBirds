-- 0006_species_content.sql
--
-- Cached "About" text for a species — see docs/features/bird-info.md. No
-- media here: photos/audio already have their own caches (bird_photos.py's
-- species_photo_cache.json / bird_audio.py's in-memory one) — duplicating
-- those into this table would just be a second cache to keep in sync for no
-- benefit.

create table if not exists species_content (
    scientific_name  text primary key,   -- matches this app's established identity key for a species
                                          -- (see pinned-birds.md's note on why scientific_name, not an
                                          -- eBird-only code, is the one field every source reliably has)
    about            text,                -- Wikipedia summary extract; null is fine — callers fall back to taxonomy only
    about_source_url text,                -- the Wikipedia page, for the required outbound attribution link
    fetched_at       timestamptz not null default now()
);
