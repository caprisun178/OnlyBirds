# Explore map

> **Status:** Planned. Build after [Add Observation](add-observation.md) — it
> queries `observations.geom`, which that feature adds, and needs the PostGIS
> extension from the baseline.

## 1. What you're building

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
| `Presenters/` | `Presenters/ExploreMap.jsx` (**new**) | map camera, filters, pin selection, tap-to-log hand-off |
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
   `Presenters/ExploreMap.jsx` → map components + `AttributionFooter`.

## Related pages

- [Add Observation](add-observation.md) — supplies `observations.geom`; tap-to-log lands here
- [User profiles](user-profiles.md) — supplies the starting map centre
- [Bird information page](bird-info.md) — sighting popups link here
- [Pinned birds](pinned-birds.md) — pin a species straight from a popup
- [Database & migrations](database.md)
- [eBird API](../ebird-api.md) — auth, endpoints, failure behavior
