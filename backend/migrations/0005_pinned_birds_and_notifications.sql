-- 0005_pinned_birds_and_notifications.sql
-- See docs/features/pinned-birds.md. Apply with backend/scripts/migrate.sh.
-- (The feature page's own SQL sample names this 0006 — written before
-- 0004_observation_region.sql existed; this is the real next number.)

-- the want-to-see list
create table if not exists pinned_birds (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references users(id) on delete cascade,
    species_id       uuid references species(id),
    -- The match/unique key. The feature page's draft used eBird speciesCode,
    -- but confirmed in app/services/adapters.py: an eBird-sourced
    -- observation's species carries source_ids={"ebird": ...} only, an
    -- iNaturalist-sourced one carries source_ids={"inat": ...} only, and
    -- neither is guaranteed on a manually-logged sighting. scientific_name
    -- is the one field every source (including manual entries, which
    -- always resolve one through the identification flow) reliably sets —
    -- matching on an eBird-only code would silently miss every manual and
    -- iNaturalist sighting, which is most of what this app actually logs.
    scientific_name  text not null,
    common_name      text,                        -- denormalized for display without a join
    region           text not null,                -- eBird regionCode scope; 'world' allowed
    created_at       timestamptz not null default now(),
    unique (user_id, scientific_name)
);
create index if not exists pinned_birds_species_idx on pinned_birds (scientific_name);

-- the notification feed (shared with Stickers)
create table if not exists notifications (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users(id) on delete cascade,
    kind        text not null check (kind in ('pin_hit', 'sticker_awarded')),
    payload     jsonb not null default '{}',    -- pin_hit: {species, region, observation_id, count}
    dedupe_key  text unique,                    -- e.g. 'pin_hit:<user>:<species>:<region>:2026-09-09'
    read_at     timestamptz,                    -- null until the user opens the feed
    created_at  timestamptz not null default now()
);
create index if not exists notifications_unread_idx on notifications (user_id, created_at desc)
    where read_at is null;
