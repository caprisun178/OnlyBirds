# User profiles

> **Status:** Partial — backend done (POST /users, GET /users/by-id/{id}, GET /users/{username}, PATCH /users/{id}); frontend own-profile screen done (avatar, life list + sticker counts, default-region picker). Sign in with Google done, enforced on every user-scoped endpoint. Still planned: avatar upload, public profile view, picking a username.

## 1. What you're building

A deliberately small profile.

| Field | Source |
|---|---|
| `username` | chosen at signup, unique, immutable-ish |
| `avatar_url` | uploaded image |
| `default_region` | picked by the user from the eBird region hierarchy |
| life list total | **derived** — number of distinct species in the user's observations (same computation as the Life List page, `get_life_list`) |
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

Sign in with Google. No passwords stored, no third auth provider in between.

1. The Login screen (`Presenters/Login.js`) renders Google's own button
   (Google Identity Services, loaded by `Dao/googleIdentity.js`). Signing in
   gives the frontend a Google **ID token**.
2. `POST /auth/google {credential}` sends it to the backend, which asks Google
   to verify it (`app/dao/google_auth.py`, Google's `tokeninfo` endpoint) and
   checks it was issued for our `GOOGLE_CLIENT_ID`.
3. The backend get-or-creates the `users` row with
   `auth_provider_id = "google:<sub>"` (Google's stable account id). On the first
   sign-in the Google profile photo becomes `avatar_url`. It never overwrites one
   the user set themselves.
4. It returns **our own session token**: an HMAC-signed `{sub, exp}` under
   `SESSION_SECRET`, valid `SESSION_TTL_DAYS` (30). It's stateless, so nothing is
   stored server-side and signing out is just the frontend forgetting it.
5. The frontend keeps the session in `localStorage` (`Services/auth.js`), and
   `Dao/apiClient.js` sends `Authorization: Bearer <token>` on every request.
   A 401 on a request that carried the token signs the user out locally.

**Enforcement (backend, `app/routers/deps.py`).** Every `/users/{user_id}/...`
endpoint (observations, life list, pins, notifications, stickers) and
`PATCH /users/{id}` returns **401** when signed out and **403** when `user_id`
isn't the caller. `POST /observations` checks the body's `user_id`, and
`PATCH /observations/{id}` checks the observation's owner. `POST /uploads/photo`
needs any signed-in user. Optional `?user_id=` params (region checklist, trip
plan) work without it but are checked when present. Public reads
(`GET /users/{username}`, `GET /users/by-id/{id}`, sightings, species, the map)
need no sign-in. `POST /feedback` works signed out; signed in, the report is
attributed from the session, not the body.

**Signed out (frontend).** `preview.js`'s `SIGN_IN_REQUIRED` routes
(Add Observation, Life List, observation log, Stickers, Notifications, Profile)
redirect to Login and come back afterwards. Home disables those links and hides
the notification bell. Explore Map disables "Only my sightings" and skips
"new for you". Species pages hide seen status and disable pinning. Test Your
Skill starts at "Anywhere".

**Setup.** Set `GOOGLE_CLIENT_ID` and `SESSION_SECRET` in `backend/.env`
(see `.env.example` for where to get each). Until both are set,
`GET /auth/config` returns `{"google_client_id": null}`, the Login screen says
sign-in isn't configured, and the app behaves as signed out.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/auth/config` | `{google_client_id}`, public, null while unconfigured |
| `POST` | `/auth/google` | `{credential}` → `{token, expires_at, name, profile}`. 401 bad token, 503 unconfigured |
| `GET` | `/auth/me` | the signed-in user's profile, 401 if signed out |

The old test user `u1` isn't migrated: its rows stay in the database, but
nothing in the app signs in as it any more.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| `username` | the user, at signup | `users.username` |
| Avatar image file | the user's device | **object storage** (S3 / Supabase Storage); the URL goes in `users.avatar_url` |
| `default_region` | the user picks from the region picker (same one as the Life List — proxied eBird `GET /ref/region/list`) | `users.default_region` |
| life list total | our own data | **not stored** — computed from `observations` via `get_life_list`|
| sticker count | our own data | **not stored** — `select count(*) from user_stickers where user_id = $1` |

Totals are always computed, never cached — they are cheap counts and caching
them just creates a value that can go stale.

## 3. Database changes (SQL)

Three columns on `users`. Nothing new. See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0003_user_profile_fields.sql

alter table users add column username       text unique;
alter table users add column avatar_url     text;
alter table users add column default_region text not null default 'world';  -- eBird regionCode
```

| Column | Meaning |
|---|---|
| `username` | Public handle. `unique` so two users can't share one. Nullable because a `users` row exists before the user has picked a name. |
| `avatar_url` | URL of the uploaded image in object storage. Null → the UI shows initials. |
| `default_region` | eBird region code used as the app-wide default. `world` means "no regional bias". Not null so callers never have to handle a missing value. |

Derived totals — no column, just values the profile endpoint computes:

The life list total is computed in `app/services/user.py` by reusing `get_life_list` (the `life_list_entries` table does not exist; the life list is derived from observations).

The sticker count is a query on `user_stickers`. It currently returns `0` until Stickers merges.

```sql
select count(*) from user_stickers where user_id = $1;   -- sticker count
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
| `routers/` | `app/routers/users.py` (**new**) | `POST /users`, `GET /users/by-id/{id}`, `GET /users/{username}`, `PATCH /users/{id}` |
| `Dao/` | `frontend/src/Dao/users.js` | profile fetch by id, create, `PATCH` |
| `Services/` | `frontend/src/Services/profile.js` (**new**) | UI-shaped profile model |
| `Presenters/` | `Presenters/Profile.js` (**new**) | own-profile edit form (public view still planned) |
| `Components/` | `Avatar`, `RegionPicker` | presentational; `RegionPicker` is meant to be shared with the Life List (which still has its own inline copy) |

## 6. Build order

1. Write and run `backend/migrations/0003_user_profile_fields.sql`.
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
