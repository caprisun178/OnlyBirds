-- 0002_life_list_region_checklists.sql
-- Life List: cache table for a region's full species checklist.
-- See docs/features/life-list.md. Apply with backend/scripts/migrate.sh.

create table if not exists region_checklists (
    region_code    text primary key,        -- eBird regionCode, e.g. 'US-WA' or 'world'
    species_codes  text[] not null,          -- eBird speciesCodes in the region, taxonomic order
    fetched_at     timestamptz not null default now()
);
