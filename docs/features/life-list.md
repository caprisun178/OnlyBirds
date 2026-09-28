# Life List page

> **Status:** Partial — the region completion view works end to end against
> the live eBird API (region picker, checklist, seen/unseen, progress, sort,
> filters, pagination), and a seen card now opens that species' observation
> log (`Presenters/ObservationList.js`) via `preview.js`'s route-param
> support. What's left: PostgreSQL persistence for the checklist cache
> (roadmap step 3), the "world" life list, and deep-linking a *missing* card
> into Add Observation.

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

Next to the other filters (Show/Type/Sort) there's also a quick **State**
dropdown — the whole US plus every state/DC (`GET /regions?parent=US&type=subnational1`,
loaded eagerly on mount, not lazily like the picker's own state dropdown) —
so jumping to a specific state's checklist is one click instead of opening
"Change region" and re-picking country → state each time. Both controls
drive the same `state.regionCode`/`loadChecklist()` (`changeRegion()`), so
they stay in sync: picking a county via "Change region" leaves the quick
dropdown showing "Custom region" (`isKnownQuickRegion()`) rather than
silently defaulting to the wrong state.

There's no `default_region` to start from yet ([`user-profiles.md`](user-profiles.md)
is still "Planned"), so the screen takes an initial `region` prop (falls back
to `"US"`) instead — swap that for the real default once profiles exist.
**`region = "world"` isn't supported yet** — eBird's species-list endpoint
needs an actual region code, and a worldwide checklist is on the order of
11,000 species, which needs pagination *and* a real persistent cache before
it's practical to fetch at all. Trying it today would just 5xx.

The checklist genuinely is scoped to the picked region — `region_repo` only
ever calls eBird's spplist endpoint for that exact region code. What can
still look wrong: `GET /product/spplist/{regionCode}` returns *every* species
code *ever* reported there, with no "is this actually established here"
concept — so a single old report of an escaped farm/zoo bird (a Common
Ostrich has genuinely been reported once in the US, per live eBird data)
stays on the list forever. Two layers filter that out:

