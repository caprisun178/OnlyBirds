# Plan a trip

> **Status:** Completed — backend and frontend both built end to end
> (`GET /trip/plan`, `GET /trip/hotspot-sightings`, `Presenters/PlanATrip.js`,
> the Home button); verified live against both real APIs, including the
> hotspot drill-down's eBird + iNaturalist merge. A first tap on a hotspot
> takes ~7-8 seconds (confirmed live); a repeat tap on the same hotspot is
> cached and near-instant. See the note in
> [§2](#2-where-the-data-comes-from-and-where-it-goes) before touching the
> eBird window or the cache. Standalone feature — originally considered as a
> subsection of
> [Explore map](explore-map.md)'s Trip Planning box, but deliberately kept
> separate: it answers a different question ("I'm going somewhere on
> specific dates — what should I expect and where should I go") than Explore
> Map's "what's around here right now." See that page's history for the
> earlier, smaller version this grew out of (built, then reverted, while
> this page didn't exist yet).

## 1. What you're building

A **Plan a Trip** button (Home, next to Life List / Add Observation) opens a
small form: a destination (place search, same autocomplete pattern as
Explore Map's) and a trip date range (start date, end date — not a single
day, since an actual trip is rarely one day). Submitting it returns:

1. **Suggested hotspots** near the destination — real eBird-designated
   birding locations, not a guess from whatever sightings happen to share a
   location name (see the note below on why that distinction matters).
2. **Likely species** for those dates — ranked by how often they were
   reported in roughly that same window *last year*, so a user visiting in
   late October sees what late-October birding there has actually looked
   like, not a generic year-round list.
3. **New for you** — which of those likely species aren't already on the
   user's life list, so a trip can be framed around "what might I add,"
   not just "what's common."

Tapping a suggested hotspot opens a drill-down: a small map (reusing Explore
Map's `Components/SightingsMap.js`) scoped tightly to that one hotspot,
showing the actual iNaturalist sightings there in the same window last
year — not just the aggregate "likely species" count, but *which* sightings,
where, and (tapping a pin) the same detail card Explore Map uses.

Framed honestly, not oversold: this is **one year of historical comparison**
via iNaturalist, not a genuine multi-year statistical frequency model (see
[§2](#2-where-the-data-comes-from-and-where-it-goes) for why, and
[Explore map](explore-map.md)'s own history — this is the second time this
exact scoping conversation happened, so it's written down here this time).

### Why this needed its own page

The earlier version of "species likely around now" lived inside Explore
Map's Trip Planning box, scoped to *today*, in whatever area the map
happened to be centered on. That answers "what's around here right now" —
useful while already browsing, but it's a different question from "I'm
flying out on the 14th, what should I expect and where should I go," which
needs its own destination input, its own date range, and a focus on
*hotspots* (named, visitable places) rather than a generic radius circle.
Trying to cram both into one box made neither answer clearly, so this is a
separate screen with its own button, reached deliberately rather than
stumbled into while panning the map.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Destination → lat/lng | OpenStreetMap Nominatim (`GET /geocode/search`, already built — see [Add Observation](add-observation.md)) | not persisted, just used for this request |
| Suggested hotspots | eBird `GET /ref/hotspot/geo?lat=&lng=&dist=` — real, named, eBird-curated birding locations, each with `numSpeciesAllTime` as a popularity signal | not persisted — fetched fresh per request |
| Likely species for the date range | iNaturalist `GET /observations/species_counts?lat=&lng=&radius=&d1=&d2=&taxon_id=3&quality_grade=research` — species ranked by how many observations they had in *last year's* equivalent date window | not persisted — fetched fresh per request |
| "New for you" | the user's own life list (`app/services/life_list.py#get_life_list`, already built) | not persisted — computed per request by set-difference |
| Hotspot drill-down sightings | iNaturalist `GET /observations?lat=&lng=&radius=&d1=&d2=&taxon_id=3&quality_grade=research` — the raw sightings behind one hotspot's slice of that same last-year window, tightly scoped (2km) to the single hotspot rather than the whole trip search radius — **plus** eBird `GET /data/obs/{locId}/historic/{y}/{m}/{d}`, one call per day in the window, merged in alongside iNaturalist's (see the note below) | not persisted — fetched fresh per hotspot tap |

!!! note "Why eBird hotspots, not Explore Map's location-name grouping"
    Explore Map's "top spots" feature groups whatever sightings it already
    has by their free-text `location_name` and ranks by count — which only
    produces a usable list where multiple sightings happen to share the
    *exact same* location string. That's a fine incremental improvement over
    nothing for a box that's already showing sightings anyway, but it's the
    wrong foundation for "suggest me somewhere to go": it can't suggest a
    real place with zero recent sightings (most hotspots, most weeks), and
    it has no sense of which named places are actually established birding
    locations versus a one-off GPS point. eBird's own Hotspots API is built
    for exactly this — real, named, user-curated locations specifically
    because people birded there enough for it to earn hotspot status.

!!! note "Why this is one year of comparison, not real frequency data"
    eBird's actual seasonal/frequency data (the bar-chart "how often is this
    species seen here each week of the year" visualizations on ebird.org)
    comes from their separate **Status & Trends** data product — not the
    public API this app already has a key for, and not something reachable
    without a different kind of access entirely. eBird's `/data/obs/.../historic`
    endpoint is the closest the public API gets, but it's per-day and keyed
    by eBird region code, not point+radius, so it would need a
    lat/lng → region-code lookup this app doesn't have yet (`region_for_point()`
    in `app/dao/ebird.py` is still an unimplemented stub for exactly this
    reason). iNaturalist's API *does* support point+radius plus a date
    range directly, so "what showed up here in roughly this window last
    year" is genuinely buildable today — it's just one year, not an
    average, and the UI should say so rather than imply more confidence
    than the data supports.

!!! note "Why the comparison window is padded ±30 days (±7 for eBird)"
    The naive version of this shifted the trip's exact `start_date`/`end_date`
    back one year and searched only that span — for a multi-day trip that's
    a reasonable slice, but for a short or single-day trip it's a single day
    a year ago, too thin a slice of real observation density to reliably
    return anything (confirmed live: a single-day trip at a tight 2km
    hotspot radius came back with zero sightings). `_last_year_window()` in
    `app/services/trip.py` pads both ends — `_DATE_WINDOW_PAD_DAYS` (30) for
    iNaturalist, which costs one API call regardless of window size, so
    widening it is free. eBird is different (see the note below): its
    historic endpoint costs one real HTTP call *per day* in the window, so
    `hotspot_sightings()` gives eBird its own narrower
    `_EBIRD_DATE_WINDOW_PAD_DAYS` (7) instead — iNaturalist's full ±30 days
    still covers the "single-day trip returns nothing" case on its own, so
    eBird's narrower window doesn't bring that problem back.

!!! note "The hotspot drill-down's eBird merge: why it's not instant, and what cuts the cost"
    eBird's only historical-data endpoint (`/data/obs/{regionCode}/historic/{y}/{m}/{d}`)
    has no date-range parameter and is keyed by region code, not lat/lng —
    but it does accept a hotspot's own `locId` as that region code (confirmed
    live: real per-day checklist data came back from a real hotspot), which
    is what makes this reachable at all without the lat/lng→region lookup
    `region_for_point()` in `app/dao/ebird.py` still doesn't have. The
    tradeoff: one HTTP call per day in the window. `_ebird_historic_window()`
    in `app/services/trip.py` caps concurrency at `_EBIRD_HISTORIC_CONCURRENCY`
    (8) rather than firing every day's call at once — docs/ebird-api.md
    already flags this app as having no rate-limiting built yet.
    `EBirdConfigError`/`httpx.HTTPError` on any single day is swallowed, not
    propagated, so a bad or missing key degrades to iNaturalist-only results
    rather than failing the whole request.

    A first live end-to-end test (±30-day eBird window, 61 calls) came back
    in **~29 seconds** — too slow to ship as-is. Two changes brought a cold
    (first-ever) tap on a hotspot down to **~7-8 seconds**, confirmed live:
    narrowing eBird's own window to ±7 days (61 calls → ~15-20), and
    `_hotspot_sightings_cache` — an in-process dict in `app/services/trip.py`,
    keyed on every input that affects the result (lat, lng, radius, dates,
    `loc_id`), with no TTL or eviction, since the data is a year-old window
    that genuinely barely changes within a process's lifetime. A **repeat**
    tap on the same hotspot with the same trip dates is served from that
    cache and returns in well under a second (confirmed live: ~0.3s). A
    failed call is never cached (the exception raises before the line that
    stores it), so a transient eBird/iNaturalist failure doesn't get stuck
    as a permanently-cached empty result. The cache is cleared on restart —
    it's process-local, not the shared `sighting_cache` table the full
    Explore Map spec still has planned, which would be the next step if
    this needs to survive restarts or be shared across users.

## 3. Database changes (SQL)

None. Nothing here persists — every request re-fetches fresh from eBird,
iNaturalist, and the user's own (already-stored) life list. A future version
could cache hotspot lists (they don't change often) the same way the full
Explore Map spec's `sighting_cache` table is meant to, but that's not needed
to ship a working v1.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/trip/plan?lat=&lng=&radius_km=&start_date=&end_date=&user_id=` | hotspots + likely species (+ life-list gap if `user_id` given) → `TripPlan` |
| `GET` | `/trip/hotspot-sightings?lat=&lng=&start_date=&end_date=&radius_km=&loc_id=` | actual sightings near one hotspot in the same last-year window → `list[Observation]`, for the drill-down map |

`start_date`/`end_date` are `YYYY-MM-DD`, the *actual* trip dates (this
year or any year) — the service translates them to the equivalent window
one year earlier before querying iNaturalist; the caller never has to do
that math (both endpoints do this the same way). `user_id` on `/trip/plan`
is optional: omit it and `new_for_you` on every species is just omitted
rather than guessed at. `radius_km` on `/trip/hotspot-sightings` defaults
to a tight 2km (a specific hotspot, not the whole trip search area). `loc_id`
is also optional: given (the frontend always passes the tapped hotspot's
own `loc_id`), eBird checklist data for that hotspot is merged in too — see
the warning above on what that costs; omitted, results are iNaturalist-only.

### Response shape

```jsonc
{
  "hotspots": [
    {"loc_id": "L123456", "name": "Sandy Ridge Reservation", "lat": 41.5, "lng": -81.8, "species_all_time": 214}
  ],
  "likely_species": [
    {
      "species": {"common_name": "Yellow-rumped Warbler", "scientific_name": "Setophaga coronata"},
      "observation_count": 18,
      "photo_url": "https://...",
      "new_for_you": true
    }
  ]
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/ebird.py` (extend) | `get_hotspots_near(lat, lng, radius_km)` — `GET /ref/hotspot/geo`; `get_historic_checklist(region_code, d)` — `GET /data/obs/{region_code}/historic/{y}/{m}/{d}`, accepts a hotspot's own `locId` as `region_code` (confirmed live) |
| `dao/` | `app/dao/inaturalist.py` (extend) | `get_species_counts(lat, lng, radius_km, d1, d2)` — `GET /observations/species_counts` (this exact function existed once already, for Explore Map's now-removed seasonal box — same shape, revived here); `get_nearby_observations()` extended with optional `d1`/`d2` for the hotspot drill-down |
| `models/` | `app/models/trip.py` (**new**) | `Hotspot`, `LikelySpecies`, `TripPlan` (the drill-down reuses the existing `Observation` model, not a new one) |
| `services/` | `app/services/trip.py` (**new**) | date-range → last-year window; fan out to hotspots + species_counts concurrently; cross-reference the caller's life list for `new_for_you`; `hotspot_sightings()` for the drill-down, merging iNaturalist with `_ebird_historic_window()`'s concurrency-capped per-day eBird loop (its own narrower ±7-day window), result cached in `_hotspot_sightings_cache` |
| `routers/` | `app/routers/trip.py` (**new**) | `GET /trip/plan`, `GET /trip/hotspot-sightings` |
| `Dao/` | `frontend/src/Dao/trip.js` (**new**) | raw `GET /trip/plan` and `GET /trip/hotspot-sightings` calls |
| `Services/` | `frontend/src/Services/trip.js` (**new**) | param shaping, defaults |
| `Presenters/` | `Presenters/PlanATrip.js` (**new**) | destination search (reuse the geocoding-autocomplete pattern from `ExploreMap.js`), date-range form, results display, and the per-hotspot drill-down map (reuses `Components/SightingsMap.js` and `Components/SightingDetail.js`, same generation-counter remount pattern as `ExploreMap.js#wireMap()`) |

## 6. Build order

1. `app/dao/ebird.py#get_hotspots_near()` — new, tested against a live call
   once to confirm the response shape, then mocked in tests per
   [eBird API](../ebird-api.md)'s offline-tests rule.
2. `app/dao/inaturalist.py#get_species_counts()` — revive the removed
   function (see the note above); same tests it had before.
3. `app/models/trip.py` — response models.
4. `app/services/trip.py#plan_trip()` — the date-math + fan-out + life-list
   cross-reference.
5. `app/routers/trip.py` — wire the endpoint, point/add to
   `app/main.py`'s router includes.
6. Tests: hotspot DAO params, species-count date-window math (today's date
   minus a year, not just minus 365 days — leap years), the life-list
   cross-reference with and without `user_id`.
7. Frontend: `Dao/trip.js` → `Services/trip.js` → `Presenters/PlanATrip.js`
   → a **Plan a Trip** button on `Presenters/Home.js`'s header, alongside
   Life List / Add Observation.

## Related pages

- [Explore map](explore-map.md) — where the smaller, same-day version of
  this idea lived before this page existed
- [Add Observation](add-observation.md) — supplies the geocoding
  search pattern this reuses
- [eBird API](../ebird-api.md) — auth, endpoints, failure behavior
