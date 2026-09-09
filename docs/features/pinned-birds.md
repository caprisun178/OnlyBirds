# Pinned birds

> **Status:** Planned. Build after [Add Observation](add-observation.md) (needs
> `observations.region`) and [User profiles](user-profiles.md) (pins default to
> `default_region`).

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

Two new tables. See [Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0006_pinned_birds_and_notifications.sql

-- the want-to-see list
create table pinned_birds (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references users(id) on delete cascade,
    species_id   uuid references species(id),
    species_code text not null,                 -- eBird speciesCode (kept even if species row is thin)
    region       text not null,                 -- eBird regionCode scope; 'world' allowed
    created_at   timestamptz not null default now(),
    unique (user_id, species_id)                -- one pin per species per user
);
create index pinned_birds_species_idx on pinned_birds (species_code);

-- the notification feed (shared with Stickers)
create table notifications (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users(id) on delete cascade,
    kind        text not null check (kind in ('pin_hit', 'sticker_awarded')),
    payload     jsonb not null default '{}',    -- pin_hit: {species, region, observation_id, count}
    dedupe_key  text unique,                    -- e.g. 'pin_hit:<user>:<species>:<region>:2026-09-09'
    read_at     timestamptz,                    -- null until the user opens the feed
    created_at  timestamptz not null default now()
);
create index notifications_unread_idx on notifications (user_id, created_at desc)
    where read_at is null;
```

| Column | Meaning |
|---|---|
| `pinned_birds.region` | How wide the user is watching. The match query treats this as a prefix. |
| `pinned_birds` unique `(user_id, species_id)` | Pinning the same bird twice just updates the region instead of making a duplicate. |
| `notifications.kind` | Which feature raised it. Add a value here when a new feature needs the feed. |
| `notifications.payload` | Everything the UI needs to render the row **without another query** — species, region, the observation to deep-link to, and the dedupe count. |
| `notifications.dedupe_key` | The engine builds this string and relies on the `unique` constraint: a second insert with the same key fails cleanly, so the day's repeats collapse to one row. |
| partial index `... where read_at is null` | Makes the unread badge count fast — it only indexes unread rows. |

### The match query

```sql
-- :obs_region and :species_code come from the new observation
select p.user_id
from pinned_birds p
where p.species_code = :species_code
  and p.user_id <> :observer_id
  and ( p.region = 'world'
        or :obs_region = p.region
        or :obs_region like p.region || '-%' );
```

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{id}/pins` | the user's pinned species + region scope |
| `POST` | `/users/{id}/pins` | `{species, region?}`; `region` defaults to `default_region`; idempotent per `(user, species)` |
| `PATCH` | `/users/{id}/pins/{species}` | change the region scope |
| `DELETE` | `/users/{id}/pins/{species}` | unpin |
| `GET` | `/users/{id}/notifications?unread=true` | feed, newest first |
| `POST` | `/users/{id}/notifications/read` | mark all read, or `{ids: [...]}` |

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/pin_repo.py` (**new**) | CRUD on `pinned_birds`; the match query above |
| `dao/` | `app/dao/notification_repo.py` (**new**) | insert (swallow a `dedupe_key` clash), list, mark-read, unread count |
| `services/` | `app/services/pins.py` (**new**) | `evaluate_pins(observation)`: run the match, build `dedupe_key`, insert notifications; `pin(user, species, region)` with the "already on life list" guard |
| `services/` | `app/services/notifications.py` (**new**) | feed model + unread count; shared by pins and stickers |
| `routers/` | `app/routers/pins.py`, `app/routers/notifications.py` (**new**) | the endpoints above |
| `services/` | `app/services/observation.py` (hook) | call `evaluate_pins(observation)` after every logged observation |
| `Dao/` | `frontend/src/Dao/pins.js`, `Dao/notifications.js` (**new**) | raw calls |
| `Services/` | `frontend/src/Services/pins.js`, `Services/notifications.js` (**new**) | UI models |
| `Presenters/` | `PinToggle` state on the Life List card; `NotificationsFeed.jsx` (**new**) | |
| `Components/` | `PinButton`, `NotificationBell`, `NotificationList` | presentational |

## 6. Build order

1. Write and run `backend/migrations/0006_pinned_birds_and_notifications.sql`.
2. Add `app/dao/pin_repo.py` and `app/dao/notification_repo.py`.
3. Add `app/services/notifications.py` (generic — stickers will use it too).
4. Add `app/services/pins.py` with `evaluate_pins()` and the pin guard.
5. Call `evaluate_pins(observation)` from the observation service.
6. Add `app/routers/pins.py` + `app/routers/notifications.py`; register both.
7. Tests: user A pins `snowy` at `US-WA`; user B logs `snowy` at `US-WA-033`;
   assert A gets exactly one `pin_hit`, and a second identical log the same day
   adds none.
8. Frontend: `PinButton` on the `MissingBird` card, then `NotificationBell` +
   `NotificationsFeed.jsx`.

## Related pages

- [Add Observation](add-observation.md) — every log runs `evaluate_pins`
- [Stickers](stickers.md) — shares the `notifications` table
- [User profiles](user-profiles.md) — supplies the default pin region
- [Life List page](life-list.md) — the `MissingBird` card hosts `PinButton`
- [Database & migrations](database.md)
