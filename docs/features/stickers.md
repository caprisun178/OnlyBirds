# Stickers

> **Status:** Planned. Build after [Add Observation](add-observation.md) — the
> engine runs when a new life-list entry is created, and some rules need
> `observations.region`.

## 1. What you're building

The reward layer. As users fill in their life list they earn **stickers** for
milestones — first bird, first owl, first eagle, all eagles, and so on. Stickers
live on the [profile](user-profiles.md) as a collectible shelf.

### Rule types

Every sticker is one rule type plus `criteria`:

| Rule type | Awards when… | Example | `criteria` |
|---|---|---|---|
| `first_ever` | the user's first life-list entry of any bird | **First Bird** | — |
| `first_in_group` | first life-list entry whose species is in a group | **First Owl** | `{group: "owls"}` |
| `group_complete` | the user has seen **every** species in a set | **All Eagles** | `{group: "eagles"}` |
| `count_milestone` | life list total reaches N | **Century (100)** | `{threshold: 100}` |
| `region_complete` | life list covers a region's full checklist | **Washington Sweep** | `{region: "US-WA"}` |
| `first_in_region` | first bird logged in a given region | **Hello, California** | `{region: "US-CA"}` |

### Groups and sets

- Some groups are clean taxonomic ranks — **owls** = order *Strigiformes* —
  resolved straight from the taxonomy (`kind = 'rank'`).
- Some are folk categories that span the taxonomy — **eagles** are spread across
  several genera. Those are an explicit curated **set of species codes**,
  versioned in the repo (`kind = 'set'`).
- `criteria.group` names a `groups` row; the engine loads that row to know which
  species count.

### The engine

- Runs **after every new `life_list_entries` row** (i.e. after a lifer, not
  every observation).
