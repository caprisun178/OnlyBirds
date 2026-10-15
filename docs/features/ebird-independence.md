# Running without eBird

> **Status:** Scoping, nothing built. Proposed 2026-10-15. This page answers
> one question: **can OnlyBirds work with no eBird API key, no eBird data
> request and no agreement with Cornell?** Short answer: yes, but not from
> hand-entered data alone. It needs three inputs together: our users' own
> sightings (including a curator logging real field trips), **open
> datasets** (GBIF's openly licensed copy of eBird, and iNaturalist), and
> **hotspots we compute ourselves**.
>
> This is the alternative to [Seeded sighting data](data-seeding.md), which
> keeps eBird but takes its data through Cornell's official bulk channel.
> The two share most of their tables (§6), so this isn't a fork in the
> design.

## 1. The manual-entry idea, and why it isn't enough alone

The proposal was: an admin account logs a year of sightings by hand and
adds hotspots manually, so the app has its own data and never touches
eBird.

**What's fine and what isn't:**

| | OK? | Why |
|---|---|---|
| Logging birds **you saw in the field**, one observation each | **Yes** | They're your own observations. That's what the app is for. |
| Adding hotspots you **visited or know** (a park, a marsh, a trail) | **Yes** | Place names and coordinates are facts, not eBird's database. |
| Re-typing sightings **seen on eBird's website** | **No** | It's still copying eBird's database, whether by script or by hand. eBird's [Terms of Use](https://www.birds.cornell.edu/home/ebird-api-terms-of-use/) forbid redistributing their data, and it would present other people's sightings as the admin's. |

**Why one person's year can't carry the app.** These are rough figures
(GBIF counts checked 2026-10-15):

| | Records |
|---|---|
| One dedicated birder, one year | a few thousand, mostly in one county |
| iNaturalist research-grade bird observations (all time) | ~35.6 million |
| eBird, 2024 alone | ~249 million |
| eBird, all time (on GBIF) | ~1.78 billion |

Hand-entered data works for **one home region**, a demo, and test fixtures.
Everywhere else, Explore Map, Plan a Trip's likely species, the
migration calendar and region checklists would be
empty or misleading. The curator's logging is still valuable, but as
**complete-checklist data for the home region** (§5), not as the backbone.

## 2. What eBird does for us today

Every eBird call in the backend (`app/dao/ebird.py`) and what replaces it:

| eBird function | Used by | Replacement | Quality vs. today |
|---|---|---|---|
| `get_nearby_bird_sightings()` (recent obs near a point) | Explore Map (`services/sightings.py`) | iNaturalist recent obs (already used) + our users' observations | **Worse.** Far fewer birds per area, especially outside cities. The main cost of this plan. |
| `get_hotspots_near()` | Plan a Trip (`services/trip.py`) | our `hotspots` table: computed + curated (§4) | Similar near people; thinner in remote areas |
| `get_historic_checklist()` (one call per day) | Plan a Trip, photo ID's "likely in this region" (`services/identify.py`) | local query over GBIF eBird data + iNat by distance and week of year | **Better speed** (local, no per-day calls); data lags about a year (§3) |
| `get_taxonomy()` | region checklists (`dao/region_repo.py`) | an open taxonomy loaded into `species` (§7) | Same, after one-time code mapping |
| `get_region_spplist()` | region checklists, exotic filtering | species list per region from local data | Same |
| `recent_obs_in_region()` | exotic-species lookback (`region_repo.py`) | local data, last N months | Lags; fine for this purpose |
| `get_region_children()` | Life List region picker (`services/life_list.py`) | our `regions` table (§7) | Same |
| `region_for_point()` | every logged observation, photo ID | point-in-polygon on boundary data (§7) | Same, and no network call |
| `notable_obs()` | nothing yet | n/a | Rare-bird alerts would need their own design |

## 3. Open data sources

| Source | What | License | Freshness | How we get it |
|---|---|---|---|---|
| **GBIF: EOD, eBird Observation Dataset** ([dataset](https://www.gbif.org/dataset/4fa7b334-ce0d-4e88-aaae-2e0c138d049e)) | eBird's records, published by Cornell to GBIF | **CC BY 4.0**: commercial use allowed, attribution required | Republished roughly yearly. Last published 2025-08-08; newest records are from 2024 | GBIF download API (free account), filtered by region, date, class Aves |
| **GBIF: iNaturalist research-grade** | iNat's verified observations | per record CC0 / CC BY / CC BY-NC | weekly | same download API |
| **iNaturalist API** (already used) | recent observations, taxa | non-commercial ToU; ~60 req/min, 10k/day | live | as today |
| **Our users** | `observations` | ours | live | as today |
| **Boundary data** | countries, states, counties | Natural Earth (public domain); US Census TIGER (public domain) | rarely changes | one-time import |
| **OpenStreetMap / PAD-US** | parks, reserves, protected areas for hotspot names | OSM: ODbL (attribution; share-alike for derived databases); PAD-US: public domain | rarely | one-time import per region |

**The GBIF eBird copy is the key finding.** It's eBird's own data, but
published under an open license, so using it needs no API key, no data
request and no agreement, just attribution. It's also the most likely path
to ever allowing commercial use, which neither the eBird API nor the EBD
allows (see [External services & API risk](../external-services.md)).

**Its limits:**

- **About a year behind.** It's for "what's usually here this week of the
  year", not "what's here today". As of this writing it holds nothing from
  2025.
- **No checklist or effort fields.** `eventID`, `samplingProtocol` and
  `samplingEffort` come back empty, so a true eBird-style frequency ("on X%
  of complete checklists") can't be computed from it. We can rank species
  by **share of records** per place and week, which is good enough for
  "likely species" ordering but over-weights conspicuous, popular birds.
- **Probably excludes sensitive species and some locations.** Verify on the
  first import; don't assume.
- **Attribution must be visible** wherever it's shown: "eBird Observation
  Dataset, Cornell Lab of Ornithology, via GBIF.org" plus the download DOI.

**Checked live (2026-10-15):** GBIF's search API returned 108,855 EOD
records within 10 km of Durham, NC in May, with per-species counts in one
request (`geoDistance=35.99,-78.90,10km&month=5&facet=speciesKey`). The
data supports the queries Plan a Trip needs. We'd still import it rather
than call GBIF per request, for speed and to avoid leaning on their API.

## 4. Hotspots

Two kinds, one table:

1. **Computed.** Cluster sighting locations (our users + iNat + EOD) with
   PostGIS `ST_ClusterDBSCAN` (e.g. points within ~300 m, at least N
   distinct observation days). Each cluster becomes a candidate hotspot at
   its centroid. Name it from the nearest OSM / PAD-US park or reserve
   polygon it falls inside, or failing that, the most common EOD `locality`
   string in the cluster (EOD is CC BY, so reusing the name with
   attribution is fine). Recompute after each import.
2. **Curated.** An admin adds, renames, merges or hides hotspots by hand
   (a park entrance, a known marsh). Curated rows are never overwritten by
   recomputation; a computed cluster that overlaps a curated hotspot
   attaches to it instead of creating a duplicate.

A hotspot is shown to users when it's curated, or when it's computed and
passes a threshold (e.g. 20+ distinct observation days, 15+ species), so
one person's backyard doesn't become a public hotspot. **Privacy:** never
create a computed hotspot from a single user's observations.

## 5. Curator field logging (the "year of data")

Still worth doing, with a few rules so the data is honest and more useful
than plain sightings:

- **Real field sightings only**, logged from a normal account with a
  `curator` role (not a hidden "system" user), so the sightings are
  attributable and appear in that person's own life list like anyone
  else's.
- **Log complete checklists:** every species seen on an outing, with start
  time, duration and distance. That gives the home region the effort data
  EOD lacks (§3), so its frequencies can be true "% of checklists" ones.
  This needs a small `checklists` concept (§6). Today an observation is a
  single bird with no outing grouping.
- **Curator observations count normally** for that person's life list.
  Whether they count for [competitions](competitions.md) is an open
  question (§10).

## 6. Database changes (SQL)

Builds on the tables proposed in [Seeded sighting data](data-seeding.md)
(`seed_datasets`, `external_sightings`, `species_frequency`). Only the
additions are shown.

```sql
-- 00NN_ebird_independence.sql  (next free number)

-- new allowed sources for the data-seeding tables
alter table seed_datasets drop constraint seed_datasets_source_check;
alter table seed_datasets add constraint seed_datasets_source_check
    check (source in ('ebird_ebd', 'gbif_inat', 'gbif_ebird_eod', 'ebird_taxonomy',
                      'open_taxonomy', 'boundaries', 'osm_places'));
alter table external_sightings drop constraint external_sightings_source_check;
alter table external_sightings add constraint external_sightings_source_check
    check (source in ('ebird', 'inat', 'gbif_ebird'));

-- frequency basis: 'checklists' (true % of checklists) vs 'records' (share of records)
alter table species_frequency add column basis text not null default 'checklists'
    check (basis in ('checklists', 'records'));

create table regions (
    code         text primary key,          -- eBird-style codes kept: 'US', 'US-NC', 'US-NC-063'
    name         text not null,
    region_type  text not null check (region_type in ('country', 'subnational1', 'subnational2')),
    parent_code  text references regions(code),
    geom         geography(multipolygon, 4326) not null,
    dataset_id   uuid references seed_datasets(id)
);
create index regions_geom_idx on regions using gist (geom);

create table hotspots (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    lat           double precision not null,
    lng           double precision not null,
    geom          geography(point, 4326) not null,
    region_code   text references regions(code),
    origin        text not null check (origin in ('computed', 'curated')),
    hidden        boolean not null default false,     -- curator can suppress
    obs_days      integer,                            -- computed stats, refreshed per import
    species_count integer,
    name_source   text,                               -- 'osm' | 'padus' | 'eod_locality' | 'curator'
    created_by    uuid references users(id),          -- curated only
    updated_at    timestamptz not null default now()
);
create index hotspots_geom_idx on hotspots using gist (geom);

-- optional, for §5: group a user's observations into a complete checklist
create table checklists (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references users(id),
    hotspot_id   uuid references hotspots(id),
    started_at   timestamptz not null,
    duration_min integer,
    distance_km  numeric(6,2),
    complete     boolean not null default true        -- "I reported everything I identified"
);
alter table observations add column checklist_id uuid references checklists(id);
```

(The `users.role` column for `curator` follows whatever the admin page
work, on `working/sparisi/AdminPage`, settles on.)

## 7. Regions and taxonomy

**Regions.** `region_for_point()` is called on every logged observation.
Replace it with a point-in-polygon lookup on `regions`: Natural Earth for
countries and states/provinces, US Census TIGER for US counties. Keep
**eBird-style codes** (`US-NC-063` = ISO 3166-2 + county FIPS) so existing
rows and code that store region codes don't change. Outside the US,
county-level (`subnational2`) coverage needs a source per country; start
US-only, matching the current user base.

**Taxonomy.** The app's own convention is already to key on
`scientific_name`, but eBird **species codes** (e.g. `sandcran`) are baked
into `app/data/birds.py`, `exotic_exclusions.py` and `species.ebird_code`.
Options:

1. **iNaturalist taxonomy** (already called, has `extinct`, common names
   in many languages). Non-commercial terms, like the rest of iNat.
2. **GBIF Backbone Taxonomy:** open, matches GBIF records directly.
3. **Clements / IOC checklists:** the standard bird lists. Check each
   one's current license before relying on it.

Recommended: **GBIF Backbone** as the key for imported records (it's what
GBIF data already uses), with a one-time mapping table from existing eBird
codes to scientific names so the hard-coded code lists keep working.

## 8. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| scripts | `backend/scripts/import_gbif.py` (from [data-seeding](data-seeding.md), **extend**) | also accept the EOD dataset key; tag `source = 'gbif_ebird'`; compute `species_frequency` with `basis = 'records'` |
| scripts | `backend/scripts/import_boundaries.py` (**new**) | load Natural Earth + TIGER into `regions` |
| scripts | `backend/scripts/compute_hotspots.py` (**new**) | cluster, name from OSM/PAD-US/EOD locality, merge with curated rows |
| `dao/` | `app/dao/region_repo.py` (**extend**) | local region lookups and species lists instead of `ebird.*` |
| `dao/` | `app/dao/hotspot_repo.py` (**new**) | near-point queries; curator CRUD |
| `services/` | `trip.py`, `sightings.py`, `identify.py`, `life_list.py`, `observation.py` | swap each `ebird.*` call per §2's table, behind one setting (below) |
| admin UI | admin page (**extend**) | hotspot curation: add / rename / merge / hide |
| frontend | wherever EOD-derived data shows | "eBird Observation Dataset via GBIF" attribution + "data through <year>" note |

**One switch, not a rewrite.** Add a `DATA_SOURCE_MODE` setting
(`ebird` | `open`) and route each §2 call through it, so both paths run
side by side, can be compared on the same screen, and eBird can be turned
off in one place.

## 9. Build order

1. **Boundaries + local `region_for_point()`.** Small, removes an eBird
   call from every observation, and nothing else depends on it.
2. **GBIF import for one region** (home region): EOD + iNat. Measure rows
   and disk (see [data-seeding §3 sizing](data-seeding.md#sizing)).
3. **Plan a Trip on local data** for that region (likely species by week,
   historic sightings). Compare side by side with the eBird version.
4. **Computed hotspots** for that region; curator tools on the admin page.
5. **Taxonomy mapping**, then region checklists off eBird.
6. **Curator checklists** (§5), so the home region gets true frequencies.
7. **Explore Map** on iNat + our users only; decide if the drop in recent
   sightings is acceptable (§10).
8. Flip `DATA_SOURCE_MODE=open` in dev, then production; remove the eBird
   key last.

## 10. Open questions

1. **Is thinner "recent sightings" acceptable?** Explore Map is the one
   screen that gets clearly worse: open data is about a year behind, and
   iNat is much sparser than eBird for recent birds.
2. **Commercial plans?** EOD is CC BY (commercial OK), but iNat is
   non-commercial. A commercial app would need to drop or license iNat.
3. **Do curator observations count in competitions?** Recommended: yes for
   the curator's own life list, excluded from competitions while the
   curator is also the admin.
4. **Which home region first?** Wherever the curator birds (NC?).
5. **Keep both modes long-term, or remove eBird entirely?** Keeping the
   switch costs little and keeps the faster, fresher eBird path available
   if Cornell grants access, e.g. the pending Status & Trends request for
   the migration calendar.

## 11. Related pages

- [Seeded sighting data](data-seeding.md): the eBird-bulk alternative; shared tables
- [External services & API risk](../external-services.md): why this exists
- [eBird API](../ebird-api.md): what we use today
- [Plan a trip](plan-a-trip.md), [Explore map](explore-map.md), [Life List page](life-list.md): the screens that change
- Migration calendar (`docs/features/migration-calendar.md`, on `working/sparisi/migrationCalendar`): frequencies by week
- [Database & migrations](database.md)
