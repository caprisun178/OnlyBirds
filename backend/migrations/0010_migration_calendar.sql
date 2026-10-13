-- 0010_migration_calendar.sql
-- Migration calendar (docs/features/migration-calendar.md §3): per-grid-cell
-- weekly bird observation counts from iNaturalist, so everyone in the same
-- ~55 km cell shares one cached calendar. Numbered after 0007–0009, which
-- are already applied from other branches (bug reports, bulk import).
-- Apply with backend/scripts/migrate.sh.

create table if not exists migration_calendars (
    cell_id      text primary key,                -- 'lat:lng' of the cell's SW corner, e.g. '35.5:-79.0'
    center_lat   double precision not null,
    center_lng   double precision not null,
    radius_km    int not null default 40,
    status       text not null default 'building'
        check (status in ('building', 'ready', 'failed')),
    total_obs    int,                             -- whole-year bird observations; drives the data-quality banners
    built_at     timestamptz,                     -- last successful build; null until the first one
    updated_at   timestamptz not null default now()
);

create table if not exists migration_calendar_weeks (
    cell_id      text not null references migration_calendars (cell_id) on delete cascade,
    week         smallint not null check (week between 1 and 53),
    total_obs    int not null,                    -- all bird observations that week: the share denominator
    primary key (cell_id, week)
);

create table if not exists migration_calendar_counts (
    cell_id          text not null references migration_calendars (cell_id) on delete cascade,
    scientific_name  text not null,               -- the app's species identity (same as bird-info / pins)
    common_name      text,
    inat_taxon_id    int,
    week             smallint not null check (week between 1 and 53),
    obs_count        int not null,
    primary key (cell_id, scientific_name, week)
);
