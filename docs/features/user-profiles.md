# User profiles

> **Status:** Planned.

## 1. What you're building

A deliberately small profile.

| Field | Source |
|---|---|
| `username` | chosen at signup, unique, immutable-ish |
| `avatar_url` | uploaded image |
| `default_region` | picked by the user from the eBird region hierarchy |
| life list total | **derived** — count of the user's `life_list_entries` rows |
| sticker collection | **derived** — the user's `user_stickers` rows |

No bio, no follower graph in MVP.

### Default region

The user selects a **default region** — one eBird region code chosen from the
same hierarchy as the [Life List region filter](life-list.md#region-filter)
(`world → country → subnational1 → subnational2`). It is the app-wide default for
everything region-scoped, so the user is not re-picking a location on every
screen:

- **Life List page** — the checklist and progress denominator load for this
  region when no explicit `region` is passed.
- **Add Observation** — the place picker's map starts centred here, and it seeds
  the `region` hint sent to `/identify/describe`.
- **Explore map** — opens centred on this region's bounds instead of a world
  view.
- **Pinned birds** — a new pin defaults its region scope to this value.

Set at first sign-in (default to a coarse guess, e.g. country from the browser
locale) and editable any time via `PATCH /users/{id}`. Individual screens may
override it locally for a session without changing the saved value.
`region = world` is the valid "no regional bias" choice.

### Views

- **Own profile**: editable avatar + username, life list total (links to the
  [Life List page](life-list.md)), full sticker shelf.
- **Public profile** (`/u/{username}`): the same, read-only, for sharing.

### Auth

Auth is delegated to a hosted provider (Auth0 / Supabase Auth). On first sign-in
we create a `users` row keyed by `auth_provider_id`; the user then picks a
`username`. The base server currently trusts `auth_provider_id` as passed —
token verification is a follow-up.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| `username` | the user, at signup | `users.username` |
| Avatar image file | the user's device | **object storage** (S3 / Supabase Storage); the URL goes in `users.avatar_url` |
| `default_region` | the user picks from the region picker (same one as the Life List — proxied eBird `GET /ref/region/list`) | `users.default_region` |
| life list total | our own data | **not stored** — `select count(*) from life_list_entries where user_id = $1` |
| sticker count | our own data | **not stored** — `select count(*) from user_stickers where user_id = $1` |

Totals are always computed, never cached — they are cheap counts and caching
them just creates a value that can go stale.

## 3. Database changes (SQL)

Three columns on `users`. Nothing new. See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0004_user_profile_fields.sql

alter table users add column username       text unique;
alter table users add column avatar_url     text;
alter table users add column default_region text not null default 'world';  -- eBird regionCode
```

| Column | Meaning |
|---|---|
| `username` | Public handle. `unique` so two users can't share one. Nullable because a `users` row exists before the user has picked a name. |
| `avatar_url` | URL of the uploaded image in object storage. Null → the UI shows initials. |
| `default_region` | eBird region code used as the app-wide default. `world` means "no regional bias". Not null so callers never have to handle a missing value. |

Derived totals — no column, just queries the profile endpoint runs:

```sql
select count(*) from life_list_entries where user_id = $1;   -- life list total
select count(*) from user_stickers      where user_id = $1;   -- sticker count
```

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/users` | create after first auth: `{auth_provider_id, username, email?}` |
| `GET` | `/users/{username}` | public profile: `username`, `avatar_url`, `life_list_total`, `sticker_count` |
| `PATCH` | `/users/{id}` | update `avatar_url` and / or `default_region` |
| `GET` | `/users/{id}/stickers` | full sticker collection (earned + locked) — see [Stickers](stickers.md) |

### Example — `GET /users/hawkeye`

```json
{
  "username": "hawkeye",
  "avatar_url": "https://storage.example/av/hawkeye.jpg",
  "default_region": "US-WA",
  "life_list_total": 142,
  "sticker_count": 7
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/user_repo.py` (**new**) | CRUD on `users`; the two `count(*)` queries |
| `services/` | `app/services/user.py` (**new**) | assemble the profile response (row + counts); validate a `username` is free |
| `routers/` | `app/routers/users.py` (**new**) | `POST /users`, `GET /users/{username}`, `PATCH /users/{id}` |
| `Dao/` | `frontend/src/Dao/user.js` (extend) | profile fetch + `PATCH` |
| `Services/` | `frontend/src/Services/profile.js` (**new**) | UI-shaped profile model |
| `Presenters/` | `Presenters/Profile.js` (**new**) | own-profile edit form + public view |
| `Components/` | `Avatar`, `RegionPicker`, `StatCount` | presentational; `RegionPicker` is shared with the Life List |

## 6. Build order

1. Write and run `backend/migrations/0004_user_profile_fields.sql`.
2. Add `app/dao/user_repo.py` and `app/services/user.py`.
3. Add `app/routers/users.py`; register it in `app/main.py`.
4. Tests: create a user, `PATCH` the `default_region`, `GET` the public profile,
   assert the counts.
5. Frontend: `Services/profile.js` → `Presenters/Profile.js` → `RegionPicker`
   (reuse from the Life List) + `Avatar`.

## Related pages

- [Life List page](life-list.md) — consumes `default_region`, shares `RegionPicker`
- [Stickers](stickers.md) — the sticker shelf on the profile
- [Pinned birds](pinned-birds.md) — new pins default to `default_region`
- [Database & migrations](database.md)
