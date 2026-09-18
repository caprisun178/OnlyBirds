# Life List page

> **Status:** Partial — the region completion view works end to end against
> the live eBird API (region picker, checklist, seen/unseen, progress, sort,
> pagination). What's left: PostgreSQL persistence for the checklist cache
> (roadmap step 3), the "world" life list, and deep-linking a missing card
> into Add Observation (no cross-screen navigation exists yet at all).

## 1. What you're building

The user's personal index of every bird species. It is a **completion view**,
not just a log: it shows the full checklist of birds for a region, with the
ones the user has observed filled in and the rest shown as greyed
placeholders.

### Region filter

The checklist is scoped by region, picked from eBird's region hierarchy:

```text
world → country (US) → subnational1 (US-WA) → subnational2 / county (US-WA-033)
```

The "Change region" picker is three cascading dropdowns — country, then
state/province, then county — each populated from the previous pick
(`GET /regions?parent=&type=`). Any level can be used directly: pick a
country and hit "View this region's checklist" without ever touching the
state/county dropdowns, and the checklist scopes to the whole country.

There's no `default_region` to start from yet ([`user-profiles.md`](user-profiles.md)
is still "Planned"), so the screen takes an initial `region` prop (falls back
to `"US"`) instead — swap that for the real default once profiles exist.
**`region = "world"` isn't supported yet** — eBird's species-list endpoint
needs an actual region code, and a worldwide checklist is on the order of
11,000 species, which needs pagination *and* a real persistent cache before
it's practical to fetch at all. Trying it today would just 5xx.

### Missing-bird placeholder

Every species in the region checklist renders as a card:

| State | Card shows |
|---|---|
| Observed | the user's `photo_url` from their observation, common name, scientific name, "Seen — \<date>" |
| Not yet observed | a greyed placeholder icon, common name, scientific name, "Not seen yet" |

