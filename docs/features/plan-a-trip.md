# Plan a trip

> **Status:** Planned. Standalone feature — originally considered as a
> subsection of [Explore map](explore-map.md)'s Trip Planning box, but
> deliberately kept separate: it answers a different question ("I'm going
> somewhere on specific dates — what should I expect and where should I go")
> than Explore Map's "what's around here right now." See that page's history
> for the earlier, smaller version this grew out of (built, then reverted,
> while this page didn't exist yet).

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

`start_date`/`end_date` are `YYYY-MM-DD`, the *actual* trip dates (this
year or any year) — the service translates them to the equivalent window
one year earlier before querying iNaturalist; the caller never has to do
that math. `user_id` is optional: omit it and `new_for_you` on every
species is just omitted rather than guessed at.

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
| `dao/` | `app/dao/ebird.py` (extend) | `get_hotspots_near(lat, lng, radius_km)` — `GET /ref/hotspot/geo` |
| `dao/` | `app/dao/inaturalist.py` (extend) | `get_species_counts(lat, lng, radius_km, d1, d2)` — `GET /observations/species_counts` (this exact function existed once already, for Explore Map's now-removed seasonal box — same shape, revived here) |
| `models/` | `app/models/trip.py` (**new**) | `Hotspot`, `LikelySpecies`, `TripPlan` |
| `services/` | `app/services/trip.py` (**new**) | date-range → last-year window; fan out to hotspots + species_counts concurrently; cross-reference the caller's life list for `new_for_you` |
| `routers/` | `app/routers/trip.py` (**new**) | `GET /trip/plan` |
| `Dao/` | `frontend/src/Dao/trip.js` (**new**) | raw `GET /trip/plan` call |
| `Services/` | `frontend/src/Services/trip.js` (**new**) | param shaping, defaults |
| `Presenters/` | `Presenters/PlanATrip.js` (**new**) | destination search (reuse the geocoding-autocomplete pattern from `ExploreMap.js`), date-range form, results display |

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
