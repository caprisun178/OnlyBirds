# Pinned birds

> **Status:** Partial — backend built and tested end to end (`region_for_point()`,
> `observations.region`, `pinned_birds` + `notifications` tables, match/dedupe
> engine wired into every logged observation, full pin + notification API).
> Frontend (`PinButton`, `NotificationBell`, `NotificationsFeed.js`) not yet
> built. One real design change from this page's original draft: matching is
> keyed on **`scientific_name`**, not eBird's `speciesCode` — see the note in
> [§3](#3-database-changes-sql) for why.

## 1. What you're building

A **want-to-see list**. The user pins a species they are chasing; when someone
else logs that species in the user's region, the user gets a notification —
"A Snowy Owl was just reported in US-WA". This turns the
[Life List](life-list.md) placeholders from a passive checklist into active
targets.

This feature also introduces the app's **first notification feed** — a bell icon
with an unread count. [Stickers](stickers.md) award messages use the same feed.

### Pinning

- Any not-yet-observed species can be pinned — from its `MissingBird` card on
  the Life List, or from the [species info page](bird-info.md).
- A pin carries a **region scope**, defaulting to the user's
  [`default_region`](user-profiles.md#default-region). The user can widen it
  (pin at `US` while travelling) or narrow it (`US-WA-033`).
- Pinning a species the user has already logged is a no-op — nothing to chase.
- A pin auto-clears once the species lands on the user's life list. Manual
  unpin any time.

### Match + notify

Runs **after every logged `observations` row** (not just lifers — someone else
seeing a common bird is still a sighting the user might chase), right alongside
the [sticker engine](stickers.md#the-engine):

```text
new observation  (by user O, region R = e.g. 'US-WA-033', species S)
        │
        ▼
find pinned_birds rows where
      species matches S
  AND the pin's region contains R      (world ⊇ US ⊇ US-WA ⊇ US-WA-033)
  AND user_id <> O                     (don't notify the person who reported it)
        │
        ▼
for each → insert a 'pin_hit' notification   (deduped to one per user/species/region/day)
```

- **Region containment** is eBird-code prefix matching: `world` matches
  everything; otherwise `R` matches the pin's region when `R = region` or `R`
  starts with `region || '-'`.
- **Dedupe**: at most one `pin_hit` per `(user, species, region, day)` — a
  twitchy species reported five times in a morning is one nudge, with a count.
- Location is coarsened to the region — never exact lat/lng — and the reporter's
  username is shown only if their profile is public.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| A pin (species + region scope) | the user tapping "pin" | `pinned_birds` table |
| The default region for a new pin | the user's profile | read from `users.default_region` |
| The trigger to check pins | our own `POST /observations` completing | in-process call to `evaluate_pins(observation)` |
| A notification | our engine | `notifications` table |
| Unread badge count | our own data | `select count(*) ... where read_at is null` |
| Deep-link target in a notification | our own data | `notifications.payload` holds `observation_id`, `species`, `region` |

**Entirely our own data.** No external API — a `pin_hit` fires off *another
user's* observation that we already stored.

## 3. Database changes (SQL)

Three changes, across two migrations (numbered after this repo's actual
migration history — `0004`/`0005`, not this page's original `0006` draft).
See [Database & migrations](database.md#how-to-apply-a-migration).

!!! note "Matching is keyed on `scientific_name`, not eBird's `speciesCode`"
    The original draft below keyed `pinned_birds` (and the match query) on
    eBird's `speciesCode`. Checked against `app/services/adapters.py` while
    building this: an eBird-sourced observation's species carries
    `source_ids={"ebird": ...}` *only*, an iNaturalist-sourced one carries
    `source_ids={"inat": ...}` *only*, and neither is guaranteed on a
    manually-logged sighting — which is most of what this app actually logs.
    Matching on an eBird-only code would silently miss every manual and
    iNaturalist sighting. `scientific_name` is the one species identity
    every source reliably sets (manual entries always resolve one through
    the identification flow), so that's the real key, both for the unique
    constraint and the match query.

`backend/migrations/0004_observation_region.sql` — completes the schema gap
`docs/features/database.md` already flagged ("region/geom still to come"):

```sql
alter table observations add column if not exists region text;
create index if not exists observations_region_idx on observations (region);
```

`backend/migrations/0005_pinned_birds_and_notifications.sql` — the two new
tables:

```sql
-- the want-to-see list
create table if not exists pinned_birds (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references users(id) on delete cascade,
    species_id       uuid references species(id),
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
```

| Column | Meaning |
|---|---|
| `pinned_birds.region` | How wide the user is watching. The match query treats this as a prefix. |
| `pinned_birds` unique `(user_id, scientific_name)` | Pinning the same bird twice just updates the region instead of making a duplicate. `scientific_name`, not `species_id` — `species_id` is nullable, and a unique constraint on a nullable column doesn't stop duplicates when it's null (Postgres treats every null as distinct). |
| `notifications.kind` | Which feature raised it. Add a value here when a new feature needs the feed. |
| `notifications.payload` | Everything the UI needs to render the row **without another query** — species, region, the observation to deep-link to. |
| `notifications.dedupe_key` | The engine builds this string and relies on the `unique` constraint: a second insert with the same key fails cleanly (`on conflict (dedupe_key) do nothing`), so the day's repeats collapse to one row. |
| partial index `... where read_at is null` | Makes the unread badge count fast — it only indexes unread rows. |

**Not yet applied to a live database** — these are written and committed
(the "permanent record," per `database.md`'s own convention) but running
`backend/scripts/migrate.sh` against the real Neon/Supabase database is a
separate, explicit step for whoever owns that connection string.

### The match query

```sql
-- :obs_region and :scientific_name come from the new observation
select p.user_id
from pinned_birds p
where lower(p.scientific_name) = lower(:scientific_name)
  and p.user_id is distinct from :observer_id
  and ( p.region = 'world'
        or :obs_region = p.region
        or :obs_region like p.region || '-%' );
```

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{id}/pins` | the user's pinned species + region scope |
| `POST` | `/users/{id}/pins` | `{scientific_name, common_name?, region?}`; `region` defaults to `default_region`; idempotent per `(user, scientific_name)`; `409` if already on the user's life list |
| `PATCH` | `/users/{id}/pins/{scientific_name}` | `{region}` — change the region scope; `404` if not pinned |
| `DELETE` | `/users/{id}/pins/{scientific_name}` | unpin; `404` if not pinned |
| `GET` | `/users/{id}/notifications?unread=true` | feed, newest first |
| `POST` | `/users/{id}/notifications/read` | `{}` marks all read, or `{ids: [...]}` for specific ones |

`{scientific_name}` in a path is the plain species name (e.g.
`Bubo scandiacus`), URL-encoded by the caller as needed — FastAPI decodes
it automatically.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extend) | `region_for_point(lat, lng)` — finds the nearest hotspot (`get_hotspots_near()`, expanding radius up to eBird's 500km cap) and reads its `subnational2Code`/`subnational1Code`/`countryCode`; falls back to `"world"` |
| `dao/` | `app/dao/pin_repo.py` (**new**) | CRUD on `pinned_birds`; the match query above; dual in-memory/Postgres, same pattern as `observation_repo.py` |
| `dao/` | `app/dao/notification_repo.py` (**new**) | insert (swallow a `dedupe_key` clash via `on conflict ... do nothing`), list, mark-read, unread count |
| `models/` | `app/models/pin.py`, `app/models/notification.py` (**new**) | `PinnedBird`, `PinCreate`, `PinRegionUpdate`, `Notification` |
| `services/` | `app/services/pins.py` (**new**) | `evaluate_pins(observation)`: run the match, build `dedupe_key`, insert notifications; `pin(user, payload)` with the "already on life list" guard (via `life_list.py#get_life_list`) |
| `services/` | `app/services/notifications.py` (**new**) | feed model + unread count; shared by pins and stickers |
| `routers/` | `app/routers/pins.py`, `app/routers/notifications.py` (**new**) | the endpoints above |
| `services/` | `app/services/observation.py` (hook) | compute `region` via `region_for_point()` before persisting; call `evaluate_pins(observation)` after every logged observation (deferred import — see that file's comment on the circular-import reason) |
| `Dao/` | `frontend/src/Dao/pins.js`, `Dao/notifications.js` (**planned**) | raw calls |
| `Services/` | `frontend/src/Services/pins.js`, `Services/notifications.js` (**planned**) | UI models |
| `Presenters/` | `PinToggle` state on the Life List card; `NotificationsFeed.js` (**planned**) | |
| `Components/` | `PinButton`, `NotificationBell`, `NotificationList` (**planned**) | presentational |

## 6. Build order

1. ✅ `backend/migrations/0004_observation_region.sql`,
   `0005_pinned_birds_and_notifications.sql` — written, not yet applied to a
   live database (see [§3](#3-database-changes-sql)).
2. ✅ `app/dao/ebird.py#region_for_point()` — implemented, confirmed live
   (`US-NC-067` for a real Winston-Salem point; `"world"` for mid-Pacific).
3. ✅ `app/dao/pin_repo.py` and `app/dao/notification_repo.py`.
4. ✅ `app/services/notifications.py` (generic — stickers will use it too).
5. ✅ `app/services/pins.py` with `evaluate_pins()` and the pin guard.
6. ✅ `app/services/observation.py` — region computed and `evaluate_pins()`
   called for every logged observation.
7. ✅ `app/routers/pins.py` + `app/routers/notifications.py`; registered in
   `app/main.py`.
8. ✅ Tests (`test_ebird.py`, `test_pins.py`): the doc's own suggested
   scenario (user A pins at `US-WA`; user B logs inside `US-WA-033`; A gets
   exactly one `pin_hit`; a same-day repeat adds none; a different day
   doesn't dedupe) plus region-prefix matching, the life-list guard,
   reporter self-exclusion, and the full notification feed/mark-read flow.
9. ⬜ Frontend: `PinButton` on the `MissingBird`/`SpeciesCard` cards, then
   `NotificationBell` + `NotificationsFeed.js`.

## Related pages

- [Add Observation](add-observation.md) — every log runs `evaluate_pins`
- [Stickers](stickers.md) — shares the `notifications` table
- [User profiles](user-profiles.md) — supplies the default pin region
- [Life List page](life-list.md) — the `MissingBird` card hosts `PinButton`
- [Database & migrations](database.md)
