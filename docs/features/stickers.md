# Stickers

> **Status:** Partial — the fixture-backed catalog, group/count rules, shelf
> API, rarity/earned filters, and award hook after a logged lifer are
> implemented. Earned stickers are saved in Postgres (`user_stickers`,
> migration 0009) so they survive redeploys; each award adds a
> `sticker_awarded` notification and is returned by `POST /observations`
> for Add Observation's "you earned a sticker" message. Region rules remain
> future work.

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

- The prototype matches groups against the `taxon_group` labels or explicit
  eBird species codes recorded in `groups.json`. The starter **eagles** group
  is an explicit curated **set of species codes**; the owl and raptor groups
  use taxon-group labels. Live taxonomy queries and rank-based group expansion
  are not implemented yet.
- `criteria.group` names a `groups` row; the engine loads that row to know which
  species count.
- `group_complete` currently needs an explicit species-code set so it has a
  known target. Region rule types are present in the model but are not active
  until observations carry a derived region and checklists are available.

### The engine

- Runs after `POST /observations` stores a `logged` observation that adds a new
  species to the derived life list; repeat sightings do not run the evaluator.
- Evaluates the refreshed life list and records newly satisfied rules in
  `user_stickers` (Postgres; an in-memory ledger when `DATABASE_URL` is unset).
  Each new award also adds one `sticker_awarded` notification, and
  `POST /observations` returns the awards as `stickers_earned`. The shelf
  endpoint recomputes current progress each time it is requested.
- A failure here never fails the logged observation: it's logged and the
  response just has no `stickers_earned`.
- **Idempotent**: the `(user_id, sticker_code)` primary key prevents
  duplicate awards. `count_milestone` and `group_complete` only ever
  go locked → earned.
- Exposed for tests/backfill as an internal `evaluate_stickers(user_id)` in
  `Services/stickers` — there is no public "grant" endpoint.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| The sticker catalog (name, optional art, rule, rarity) | a **fixture file in the repo** | in-memory catalog (Postgres `stickers` table planned) |
| Group definitions (taxon-group labels or species-code set) | a **fixture file in the repo** | in-memory group catalog (Postgres `groups` table planned) |
| Which stickers a user has earned | our engine, after each lifer | `user_stickers` (migration 0009) |
| The user's life list (engine input) | our own data | derived from logged `observations` |
| Region checklist (for `region_complete`) | reuse the [Life List](life-list.md) cache | `region_checklists` |
| Sticker art images | optional file per `code` in `backend/app/data/stickers/`, served at `/static/stickers/<code>.svg` | `stickers.image_url` holds that path; the shelf shows a placeholder until art exists |

No external API. The catalog and groups are **our data, checked into the repo**
and loaded into memory at startup. They change with the code, so they stay
fixtures rather than tables; only the awards are in Postgres.

## 3. Database changes (SQL)

Built: `user_stickers` only (`backend/migrations/0009_user_stickers.sql`),
with `sticker_code` as plain text rather than a foreign key, since the
catalog stays a fixture. The `stickers` and `groups` tables below were the
original plan and aren't needed while the catalog is a checked-in file.
See [Database & migrations](database.md#how-to-apply-a-migration).

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
| `groups` | Lets a rule say "owls" without hard-coding species. The planned `rank` rows query taxonomy; `set` rows list codes explicitly. The prototype uses taxon-group labels or explicit codes from its fixture. |

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

The current catalog is in `backend/app/data/stickers.json` and its groups are
in `backend/app/data/groups.json`; the in-memory repository validates and loads
these fixtures at startup. A Postgres seed script will replace that startup
loading when durable storage is implemented. Region stickers such as
`region_wa` remain planned until regional observations and checklists are
connected to the evaluator.

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
| `dao/` | `app/dao/sticker_repo.py` | load fixture catalog/groups; awards in Postgres (`PostgresStickerRepo`) or in memory |
| `services/` | `app/services/stickers.py` | evaluate supported rules and build a fresh shelf with current progress |
| `routers/` | `app/routers/stickers.py` | `GET /stickers`, `GET /users/{id}/stickers` |
| `services/` | `app/services/observation.py` | call `evaluate_stickers()` when a logged observation adds a life-list species |
| `Dao/` | `frontend/src/Dao/stickers.js` (**new**) | catalog + user stickers |
| `Services/` | `frontend/src/Services/stickers.js` (**new**) | validate the shelf response, resolve art URLs, and calculate totals |
| `Presenters/` | `Presenters/StickerShelf.js` | shelf layout, filter by rarity / earned, loading/error/empty states |
| `Components/` | `Components/StickerCard.js` | presentational earned/locked card with progress and placeholder art |

## 6. Build order

1. ~~Fixture-backed catalog and rules, covered by tests.~~ Done.
2. ~~Durable awards (`user_stickers`) and award notifications.~~ Done.
3. Add region rules once observations carry a derived region and checklists
   exist.
4. Add award notifications and richer award feedback in the UI.

## Related pages

- [Add Observation](add-observation.md) — triggers the engine
- [User profiles](user-profiles.md) — hosts the shelf and the sticker count
- [Pinned birds](pinned-birds.md) — owns the `notifications` table this shares
- [Life List page](life-list.md) — `region_checklists` feeds `region_complete`
- [Database & migrations](database.md)
