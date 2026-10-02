# Explore map

> **Status:** Partial — an MVP version is live, embedded directly on the
> Home screen: `Presenters/ExploreMap.js` + `Components/SightingsMap.js`,
> reusing the existing point+radius `GET /sightings/nearby` (search a place
> or "Use my location", pick a radius/days-back/source, see pins on a
> Leaflet map). **Everything below this point is still the original full
> spec** — viewport-driven bbox fetch, pin clustering, the `sighting_cache`
> table, `observations.geom` (PostGIS), cross-source dedupe, tap-to-log,
> notable-only filter — none of that exists yet. It's a deliberately bigger,
> separate effort; see [§0](#0-what-actually-exists-today-the-mvp) for what's
> real right now and why the gap.

## 0. What actually exists today (the MVP)

Built as a smaller stand-in for this whole page, because the full spec
depends on infrastructure that doesn't exist yet (`observations.geom` needs a
new migration; this doesn't touch the database at all) and is its own
multi-session project once it's time to build it for real.

- **Screen**: `Presenters/ExploreMap.js`, embedded directly below Home's
  header (`Presenters/Home.js` mounts it with `embedded: true` — drops the
  screen's own `<h1>`/"← Back to home" since it's already inside Home) so
  it's the first thing you see when the app loads, no click-through welcome
  page. Also reachable as its own standalone route (`explore-map`, with the
  full `<h1>` + back button) for direct access.
- **Centering**: no `default_region`/profile location yet ([User
  profiles](user-profiles.md) is still "Planned"), so the screen tries the
  browser's geolocation silently on mount (same fallback
  `Components/LocationPicker.js` already uses for Add Observation), plus an
  explicit "Use my location" button and a place search
  (`Services/geocoding.js`, the same Nominatim proxy Add Observation's
  location picker uses) for when that's denied, wrong, or the user wants
  somewhere else entirely.
- **Data**: the existing `GET /sightings/nearby?lat=&lng=&radius_km=&days_back=&source=`
  — point + radius, not a bounding box, and no caching. Merges eBird,
  iNaturalist (both with graceful degradation, see [Backend
  API](../backend.md)), **and our own logged observations** — other
  OnlyBirds users' sightings, not just the caller's own, so this is a real
  (if smaller-scope) version of the full spec's "our own + the wider
  record" idea, just without the geom column. `dao/observation_repo.py#list_near`
  does the radius filtering itself (a bounding-box SQL pre-filter, then an
  exact haversine check in Python — see that function's docstring) since
  there's no PostGIS query to lean on yet.
- **Filters**: since (7/14/30 days), radius (10/25/50/100 km), source (all /
  OnlyBirds only / eBird only / iNaturalist only) — the exact set
  `/sightings/nearby` already accepts as query params (`source=manual` for
  our own) — plus a **Bird** free-text species filter (common or scientific
  name, case-insensitive substring), the full spec's "Species → restrict to
  one species" idea, realized client-side. Unlike the other three, it never
  re-fetches: it's purely narrowing the sightings already in hand, so typing
  just tells the live map to swap its markers (`SightingsMap#setSightings()`,
  no remount) and patches the sighting count directly — no `render()`, so no
  flicker and no fighting the input's own focus on every keystroke, the same
  problem Life List's search bar solves differently (full render + restored
  focus) because *that* screen doesn't have a live map to avoid disturbing.
  Deliberately not reset by a location/radius/source/days change — "find
  this bird" reads as a standing intent while panning around, not a one-off.
