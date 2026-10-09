-- 0006_species_content.sql
-- See docs/features/bird-info.md. Apply with backend/scripts/migrate.sh.

create extension if not exists pg_trgm;   -- fuzzy text search for the species search box

-- fast "search as you type" over species names
create index if not exists species_common_name_trgm on species using gin (common_name gin_trgm_ops);
create index if not exists species_sci_name_trgm    on species using gin (scientific_name gin_trgm_ops);

-- cached Wikipedia-sourced text, one row per species. No media here —
-- photos/audio already have their own caches (bird_photos.py / bird_audio.py);
-- duplicating that into this table would just be a second cache to keep in
-- sync for no benefit.
create table if not exists species_content (
    scientific_name  text primary key,   -- matches this app's established identity key for a species
                                          -- (see pinned-birds.md's note on why scientific_name, not an
                                          -- eBird-only code, is the one field every source reliably has)
    about            text,                -- Wikipedia summary extract; null is fine — UI falls back to taxonomy only
    about_source_url text,                -- the Wikipedia page, for the required outbound attribution link
    sex_differences  text,                -- "Description" section text; null means the article didn't say (not an error)
    migration        text,                -- "Distribution and habitat"/"Migration" section text; null is equally fine
    habitat          text,                -- often the same source section as migration — stored separately since the
                                          -- UI shows them as distinct blocks
    fetched_at       timestamptz not null default now()
);