- Loads the user's life list + the stickers they have **not** yet earned,
  evaluates each rule, inserts `user_stickers` rows for any that now pass, and
  pushes one `sticker_awarded` notification per sticker (see
  [Pinned birds](pinned-birds.md#3-database-changes-sql) for the
  `notifications` table).
- **Idempotent**: the `(user_id, sticker_code)` primary key means re-running is
  safe. `count_milestone` and `group_complete` only ever go locked → earned.
- Exposed for tests/backfill as an internal `evaluate_stickers(user_id)` in
  `Services/stickers` — there is no public "grant" endpoint.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| The sticker catalog (name, art, rule, rarity) | a **fixture file in the repo**, seeded on deploy | `stickers` table |
| Group definitions (rank query or species-code set) | a **fixture file in the repo** | `groups` table |
| Which stickers a user has earned | our engine, after each lifer | `user_stickers` table |
| The user's life list (engine input) | our own data | `life_list_entries` (already exists) |
| Region checklist (for `region_complete`) | reuse the [Life List](life-list.md) cache | `region_checklists` |
| Sticker art images | designed assets in the repo / a CDN | `stickers.image_url` |

No external API. The catalog and groups are **our data, checked into the repo**
and loaded into Postgres by a seed script — treat them like code.

## 3. Database changes (SQL)

Three new tables. See [Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0005_stickers.sql

-- the catalog, seeded from a repo fixture
create table stickers (
    code        text primary key,               -- stable id, e.g. 'first_owl'
    name        text not null,
    description text,
    image_url   text,                            -- sticker art; locked = greyed client-side
    rule_type   text not null check (rule_type in (
                    'first_ever', 'first_in_group', 'group_complete',
                    'count_milestone', 'region_complete', 'first_in_region')),
    criteria    jsonb not null default '{}',     -- {group} | {threshold} | {region}
    rarity      text not null default 'common'
                  check (rarity in ('common', 'uncommon', 'rare')),
    sort_order  int not null default 0           -- order within a rarity band
);

-- the award ledger: one row per sticker a user has earned
create table user_stickers (
    user_id        uuid not null references users(id) on delete cascade,
    sticker_code   text not null references stickers(code),
    awarded_at     timestamptz not null default now(),
    observation_id uuid references observations(id),   -- the sighting that completed it
    primary key (user_id, sticker_code)                -- makes re-awarding a no-op
);

-- group / set definitions, seeded from a repo fixture
create table groups (
    code          text primary key,              -- e.g. 'owls', 'eagles'
    kind          text not null check (kind in ('rank', 'set')),
    rank_query    text,                           -- for kind='rank', e.g. 'order:Strigiformes'
    species_codes text[]                          -- for kind='set', explicit eBird codes
);
```

| Table | Why it exists |
|---|---|
| `stickers` | The menu of everything earnable. Editing it is a data change (re-seed), not a schema change. |
| `user_stickers` | The record of who has what. The composite primary key is what makes the engine safe to re-run. |
| `groups` | Lets a rule say "owls" without hard-coding species. `rank` groups query the taxonomy; `set` groups list codes explicitly. |

### Starter catalog (seed data)

| code | name | rule |
|---|---|---|
| `first_bird` | First Bird | `first_ever` |
| `first_owl` | Night Owl | `first_in_group {owls}` |
| `first_eagle` | Eagle Eye | `first_in_group {eagles}` |
| `first_raptor` | Bird of Prey | `first_in_group {raptors}` |
| `all_eagles` | Eagle Collector | `group_complete {eagles}` |
| `species_25` | 25 Club | `count_milestone {25}` |
| `species_100` | Century | `count_milestone {100}` |
| `region_wa` | Washington Sweep | `region_complete {US-WA}` |

Put this in `backend/app/data/stickers.json` + `groups.json` and load it with a
`seed_stickers()` script.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/stickers` | the full catalog |
| `GET` | `/users/{id}/stickers` | `{earned: [...], locked: [...]}` so the shelf can show progress |

There is **no** endpoint that grants a sticker — awards only happen inside
`evaluate_stickers()`.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/sticker_repo.py` (**new**) | read `stickers` / `groups`; read + insert `user_stickers` |
| `services/` | `app/services/stickers.py` (**new**) | `evaluate_stickers(user_id)`: load life list + unearned stickers, run each rule, insert passes, emit notifications; also builds the shelf model with "3 / 8 eagles" progress |
| `routers/` | `app/routers/stickers.py` (**new**) | `GET /stickers`, `GET /users/{id}/stickers` |
| `services/` | `app/services/observation.py` (hook) | call `evaluate_stickers()` right after a `life_list_entries` insert |
| `Dao/` | `frontend/src/Dao/stickers.js` (**new**) | catalog + user stickers |
| `Services/` | `frontend/src/Services/stickers.js` (**new**) | merge catalog with earned rows → shelf model |
| `Presenters/` | `Presenters/StickerShelf.jsx` (**new**) | shelf layout, filter by rarity / earned |
| `Components/` | `Sticker` (earned vs locked art), `AwardToast` | presentational |

## 6. Build order

1. Write and run `backend/migrations/0005_stickers.sql`.
2. Add `backend/app/data/stickers.json` + `groups.json` (start with the table
   above) and a `seed_stickers()` script; run it.
3. Add `app/dao/sticker_repo.py`.
4. Add `app/services/stickers.py` — implement one rule type at a time
   (`first_ever` first, it is the simplest).
5. Call `evaluate_stickers(user_id)` from the observation service after a lifer.
6. Add `app/routers/stickers.py`.
7. Tests: seed two stickers, log observations, assert the right `user_stickers`
   rows appear and re-running the engine changes nothing.
8. Frontend: `Services/stickers.js` → `Presenters/StickerShelf.jsx` → `Sticker`
   / `AwardToast`.

## Related pages

- [Add Observation](add-observation.md) — triggers the engine
- [User profiles](user-profiles.md) — hosts the shelf and the sticker count
- [Pinned birds](pinned-birds.md) — owns the `notifications` table this shares
- [Life List page](life-list.md) — `region_checklists` feeds `region_complete`
- [Database & migrations](database.md)