- **Map**: `Components/SightingsMap.js`, a Leaflet map (loaded from a CDN via
  the now-shared `Components/leaflet.js` — extracted from
  `LocationPicker.js`, which used to carry its own copy of the same loader)
  showing one pin per sighting. Individual pins only — no clustering, so a
  dense area just gets crowded; that's exactly the "genuine problem, not a
  nice-to-have" the full spec's clustering section exists to solve, deferred
  here. One related bug this did need to handle: eBird hotspot checklists all
  report the *exact same* lat/lng, so a busy hotspot's 35 species over a week
  are 35 sightings stacked on one identical point — without correction that
  renders as a single pin (found via a real "it says 35 sightings but
  there's only one visible" report, after adding the "top spots" click-to-zoom
  feature made it obvious). `SightingsMap.js#layoutMarkerPositions()` fans
  coordinate-duplicates (within ~1m) out into a small ~8m ring around the
  true point before placing markers — no clustering library, every pin stays
  individually clickable, and `onSelectSighting` still gets the sighting's
  real unmodified lat/lng (only the *marker's drawn position* is jittered).
  Basemap is Esri's "Light Gray Canvas" tile set
  (`leaflet.js#addBaseTileLayer()`) instead of standard OpenStreetMap street
  tiles — a plain gray reference map with a transparent label overlay for
  place names, no dense street labels or business/POI icons crowding the
  sightings pins. Shared with `LocationPicker.js` (Add Observation's map) so
  both screens use the same basemap rather than each picking its own.
  (Originally CARTO's Positron tiles here; switched to Esri's keyless
  equivalent once CARTO started requiring a free API key for anonymous tile
  requests in September 2026 — see the note below.)
- **Detail panel**: clicking a pin doesn't open a small map popup — it opens
  a docked panel to the right of the map (`Components/SightingDetail.js`,
  shared markup so it isn't duplicated anywhere else this gets shown),
  always reserving its space (a placeholder shows when nothing's selected)
  so clicking a pin doesn't shift the map's width around. Shows everything
  that might actually help someone relocate the bird, not just species+date:
  a photo, the free-text location label (`location_name`) and notes,
  sex/life-stage, sight-vs-sound, and a source badge. Clicking the photo
  opens it full-size in a lightbox overlay (`ExploreMap.js`'s
  `enlargePhoto()`/`renderLightboxContent()`) — Escape, the backdrop, or the
  close button all dismiss it. Selecting a pin patches the panel's DOM
  directly rather than calling `render()` (see below) — otherwise every pin
  click would remount the whole Leaflet map just to show a detail panel.
- **Region summary ("Trip planning" box)**: sits below the map/detail-panel
  row, over the currently-filtered sightings (respects species/days/
  radius/source same as the status line and map pins) — how many distinct
  species have been spotted, how many of those would be new additions to the
  signed-in user's life list, and up to 5 named locations ranked by sighting
  count ("top spots to check out"). All computed client-side in
  `ExploreMap.js#regionSummary()` over sightings already fetched for the map —
  no new endpoint. "New for you" compares each sighting's scientific name
  against `lifeListService.getSeenScientificNames(userId)` (the user's whole
  life list, fetched once per mount — unscoped by region, since there's no
  lat/lng → eBird-region-code mapping to narrow it to "this region" the way
  the Life List screen does); a sighting with no scientific name is still
  counted toward diversity but never counted as "new" rather than guessing.
  "Top spots" groups by `location_name` — eBird already sets this from
  `locName`; iNaturalist sightings didn't carry one until this feature needed
  it to group by (see note below), so sightings from either source can show
  up there. Sightings with no location name at all are silently excluded from
  the ranking (a raw lat/lng isn't an actionable "spot to visit"). Styled as
  two stat cards (species count / new-for-you count, colour-coded via the
  existing info/success tag tokens) plus a ranked list of top spots (🥇🥈🥉
  for the top 3) rather than a plain paragraph — the subtitle under the "Trip
  planning" heading restates the active days-back/radius/place so the numbers
  are self-explanatory without re-reading the filters above. Each top spot is
  clickable (`data-action="focus-area"`, keyboard-operable too — same `role`/
  `tabindex`/Enter-or-Space pattern as the detail panel's photo) and calls
  `SightingsMap#focusArea(bounds)` with that area's lat/lng bounding box
  (tracked alongside the count in `regionSummary()`'s `areaStats`): the map
  zooms (`fitBounds`) to fit all of that area's sightings and draws an orange
  rectangle outline around them, padded a bit past the exact bounds so pins
  on the edge aren't flush against the border. A later click replaces the
  outline; it isn't a filter — other pins outside the rectangle stay visible,
  this is purely a "look here" visual cue, not a `source`/`mineOnly`-style
  narrowing of what's shown.
- **Highlighting your own sightings**: pins belonging to the logged-in user
  (`sighting.user_id === userId` — only ever true for `source: 'manual'`
  sightings, since eBird/iNat ones never carry a `user_id`) render with a
  small green dot (`Components/SightingsMap.js#ownSightingIcon()`, an
  `L.divIcon` using `var(--ob-color-success-text)` — the same green Life
  List already uses for "seen" — rather than Leaflet's default blue pin) so
  they stand out at a glance; a one-line legend under the map (part of
  `renderStatusLine()`) spells out the count and color. A separate **Only my
  sightings** checkbox in the filters row narrows the map/panel/trip-planning
  box down to just those — distinct from the existing **Source → OnlyBirds
  only** filter, which shows every OnlyBirds user's sightings, not just this
  one. Purely client-side over `filteredSightings()` (`state.mineOnly`), same
  "skip render(), patch the map + status line + trip-planning box directly"
  pattern as the species filter — toggling it doesn't remount the map.
- **Collapsible panels**: both the trip-planning box and the docked sighting
  detail panel have a Hide/Show toggle in their header (`state.tripPlanningCollapsed`
  / `state.detailPanelCollapsed`), independent of each other — either can be
  tucked away to give the map more room, e.g. the detail panel once you've
  already noted what you came for, or the trip-planning box once you've
  already picked a spot. Collapsing the detail panel also drops its fixed
  560px height/scroll (`detailPanelExpandedStyle()` in `ExploreMap.js`) so it
  shrinks to just its header instead of leaving an empty scrollable box.
- **Not built**: `observations.geom` / PostGIS, `sighting_cache`,
  viewport-driven fetch (panning the map doesn't refetch — only the explicit
  filters/search do), clustering, cross-source dedupe, "notable only", tap an
  empty spot to log a sighting there, species search / deep-link.

!!! note "A real adapter bug, found by building this popup"
    `app/services/adapters.py#from_ebird` used to stuff eBird's `locName`
    into `notes` instead of `location_name` — harmless while nothing read
    `location_name` for an eBird sighting, but once the popup started
    showing both fields distinctly, an eBird pin's hotspot name would have
    shown up mislabeled as a free-text "note" instead of a location. Fixed
    to set `location_name` like it should have from the start;
    `test_adapters.py` has the regression test.

!!! note "iNaturalist sightings had no `location_name` at all — a third adapter gap"
    `from_inaturalist` never set `location_name`, since nothing read it until
    the region-summary box needed to group sightings by named location.
    iNaturalist's nearest equivalent to eBird's `locName` is `place_guess` (a
    free-text, human-entered place description) — now mapped across the same
    way. `test_adapters.py` covers it.

!!! note "iNaturalist photos were extremely blurry — a second adapter bug"
    `from_inaturalist` was taking `photos[0].url` as-is, but iNaturalist's
    observation API only ever returns the 75x75 "square" thumbnail there —
    fine for a tiny list icon, badly pixelated stretched to fill the detail
    panel's ~300px-wide image. Confirmed live: the same photo object's
    `original_dimensions` reports the real size (e.g. 776x618), and a
    "medium" (500px) version exists at the identical path, just a different
    filename. `_upgrade_inat_photo_size()` swaps `square.jpg` for
    `medium.jpg` before it ever reaches the frontend — see `test_adapters.py`.

!!! note "CARTO started requiring an API key for its free basemap tiles"
    The basemap was originally CARTO's "Positron" tiles
    (`basemaps.cartocdn.com`), picked for being free and keyless. CARTO
    changed that in September 2026: anonymous tile requests now come back
    stamped "API KEY REQUIRED" instead of a clean tile. A key is free (up to
    5M tile requests/month, no CARTO account needed) but still means a new
    external dependency to register for and keep configured, for a static,
    no-build-step frontend with no natural place to keep a key out of the
    public JS anyway. Switched to Esri's "Light Gray Canvas" tiles instead
    (`server.arcgisonline.com/.../Canvas/World_Light_Gray_Base` +
    `..._Reference` for labels) — visually similar, genuinely keyless, no
    account. One gotcha: Esri's tile path is `{z}/{y}/{x}` (y before x),
    unlike the `{z}/{x}/{y}` convention CARTO/OSM/most other providers use —
    easy to transpose and get upside-down-looking tiles.

### Re-rendering a live map from a template-string Presenter

Every screen in this codebase (`docs/frontend-screens.md`) rebuilds its whole
container from an HTML template string on each render — fine for markup, bad
for a stateful Leaflet instance, which needs its DOM node to survive. Both
map components sidestep this the same way `Presenters/AddObservation.js`
already does for `LocationPicker`: the map lives outside `state`, and the
Presenter tears it down and remounts it after every render rather than
re-rendering it as markup. `ExploreMap.js` goes one step further and restores
the map's own pan/zoom after each remount (via `SightingsMap#getView()`), so
picking a filter doesn't visually snap the map back to the searched
location — except right after actually searching for or geolocating to a new
place, where snapping there is the correct behavior. A `mapGeneration`
counter guards against a slow remount's Leaflet-loading promise resolving
after a newer remount already started (e.g. two filter changes in quick
succession) and clobbering the newer one.

The detail panel and the photo lightbox take the opposite approach:
selecting a pin or clicking its photo doesn't touch `render()`/`wireMap()`
at all — `updateDetailPanelDom()`/`updateLightboxDom()` patch just that one
element's `innerHTML` directly, the same "targeted update" pattern
`Presenters/AddObservation.js` already uses for its photo-upload status.
Going through a full `render()` for either would remount the whole Leaflet
map (tiles and all) just from clicking a pin or a photo. The lightbox's
Escape-key listener is attached to `document` only while it's open, not for
the Presenter's whole lifetime — this app tears down and remounts a fresh
Presenter on every route change, so anything attached to `document` instead
of a DOM node that gets discarded needs its own explicit `removeEventListener`
or it accumulates one stale listener per visit.

This is also why nesting `ExploreMap` inside `Home` (`embedded: true`)
doesn't fight itself: `Home.js` builds its own markup and mounts `ExploreMap`
into a sub-container exactly once, with no re-render loop of its own
afterward, so `ExploreMap`'s repeated remount-on-render cycle stays entirely
inside its own sub-container — Home's header never gets touched by it, and
vice versa.

## 1. What you're building (the full spec)

A full-screen slippy map for browsing **who saw what, where**. It opens centred
on the user's [`default_region`](user-profiles.md#default-region) bounds; the
user pans and zooms anywhere in the world and the map shows recent bird
sightings for whatever is in view — the user's own, plus the wider birding
record from eBird and iNaturalist.

### Behaviour

- **Viewport-driven**: pan / zoom settles → refetch sightings for the visible
  bounding box and the active date window. A debounce plus a minimum zoom (no
  "whole planet" fetch) keeps request volume sane.
- **Clustered pins**: dense areas collapse into count bubbles; tap a cluster to
  zoom in, tap a pin for a popup — species (links to its
  [info page](bird-info.md)), date, source badge (eBird / iNat / OnlyBirds),
  observer name where public, and a **pin this species** action.
- **Tap-to-log**: long-press an empty spot to start
  [Add Observation](add-observation.md) with that lat/lng prefilled.
- **Layers**: individual sightings (default) or a heat / abundance overlay at
  low zoom.

### Filters

| Filter | Options |
|---|---|
| Date | last 7 / 30 days (default 7), custom range |
| Species | free-text → restrict to one species; deep-linked from a species page's "recent sightings nearby" |
| Source | eBird, iNaturalist, OnlyBirds — any combination |
| Notable only | eBird's rare / notable observations for the region |

## 2. Where the data comes from and where it goes

Endpoint details (auth, base URL, failure behavior) live on the
[eBird API](../ebird-api.md) page, not here.

| Data | Comes from | Stored where |
|---|---|---|
| eBird recent sightings in a region | eBird `GET /data/obs/{regionCode}/recent` | **cache table `sighting_cache`** (`source = 'ebird'`) |
| eBird recent sightings near a point | eBird `GET /data/obs/geo/recent?lat=&lng=` | `sighting_cache` |
| eBird notable sightings | eBird `GET /data/obs/{regionCode}/recent/notable` | `sighting_cache` |
| iNaturalist sightings in a bounding box | iNat `GET /v1/observations?taxon_id=3&nelat=&nelng=&swlat=&swlng=` (taxon 3 = Aves), research-grade only | `sighting_cache` (`source = 'inat'`) |
| The user's own + other OnlyBirds users' sightings | our own data | `observations` (queried by `geom` bounding box — no cache needed) |
| Obscured coordinates (iNat sensitive taxa) | iNat returns them already coarsened | store + display as-is, flagged; **never** try to un-obscure |

!!! note "External sightings are read-through, not our data"
    We do **not** create an `observations` row for an eBird or iNat sighting.
    They live only in `sighting_cache`, keyed by map tile + time window, and
    expire. Our own `observations` are the only sightings we own. The map merges
    the two at request time.

## 3. Database changes (SQL)

One cache table. Depends on `observations.geom` (added by
[Add Observation](add-observation.md)) and PostGIS (baseline). See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0008_sighting_cache.sql

create table sighting_cache (
    id           uuid primary key default gen_random_uuid(),
    tile         text not null,          -- map tile / geohash key for the fetched area
    since_bucket text not null,          -- date window key, e.g. '2026-09-02..2026-09-09'
    source       text not null check (source in ('ebird', 'inat')),
    sightings    jsonb not null,         -- normalised [{source, source_id, species, common_name,
                                         --              lat, lng, observed_at, observer, obscured}]
    fetched_at   timestamptz not null default now(),
    unique (tile, since_bucket, source)  -- one cached blob per area+window+source
);
create index sighting_cache_lookup_idx on sighting_cache (tile, since_bucket);
```

| Column | Meaning |
|---|---|
| `tile` | A key for the geographic area we fetched (a slippy-map tile id or a geohash prefix). The service snaps the live viewport to the nearest tile so nearby pans reuse the same cache row. |
| `since_bucket` | A key for the date window, so "last 7 days" and "last 30 days" cache separately. |
| `source` | `ebird` or `inat`. Our own observations are **not** cached here. |
| `sightings` | The whole normalised result for that area+window+source, as one JSON blob. Cheaper than a row per sighting for data we throw away. |
| `fetched_at` | Re-fetch when older than a few minutes to an hour, depending on how fresh the map needs to feel. |
| unique `(tile, since_bucket, source)` | Upsert target — a refresh overwrites the blob in place. |

### Our own sightings — the bounding-box query (no new table)

```sql
select id, species_id, lat, lng, observed_at, user_id
from observations
where geom && st_makeenvelope(:west, :south, :east, :north, 4326)
  and observed_at >= :since
  and status = 'logged';
```

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/sightings?bbox={w,s,e,n}&since={date}&species={code}&source={list}&notable={bool}` | merged, deduped, normalised sightings for the viewport |
| `GET` | `/sightings/{source}/{source_id}` | single sighting detail for the popup |

`GET /sightings/nearby` already exists (a simpler point+radius version). This
feature generalises it to a bounding box with filters and caching.

### Dedupe rule

The same species at the same place on the same day, reported to more than one
service, collapses to **one pin with multiple source badges**. Key on
`(species_code, round(lat, 3), round(lng, 3), observed_on_date)`.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extend) | `recent_obs_in_region()`, `recent_obs_near()`, `notable_obs()` |
| `dao/` | `app/dao/inaturalist.py` (extend) | `obs_in_bbox()` |
| `dao/` | `app/dao/sighting_cache_repo.py` (**new**) | read / upsert `sighting_cache` by `(tile, since_bucket, source)` |
| `dao/` | `app/dao/observation_repo.py` (extend) | the bounding-box query above |
| `services/` | `app/services/sightings.py` (extend) | viewport → tile + bucket keys; fetch-or-cache each source; merge our observations; dedupe; apply filters; cluster when counts are large |
| `routers/` | `app/routers/sightings.py` (extend) | `GET /sightings` (bbox form) + `GET /sightings/{source}/{source_id}` |
| `Dao/` | `frontend/src/Dao/sightings.js` (**new**) | viewport fetch |
| `Services/` | `frontend/src/Services/map.js` (**new**) | camera seeded from `default_region`, filter state → query params |
| `Presenters/` | `Presenters/ExploreMap.js` (**new**) | map camera, filters, pin selection, tap-to-log hand-off |
| `Components/` | `MapCanvas`, `SightingCluster`, `SightingPin`, `SightingPopup`, `MapFilters`, `MapLegend`, `AttributionFooter` | presentational |

## 6. Build order

1. Confirm [Add Observation](add-observation.md) has landed `observations.geom`.
2. Write and run `backend/migrations/0008_sighting_cache.sql`.
3. Extend `app/dao/ebird.py` + `app/dao/inaturalist.py` with the bbox / region
   calls.
4. Add `app/dao/sighting_cache_repo.py` (fetch-or-cache).
5. Extend `app/services/sightings.py`: keys, merge, dedupe, filters.
6. Generalise `GET /sightings` to the bbox form; keep `/sightings/nearby`.
7. Tests: canned eBird + iNat payloads that overlap on one species/place/day;
   assert one merged pin with two badges, and that a second call hits the cache.
8. Frontend: `Services/map.js` (camera from `default_region`) →
   `Presenters/ExploreMap.js` → map components + `AttributionFooter`.

## Related pages

- [Add Observation](add-observation.md) — supplies `observations.geom`; tap-to-log lands here
- [User profiles](user-profiles.md) — supplies the starting map centre
- [Bird information page](bird-info.md) — sighting popups link here
- [Pinned birds](pinned-birds.md) — pin a species straight from a popup
- [Database & migrations](database.md)
- [eBird API](../ebird-api.md) — auth, endpoints, failure behavior
