# Life List page

> **Status:** Partial — the API already returns a user's entries; the region
> filter and the full-checklist ("completion") view are what's left to build.

This page has everything you need to build the Life List: the screens, the data,
the API, the database change, and where each piece of code goes.

## 1. What you're building

The user's personal index of every bird species. It is a **completion view**,
not just a log: it shows the full checklist of birds for a region, with the ones
the user has observed filled in and the rest shown as greyed placeholders. This
is the home screen for a signed-in user.

### Region filter

The checklist is scoped by region, chosen from a hierarchy of eBird region
codes:

```text
world → country (US) → subnational1 (US-WA) → subnational2 / county (US-WA-033)
```

- Changing the region changes **which species set** is shown and the
  denominator of the progress bar (e.g. "142 / 511 in Washington").
- The starting region is the user's
  [`default_region`](user-profiles.md#default-region); the user can change it
  for the session without saving.
- "Life list (worldwide)" is the special case `region = world`.

### Missing-bird placeholder

Every species in the region checklist renders as a card:

| State | Card shows |
|---|---|
| Observed | user's `photo_url` (or the species' representative photo), common name, `first_observed_at` |
| Not yet observed | greyed **missing-bird silhouette**, common name, "Not seen yet" |

The placeholder is one shared asset rendered by a pure `Components/MissingBird`
whenever a species has no observation for this user. Tapping a missing card
deep-links into [Add Observation](add-observation.md) pre-filled with that
species as the target.

### UI states

- **Grid** (default) and **list** toggle
- **Progress**: `seen / total` for the active region, plus a bar
- **Sort**: taxonomic (default), most recent, alphabetical
- **Empty**: brand-new user sees the whole checklist as all-missing with a "Log
  your first bird" call to action

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Region picker options (children of a region) | eBird `GET /ref/region/list/{type}/{parentCode}` | **not stored** — read live, small responses |
| Species checklist for a region (list of eBird species codes) | eBird `GET /product/spplist/{regionCode}` | **cache table `region_checklists`** — changes rarely |
| Common / scientific names for those codes | eBird `GET /ref/taxonomy/ebird` | `species` table (upsert one row per code) |
| Which species the user has actually seen | our own data | `life_list_entries` (already exists) |
| The user's photo + first-seen date per species | our own data | `life_list_entries.observation_id` → `observations` |

The completion view is assembled in `Services/lifeList.js` by taking the
`region_checklists` list and marking each species seen / not-seen using the
user's `life_list_entries`. eBird is only ever touched to *fill* the cache.

## 3. Database changes (SQL)

One new cache table. See [Database & migrations](database.md#how-to-apply-a-migration)
for how to run this.

```sql
-- 0002_life_list_region_checklists.sql

create table region_checklists (
    region_code    text primary key,        -- eBird regionCode, e.g. 'US-WA' or 'world'
    species_codes  text[] not null,         -- eBird speciesCodes in the region, taxonomic order
    fetched_at     timestamptz not null default now()
);
```

| Column | Meaning |
|---|---|
| `region_code` | The eBird region this checklist is for. It is the primary key, so one row per region. `world` is a valid value. |
| `species_codes` | A Postgres text array of eBird species codes. The frontend joins these to names via the `species` table. |
| `fetched_at` | When we last pulled this from eBird. If it is older than, say, 30 days, re-fetch and overwrite the row. |

!!! note "No change to `life_list_entries`"
    The "seen" side of the view already exists in the baseline schema. This
    feature only adds the "full checklist" side.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{user_id}/life-list?region={code}` | entries, newest first; `region` optional, defaults to the user's `default_region` |
| `GET` | `/regions?parent={code}&type={type}` | region-picker options (proxies eBird `/ref/region/list`) |
| `GET` | `/regions/{code}/checklist` | full species list for the region — names + codes + whether the user has photographed each |

`GET /users/{id}/life-list` exists today. `/regions...` and
`/regions/{code}/checklist` are new. The client builds the completion view by
zipping the last two responses together.

### Example — `GET /regions/US-WA/checklist`

```json
{
  "region_code": "US-WA",
  "total": 511,
  "species": [
    { "code": "bkcchi", "common_name": "Black-capped Chickadee", "sci_name": "Poecile atricapillus" },
    { "code": "sposan", "common_name": "Spotted Sandpiper",       "sci_name": "Actitis macularius" }
  ]
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extend) | add `get_region_children()` and `get_region_spplist()` calls |
| `dao/` | `app/dao/region_repo.py` (**new**) | read/write `region_checklists`; refetch when `fetched_at` is stale |
| `services/` | `app/services/life_list.py` (extend) | zip checklist × entries → `{species, seen, observation}` rows; compute progress; apply sort |
| `routers/` | `app/routers/life_list.py` (extend) | add `GET /regions` and `GET /regions/{code}/checklist` |
| `Dao/` | `frontend/src/Dao/lifelist.js`, `Dao/regions.js` (**new**) | fetch entries + checklist from our API |
| `Services/` | `frontend/src/Services/lifeList.js` | build the completion rows, progress, region + sort |
| `Presenters/` | `frontend/src/Presenters/LifeList.jsx` | owns region filter, sort, grid/list toggle state |
| `Components/` | `SpeciesCard`, `MissingBird`, `ProgressBar` | presentational only |

## 6. Build order

1. Write `backend/migrations/0002_life_list_region_checklists.sql` (SQL above) and run it.
2. Add `get_region_children()` / `get_region_spplist()` to `app/dao/ebird.py`.
3. Add `app/dao/region_repo.py` — `get_checklist(region_code)` returns the cached
   row, or fetches from eBird + taxonomy, upserts `species` rows, writes
   `region_checklists`, and returns it.
4. Extend `app/services/life_list.py` to combine the checklist with the user's
   entries into completion rows.
5. Add the two routes to `app/routers/life_list.py`.
6. Add a test in `backend/tests/` with a canned eBird checklist payload (no
   network).
7. Frontend: `Dao/regions.js` → `Services/lifeList.js` → `Presenters/LifeList.jsx`
   → `MissingBird` / `ProgressBar` components.

## Related pages

- [Add Observation](add-observation.md) — where a tapped missing card leads
- [User profiles](user-profiles.md) — supplies `default_region`
- [Bird information page](bird-info.md) — where a species card links to
- [Database & migrations](database.md)