`Components/SpeciesCard.js` renders the observed state, `Components/MissingBird.js`
the placeholder — the [Presenter](#5-how-the-code-is-layered) picks one per
species based on its `seen` flag. Missing cards aren't clickable yet: the
doc's original plan was to deep-link a tap into Add Observation pre-filled
with that species, but there's no router or cross-screen navigation
anywhere in this codebase yet (every screen is mounted standalone via
`preview.js` — see `docs/frontend-screens.md`), so that's wired up once one
exists.

### UI states

- **Grid** (default) and **list** toggle — same cards, different container
  layout; there isn't yet a distinct compact row design for list view.
- **Progress**: `seen / total` for the active region, plus a bar
  (`Components/ProgressBar.js`).
- **Sort**: taxonomic (default, as returned by eBird), most recent,
  alphabetical — resorts the already-fetched list client-side
  (`Services/lifeList.js#sortSpecies`), no extra network call.
- **Pagination**: 60 species per page. Not in the original plan, but a real
  region checklist runs 500-700+ species (and a country-level one, thousands)
  — rendering all of them as one page is a genuine problem, not a
  nice-to-have. Purely client-side over data already in hand; changing region
  or sort resets to page 1.
- **Empty**: a `seen === 0` region shows a "You haven't logged any birds in
  \<region> yet" banner above the (all-missing) checklist, rather than
  replacing the checklist — the completion view is the point even for a
  brand-new user.

## 2. Where the data comes from and where it goes

Endpoint details (auth, base URL, failure behavior) live on the
[eBird API](../ebird-api.md) page, not here.

| Data | Comes from | Stored where |
|---|---|---|
| Region picker options (children of a region) | eBird `GET /ref/region/list/{type}/{parentCode}` | not stored — read live, small responses |
| Species checklist for a region | eBird `GET /product/spplist/{regionCode}` (codes) + `GET /ref/taxonomy/ebird?species=...` (names), merged and filtered to real species | in-memory cache, one entry per region, 30-day staleness (`app/dao/region_repo.py`) |
| Which species the user has actually seen, first-seen date | our own data | `life_list_entries` (derived from `observations`, already exists) |
| The user's photo per seen species | our own data | `observations.photo_url`, looked up via the entry's `observation_id` |

`app/services/life_list.py#get_region_checklist` does the seen/unseen merge
**server-side** — matching a checklist species to a life-list entry by
scientific name (same fallback key `get_life_list` already uses for
cross-source dedupe) — and returns one already-zipped response. That's a
deliberate change from the original plan below, which had the frontend zip
two separate responses together; doing it server-side means the matching
logic (and its scientific-name-based caveats) lives in one place instead of
two.

!!! note "eBird's species list includes non-species entries"
    `GET /product/spplist` returns some `spuh`/slash/hybrid/domestic codes
    alongside real species (e.g. "duck sp." when a checklist couldn't
    identify the exact species) — those aren't identifiable species and
    shouldn't count toward a life list. `region_repo.get_checklist` fetches
    each code's `category` from the taxonomy call and keeps only
    `category == "species"`.

## 3. Database changes (SQL)

One new cache table, committed as
`backend/migrations/0002_life_list_region_checklists.sql` — same shape as
originally planned, but not applied anywhere yet. The running app uses the
in-memory cache in `app/dao/region_repo.py` instead; swapping in this table
is the roadmap-step-3 PostgreSQL work.

```sql
-- 0002_life_list_region_checklists.sql

create table if not exists region_checklists (
    region_code    text primary key,        -- eBird regionCode, e.g. 'US-WA' or 'world'
    species_codes  text[] not null,          -- eBird speciesCodes in the region, taxonomic order
    fetched_at     timestamptz not null default now()
);
```

| Column | Meaning |
|---|---|
| `region_code` | The eBird region this checklist is for. Primary key, so one row per region. |
| `species_codes` | A Postgres text array of eBird species codes. Join to a `species` table for names once that table exists (it doesn't yet — `region_repo.get_checklist` fetches names from eBird's taxonomy endpoint directly, filtered and cached alongside the codes, rather than upserting a separate table). |
| `fetched_at` | When we last pulled this from eBird. The in-memory cache already refetches past 30 days; this column exists so the same policy carries over to Postgres. |

!!! note "No change to `life_list_entries`"
    The "seen" side of the view already exists in the baseline schema. This
    feature only adds the "full checklist" side.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{user_id}/life-list` | existing — a user's own entries, newest first (no region scoping) |
| `GET` | `/regions?parent={code}&type={type}` | region-picker options; `type` is `country` \| `subnational1` \| `subnational2`; `parent=world` for the country level |
| `GET` | `/regions/{region_code}/checklist?user_id={id}` | the region's full checklist, each species marked seen/unseen for `user_id`; omit `user_id` for an unpersonalized species catalog |

Both new endpoints return `503` if `EBIRD_API_KEY` isn't set (there's no
fallback data source for taxonomy/region data the way `/sightings/nearby`
falls back to iNaturalist-only), and `502` if eBird itself errors.

### Example — `GET /regions/US-NC/checklist?user_id=u1`

```json
{
  "region_code": "US-NC",
  "total": 518,
  "seen": 5,
  "species": [
    { "code": "plwduc1", "common_name": "Plumed Whistling-Duck", "scientific_name": "Dendrocygna eytoni",
      "seen": false, "first_observed_at": null, "photo_url": null },
    { "code": "norcar", "common_name": "Northern Cardinal", "scientific_name": "Cardinalis cardinalis",
      "seen": true, "first_observed_at": "2026-06-15T08:00:00Z", "photo_url": "https://..." }
  ]
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extended) | `get_taxonomy()`, `get_region_children()`, `get_region_spplist()` — raw eBird calls |
| `dao/` | `app/dao/region_repo.py` (**new**) | in-memory checklist cache in front of the two eBird calls above; drops non-species categories, sorts taxonomically |
| `services/` | `app/services/life_list.py` (extended) | `get_region_children()` maps to `RegionOption`; `get_region_checklist()` merges the checklist with the user's `life_list_entries` (by scientific name) into `ChecklistSpecies` rows + progress |
| `routers/` | `app/routers/life_list.py` (extended) | `GET /regions`, `GET /regions/{region_code}/checklist`; maps `EBirdConfigError` → 503 |
| `Dao/` | `frontend/src/Dao/regions.js` (**new**) | raw calls to the two endpoints above |
| `Services/` | `frontend/src/Services/lifeList.js` (**new**) | fetches the checklist; `sortSpecies()` — client-side re-sort with no refetch |
| `Presenters/` | `frontend/src/Presenters/LifeList.js` (**new**) | region picker state, sort, grid/list toggle, pagination |
| `Components/` | `SpeciesCard.js`, `MissingBird.js`, `ProgressBar.js` (**new**) | presentational only |

## 6. Build order

1. Fill in the three eBird DAO stubs: `get_taxonomy()`, `get_region_children()`,
   `get_region_spplist()` in `app/dao/ebird.py` — these were already stubbed
   with the exact endpoint/params documented, just not implemented.
2. `app/dao/region_repo.py` — fetch + cache a region's checklist, filtered to
   `category == "species"`, sorted by `taxonOrder`.
3. Extend `app/models/life_list.py` with `RegionOption` and `ChecklistSpecies`
   / `RegionChecklistResponse`.
4. Extend `app/services/life_list.py` and `app/routers/life_list.py` with the
   two new endpoints.
5. Tests in `backend/tests/test_life_list_regions.py`: canned eBird payloads
   (taxonomy + spplist), assert non-species filtering, taxonomic sort,
   in-memory caching (second call doesn't refetch), the seen/unseen merge,
   and the `EBirdConfigError` → 503 mapping — all offline, per this repo's
   "no test hits the live API" rule.
6. `backend/migrations/0002_life_list_region_checklists.sql` — SQL parity for
   when PostgreSQL is wired up (not applied anywhere yet).
7. Frontend: `Dao/regions.js` → `Services/lifeList.js` → `Presenters/LifeList.js`
   → `Components/SpeciesCard.js` / `MissingBird.js` / `ProgressBar.js`.

Verified end to end against the live eBird API (not just canned test data):
region picker drill-down (world → country → state), checklist fetch and
cache-hit timing (~1.8s cold, ~0.3s cached), and the seen/unseen merge with
real logged observations.

Not yet done: PostgreSQL persistence for the checklist cache, the `world`
region, deep-linking a missing card into Add Observation, and a distinct
list-view row layout (list view currently reuses the grid card in a
single-column stack).

## Related pages

- [Add Observation](add-observation.md) — where a tapped missing card will
  lead, once cross-screen navigation exists
- [User profiles](user-profiles.md) — will supply `default_region`
- [Bird information page](bird-info.md) — where a species card links to,
  eventually
- [Database & migrations](database.md)
- [eBird API](../ebird-api.md) — auth, endpoints, failure behavior
