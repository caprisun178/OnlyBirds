-- 0009_user_stickers.sql
-- Earned stickers, so they survive restarts and redeploys. See
-- docs/features/stickers.md. Apply with backend/scripts/migrate.sh.
--
-- Only the award ledger becomes a table. The catalog (stickers.json,
-- groups.json in backend/app/data/) stays a checked-in fixture: it's our own
-- data and changes with the code, so `sticker_code` is plain text, not a
-- foreign key to a `stickers` table.

create table if not exists user_stickers (
    user_id        uuid not null references users(id) on delete cascade,
    sticker_code   text not null,                -- a `code` from app/data/stickers.json
    awarded_at     timestamptz not null default now(),
    observation_id uuid references observations(id) on delete set null,  -- the sighting that earned it
    primary key (user_id, sticker_code)          -- makes re-awarding a no-op
);