1. `region_repo._drop_escapees` drops species eBird currently flags
   `exoticCategory: "X"` (escapee, not countable) in that region — see
   [eBird API](../ebird-api.md#exoticcategory--not-in-the-api-reference-but-documented-by-cornell)
   for where that field comes from (Cornell Lab's own documentation, not the
   API reference) and its limitation: it only reads observations from the
   last 30 days (eBird's own cap on that endpoint, not ours), so a species
   whose *only* escapee report is older than that has no live signal to
   catch it. Verified live: drops ~26 currently-reported escapees from the
   US list on its own.
2. `app/data/exotic_exclusions.py` is a hand-maintained set of eBird species
   codes to always exclude, for exactly the escapees layer 1 can't see. It
   doesn't need an eBird API call at all, so it's not subject to the 30-day
   limitation. It's deliberately not "exclude every exotic species" — most
   exotics (House Sparrow, European Starling, Rock Pigeon, ...) are
   Naturalized and belong on a life list same as a native bird; layer 1
   already draws that line correctly for anything within its 30-day window.
   This list only covers the gap outside it, and every entry is
   cross-checked against a second, independent source (not just eBird)
   before being added: [National Audubon's Guide to North American
   Birds](https://www.audubon.org/bird-guide) has no page for any species on
   this list, corroborating that none of them belong on a US checklist.

   Seeded 2026-09-24 with the obvious ratite/tinamou cases (Common Ostrich,
   Emu, Rheas, Chilean Tinamou, Magpie Goose, ...), then grown to 165+
   entries in a 2026-09-26 full pass: every species on the live US checklist
   with zero activity anywhere in the US in eBird's last 30 days (the same
   profile as Ostrich — a one-off historic aviculture-escapee report, not an
   ongoing population) *and* individually checked, not assumed by family —
   several families in this list (waterfowl, gamebirds) have real
   native/vagrant/Naturalized members mixed in with the exotics. That
   individual check mattered: the "zero recent activity" signal alone would
   have wrongly caught Gunnison Sage-Grouse and Lesser Prairie-Chicken, two
   genuine, imperiled native US species that are simply hard to detect, not
   exotics — it finds candidates, it doesn't decide on its own. Extinct
   *native* species (Labrador Duck, Carolina Parakeet) and historically
   native ones (Thick-billed Parrot) were deliberately kept off the list too
   for the same reason: not native ≠ extinct or hard-to-find.

   West Indian Whistling-Duck is also on this list, but it's a different
   kind of entry — a product call, not a settled fact like the others. eBird
   itself classifies it "Provisional" (not "Escapee") when reported: a
   Caribbean vagrant where natural occurrence and captive origin are both
   considered plausible, and Cornell's own rules count Provisional records
   toward official eBird totals — which is exactly why layer 1 doesn't drop
   it. It's excluded here anyway, on the reasoning that a life list meant to
   represent genuine wild sightings shouldn't include a record eBird itself
   can't rule out as captive. Worth revisiting if FOSRC (Florida's records
   committee) or eBird ever resolves this one to Naturalized.

### Missing-bird placeholder

Every species in the region checklist renders as a card:

| State | Card shows |
|---|---|
| Observed | a photo — always one of: the user's own `photo_url`, a Wikimedia Commons stock photo, or (if Commons has nothing, or the request itself fails) a generated placeholder, same as the describe & guess flow — see [below](#2-where-the-data-comes-from-and-where-it-goes) — common name, scientific name, "Seen — \<date>" |
| Not yet observed | a greyed placeholder icon, common name, scientific name, "Not seen yet" |

`Components/SpeciesCard.js` renders the observed state, `Components/MissingBird.js`
the placeholder — the [Presenter](#5-how-the-code-is-layered) picks one per
species based on its `seen` flag.

A seen card is clickable — it opens that species' observation log
(`Presenters/ObservationList.js`, at the `observation-log` route) via
`onNavigate('observation-log', { userId, scientificName, commonName, region,
regionLabel })`; "Back to life list" carries `region`/`regionLabel` back so
the return trip doesn't reset the region picker.

`ObservationList.js` itself (also reachable unscoped, as "My observations",
for a future nav entry — not wired to `Home` yet) shows:
- a highlighted **"First observed"** banner (`ob-alert--success`) above the
  list — the earliest `observed_at` in whatever's currently shown, computed
  client-side (not sorted-array-position, so it stays correct across edits);
- each observation as a card with an **Edit** button that swaps it for an
  inline form (date, location, sex, life stage, sight/sound, photo, notes) —
  `Services/observations.js#updateObservation` → `PATCH
  /observations/{id}` (`ObservationUpdate`, backend), touching only the
  fields the form actually sends. The photo field reuses
  `Services/uploads.js#uploadPhoto` (same `POST /uploads/photo` the Add
  Observation wizard uses) — picking a new file uploads it immediately and
  swaps the preview in via a targeted DOM update, not a full re-render, so
  an in-flight upload doesn't wipe out text the user's still typing into
  Notes; if the upload fails, the observation's existing photo is kept
  rather than cleared;
- no 👀/🔊 detection-type icon for "sight" (only sound gets 🔊) — the eye
  emoji read as noise once every card had one.

Missing cards aren't
clickable yet: the doc's original plan was to deep-link a tap into Add
Observation pre-filled with that species — still pending, unlike the seen
case, since nothing in Add Observation's wizard accepts a pre-filled species
yet.

### UI states

- **Grid** (default) and **list** toggle — same cards, different container
  layout; there isn't yet a distinct compact row design for list view.
- **Progress**: `seen / total` for the active region, plus a bar
  (`Components/ProgressBar.js`).
- **Sort**: taxonomic (default), most recent, alphabetical — resorts the
  already-fetched list client-side (`Services/lifeList.js#sortSpecies`), no
  extra network call. Taxonomic mode (the default) buckets observed species
  first — still in taxonomic order within each bucket — then not-yet-seen
  species, so the default view (and the "Show more" progression below) works
  through the user's own life list before the rest of the region's
  checklist.
- **Filters**: seen/unseen (`state.seenFilter`) and bird type
  (`state.typeFilter`, an eBird family name like "Ducks, Geese, and
  Waterfowl" or "Crows, Jays, and Magpies") narrow the list before it's
  sliced to the visible count. The type dropdown's options
  (`lifeListService.getFamilies`) are the distinct `family_common_name`
  values present in the current region's checklist — eBird taxonomy data
  (see [API endpoints](#4-api-endpoints)), not a curated list, so options
  vary by region. Both are purely client-side over the already-fetched
  checklist; changing either resets the visible count back to 50.
- **Default filter + "Show more"**: only the first 50 species after
  sort+filter render initially. Not in the original plan, but a real region
  checklist runs 500-700+ species (and a country-level one, thousands) —
  rendering all of them at once is a genuine problem, not a nice-to-have. A
  "Show N more" button under the list grows the visible count by 50 at a
  time (`LOAD_INCREMENT` in `Presenters/LifeList.js`) until every matching
  species is shown; the button disappears at that point. Purely client-side
  over data already in hand — changing region, sort, or a filter resets the
  visible count back to 50.
- **Empty**: a `seen === 0` region shows a "You haven't logged any birds in
  \<region> yet" banner above the (all-missing) checklist, rather than
  replacing the checklist — the completion view is the point even for a
  brand-new user.

## 2. Where the data comes from and where it goes

Endpoint details (auth, base URL, failure behavior) live on the
[eBird API](../ebird-api.md) page, not here.

| Data | Comes from | Stored where |
|---|---|---|
| Region picker options (children of a region) | eBird `GET /ref/region/list/{type}/{parentCode}` | **not stored** — read live, small responses |
| Species checklist for a region (list of eBird species codes) | eBird `GET /product/spplist/{regionCode}` | **cache table `region_checklists`** — changes rarely |
| Common / scientific names for those codes | eBird `GET /ref/taxonomy/ebird` | `species` table (upsert one row per code) |
| Which species the user has actually seen | our own data | **not stored separately** — derived live from `observations` (`app/services/life_list.py`), one entry per species, dated to the earliest sighting |
| The user's photo + first-seen date per species | our own data | that same earliest `observations` row's `photo_url` / `observed_at` |
| Stock photo for a seen species with no user `photo_url` | Wikimedia Commons (`app/dao/commons.py#search_photo`, by scientific name) | **in-memory cache** in `app/dao/bird_photos.py` (`get_stock_photo()`, shared with the describe & guess flow's `get_photo()`) — process-lifetime, same as `region_repo`'s cache |

The completion view is assembled in `Services/lifeList.js` by taking the
`region_checklists` list and marking each species seen / not-seen using
`GET /users/{id}/life-list` (already derives its entries from `observations`
on every call — no separate "seen" table to keep in sync). eBird is only
ever touched to *fill* the checklist cache. For each seen species whose
observation has no `photo_url`, `app/services/life_list.py` calls
`bird_photos.get_stock_photo()`, which **always** returns a photo — a real
Commons one, or (Commons has nothing, or the request itself fails) a
generated `placehold.co` placeholder labelled with the species' common name,
same generator `app/data/birds.py` uses for the describe & guess flow's
candidate cards — so a seen card never renders with no image at all.
`ChecklistSpecies.photo_attribution` is set only for a real Commons photo
(Creative Commons requires the credit line; neither the user's own upload
nor the placeholder needs one).

Commons' search API rate-limits fairly readily — a region checklist can look
up photos for dozens of seen species in one request, easily triggering a
`429`. That's exactly the case the placeholder covers, but it's also why a
rate-limited (or otherwise failed) lookup is deliberately **not** cached as
a permanent "no photo": `app/dao/commons.py#CommonsUnavailable` is a
distinct exception from a genuine empty result, and `bird_photos.py` only
caches the latter — a transient failure just falls back for that one
request, leaving the next lookup free to retry Commons for a real photo.

Real photo isn't always the *right* photo, either: American Robin's stock
photo was a museum egg specimen, not a live bird — Commons' top search hit
for a scientific name is sometimes a GLAM-batch-uploaded specimen photo,
filename just an accession number. `commons.py`'s photo search now fetches
a few extra candidates and skips ones that look like a specimen rather than
the live animal (by title, category, or metadata, in English or French) —
see `docs/features/add-observation.md`'s note on this (same fix, shared by
both flows since they both go through `commons.py`).

## 3. Database changes (SQL)

One new cache table, committed as
`backend/migrations/0002_life_list_region_checklists.sql` — same shape as
originally planned, but not applied anywhere yet. The running app uses the
in-memory cache in `app/dao/region_repo.py` instead; swapping in this table
is the roadmap-step-3 PostgreSQL work.

```sql
-- 0003_life_list_region_checklists.sql

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

!!! note "No new table for the \"seen\" side"
    `GET /users/{id}/life-list` already derives every entry live from
    `observations` — there's no separate table to keep in sync. This feature
    only adds the "full checklist" side (`region_checklists`).

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
      "seen": false, "first_observed_at": null, "photo_url": null, "photo_attribution": null, "family_common_name": "Ducks, Geese, and Waterfowl" },
    { "code": "norcar", "common_name": "Northern Cardinal", "scientific_name": "Cardinalis cardinalis",
      "seen": true, "first_observed_at": "2026-06-15T08:00:00Z", "photo_url": "https://...", "photo_attribution": null, "family_common_name": "Cardinals" },
    { "code": "amerob", "common_name": "American Robin", "scientific_name": "Turdus migratorius",
      "seen": true, "first_observed_at": "2026-06-10T08:00:00Z", "photo_url": "https://upload.wikimedia.org/...",
      "photo_attribution": "Jane Birder / Wikimedia Commons (CC BY-SA 3.0)", "family_common_name": "Thrushes" }
  ]
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extended) | `get_taxonomy()`, `get_region_children()`, `get_region_spplist()` — raw eBird calls |
| `dao/` | `app/dao/region_repo.py` (**new**) | in-memory checklist cache in front of the eBird calls above; drops non-species categories, hand-excluded codes (`app/data/exotic_exclusions.py`), and currently-flagged escapees (`_drop_escapees`), sorts taxonomically, carries each species' `family_common_name` through from taxonomy |
| `dao/` | `app/dao/bird_photos.py` (extended) | `get_stock_photo(scientific_name, common_name)` — cached Commons photo lookup with a generated placeholder fallback (same as `get_photo()`'s, for the describe & guess flow); both share one cache. A transient `commons.CommonsUnavailable` isn't cached, only a genuine empty result is. |
| `services/` | `app/services/life_list.py` (extended) | `get_region_children()` maps to `RegionOption`; `get_region_checklist()` merges the checklist with the user's `life_list_entries` (by scientific name) into `ChecklistSpecies` rows + progress, filling in a stock photo for seen species with no `photo_url` |
| `routers/` | `app/routers/life_list.py` (extended) | `GET /regions`, `GET /regions/{region_code}/checklist`; maps `EBirdConfigError` → 503 |
| `Dao/` | `frontend/src/Dao/regions.js` (**new**) | raw calls to the two endpoints above |
| `Services/` | `frontend/src/Services/lifeList.js` (**new**) | fetches the checklist; `sortSpecies()` — client-side re-sort (seen-first in taxonomic mode) with no refetch; `getFamilies()` — distinct bird types for the type filter |
| `Presenters/` | `frontend/src/Presenters/LifeList.js` (**new**) | region picker state, filters, sort, grid/list toggle, "Show more"; wires each seen card to `onNavigate('observation-log', …)` |
| `Services/` | `frontend/src/Services/observations.js` (extended) | `updateObservation()` — maps field-notes-shaped edits to an `ObservationUpdate` PATCH body |
| `Presenters/` | `frontend/src/Presenters/ObservationList.js` (**new**) | the `observation-log` route — a user's observations, optionally scoped to one species by `scientificName`; first-observed banner; inline edit per card |
| `Components/` | `SpeciesCard.js`, `MissingBird.js`, `ProgressBar.js` (**new**) | presentational only |

## 6. Build order

1. Write `backend/migrations/0003_life_list_region_checklists.sql` (SQL above) and run it.
2. Add `get_region_children()` / `get_region_spplist()` to `app/dao/ebird.py`.
3. Add `app/dao/region_repo.py` — `get_checklist(region_code)` returns the cached
   row, or fetches from eBird + taxonomy, upserts `species` rows, writes
   `region_checklists`, and returns it.
4. Extend `app/services/life_list.py` to combine the checklist with the user's
   entries into completion rows.
5. Add the two routes to `app/routers/life_list.py`.
6. Add a test in `backend/tests/` with a canned eBird checklist payload (no
   network).
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
