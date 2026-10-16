# Seeded sighting data (eBird + iNaturalist)

> **Status:** Scoping — nothing built. Proposed 2026-10-09 as a hedge
> against the API risks in
> [External services & API risk](../external-services.md): keep our own
> copy of eBird and iNaturalist sightings, so the app keeps working (and
> gets faster) even if live API access is throttled or revoked.
> **One rule shapes everything below:** the copy comes from each
> provider's **official bulk-data channel**, never from paging through
> their APIs. Bulk-copying through the API is precisely the "abuse" that
> gets keys suspended.

## 1. What you're building

A local, regularly refreshed store of historical bird sightings, imported
offline from:

- **eBird Basic Dataset (EBD):** Cornell's full eBird export, requested
  through a short form on eBird (typically approved within ~7 days),
  refreshed **monthly**, free for non-commercial use. It can be requested
  as a custom subset (by country/state, species, date range), so we only
  take what we need.
- **iNaturalist via GBIF:** iNaturalist publishes its *research-grade*
  observations with open licenses (CC0, CC BY, CC BY-NC) to
  [GBIF](https://www.gbif.org) **weekly**. GBIF offers filtered downloads
  (birds only, by region and date) as a Darwin Core archive, each with a
  citable DOI. Photo metadata and licenses are also available from the
  [iNaturalist Open Data](https://registry.opendata.aws/inaturalist-open-data)
  set on AWS.

The app then reads **historical** questions from our own database, and
uses the live APIs only for what's genuinely live:

| Screen / question | Today | With seeded data |
|---|---|---|
| Plan a Trip: "what was seen here around these dates last year" | live: one eBird call **per day** in the window plus iNaturalist (~7–8 s first tap) | **local query, well under 1 s** |
| Plan a Trip: likely species | live iNaturalist species counts | local **frequency by week** (the same idea as eBird's bar charts), from both sources |
| Explore Map: sightings in the last 7–30 days | live | still live, with **seeded data as fallback** if a provider is down or blocks us (labelled "as of <date>") |
| Life List region checklists, taxonomy | live eBird (cached in memory) | local, from the EBD + the published eBird taxonomy |
| Competitions, Life List totals | the user's own observations only | **unchanged.** Seeded data never counts as anyone's observation |

### What it does *not* do

- **It doesn't make us independent of the live APIs for recent sightings.**
  EBD is monthly and GBIF weekly, so "what's been seen this week" still
  needs the live APIs.
- **It doesn't remove the non-commercial restriction.** Both bulk channels
  carry the same non-commercial terms as the APIs.
- **It never goes into `observations`.** That table is users' own logging;
  seeded records live in their own table.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| eBird sightings (raw records) | EBD custom download (tab-separated text), via data request | `external_sightings` (`source = 'ebird'`); **raw records are display-restricted**, see [§2.1](#21-terms-what-we-may-store-and-show) |
| eBird-derived frequencies | computed by us from complete EBD checklists | `species_frequency` |
| eBird hotspots | the EBD (locality IDs + names) and the hotspot list | `external_sightings.ebird_loc_id`, `hotspots` |
| eBird taxonomy | the yearly published eBird/Clements taxonomy file | `species` (fills `ebird_code`, family, order) |
| iNaturalist sightings | GBIF occurrence download, filtered to the iNaturalist dataset, class Aves, our regions | `external_sightings` (`source = 'inat'`), with per-record license + rights holder |
| iNaturalist photo URLs + licenses | the GBIF multimedia extension / iNaturalist Open Data | `external_sightings.photo_*` (open-licensed photos only) |
| What was imported, when, under which terms | the import scripts | `seed_datasets` |

### 2.1 Terms: what we may store and show

| | eBird (EBD) | iNaturalist (via GBIF) |
|---|---|---|
| Getting it | data-request form; Cornell learns how it'll be used | public download, cite the DOI |
| Commercial use | **prohibited** without written permission | records licensed CC BY-NC are non-commercial |
| Storing a copy | yes, that's the purpose of the EBD | yes |
| Showing **individual records** publicly | **Unclear, so ask first.** The [Data Access Terms](https://www.birds.cornell.edu/home/ebird-data-access-terms-of-use) forbid publicly distributing eBird data "in their original format, either whole or in part," and limit use to research and education | yes, with attribution to the observer and the record's license |
| Showing **derived data** (frequencies, species lists, counts per hotspot) | allowed under the same terms of use | yes |
| Attribution | "eBird Basic Dataset, Cornell Lab of Ornithology" + version | per-record observer + license; cite the GBIF download DOI |

**So the design leans on derived data for eBird.** "Likely species" and
"what was seen here last year" are built from **frequencies and species
lists**, not by publishing individual eBird checklists. Whether we may
show individual eBird records (e.g. a pin per sighting on the Plan a Trip
hotspot map, as the live API version does today) is **the first question
to put to Cornell** in the data request. Until they answer, show eBird as
aggregates and iNaturalist as individual records.

## 3. Database changes (SQL)

```sql
-- 00NN_seeded_sightings.sql  (next free number)

-- one row per import run, for provenance, citation and rollback
create table seed_datasets (
    id            uuid primary key default gen_random_uuid(),
    source        text not null check (source in ('ebird_ebd', 'gbif_inat', 'ebird_taxonomy')),
    version       text not null,      -- EBD release e.g. 'relSep-2026'; GBIF download DOI; taxonomy year
    scope         jsonb not null,     -- {"regions": ["US-WA"], "from": "2021-01-01", "to": "2026-08-31"}
    row_count     integer,
    citation      text not null,      -- the attribution string to display
    imported_at   timestamptz not null default now(),
    superseded_at timestamptz         -- set when a newer import replaces it
);

create table external_sightings (
    source             text not null check (source in ('ebird', 'inat')),
    source_record_id   text not null,          -- EBD GLOBAL UNIQUE IDENTIFIER / GBIF gbifID
    dataset_id         uuid not null references seed_datasets(id) on delete cascade,
    scientific_name    text not null,
    common_name        text,
    observed_on        date not null,
    observed_at        timestamptz,            -- when a time is known
    lat                double precision not null,
    lng                double precision not null,
    geom               geography(point, 4326) not null,
    region             text,                   -- eBird region code, e.g. 'US-WA-033'
    locality           text,
    ebird_loc_id       text,                   -- hotspot / locality id (eBird)
    checklist_id       text,                   -- eBird sampling event id
    count              integer,                -- null = 'X' (present, not counted)
    coords_obscured    boolean not null default false,  -- iNat obscured / sensitive species
    record_license     text,                   -- iNat: CC0 / CC-BY / CC-BY-NC
    observer           text,                   -- display attribution (iNat); not shown for eBird until cleared
    photo_url          text,                   -- open-licensed photos only
    photo_license      text,
    photo_attribution  text,
    primary key (source, source_record_id)
);
create index external_sightings_geom_idx    on external_sightings using gist (geom);
create index external_sightings_species_idx on external_sightings (scientific_name, observed_on);
create index external_sightings_loc_idx     on external_sightings (ebird_loc_id, observed_on);
create index external_sightings_region_idx  on external_sightings (region, observed_on);

-- derived: how often each species is reported, per place per week of year
-- (the same idea as eBird's bar charts; computed only from *complete* checklists)
create table species_frequency (
    scope_kind        text not null check (scope_kind in ('region', 'hotspot')),
    scope_id          text not null,           -- region code or ebird_loc_id
    week_of_year      smallint not null check (week_of_year between 1 and 53),
    scientific_name   text not null,
    checklists_with   integer not null,        -- complete checklists reporting it
    checklists_total  integer not null,        -- all complete checklists in that scope + week
    dataset_id        uuid not null references seed_datasets(id) on delete cascade,
    primary key (scope_kind, scope_id, week_of_year, scientific_name)
);
```

| Table | Why it exists |
|---|---|
| `seed_datasets` | Provenance: which release each row came from, the citation to show, and a way to roll back an import cleanly (`on delete cascade`). |
| `external_sightings` | The local copy, kept separate from `observations` so it can never count toward a user's life list or competitions. PostGIS `geom` for "near here" queries. Keyed on the source's own record ID, so re-imports upsert instead of duplicating. |
| `species_frequency` | The derived view that powers "likely species" and is safe to display under eBird's terms. Precomputed at import time, so the app reads it instantly. |

This replaces the planned `sighting_cache` table in
[Explore map](explore-map.md) for historical data. The short-lived cache
of *live* results is still useful for the last 7–30 days.

### Sizing

Storage depends entirely on scope, so **start with one or two
regions** (e.g. Washington State) and the last 3–5 years. Run a trial
import and measure before committing; don't estimate. A busy US state
can produce millions of eBird records per year. The full global EBD is
hundreds of GB uncompressed and is not a goal. On the
[self-hosted server](../production-environment.md) (80 GB disk), plan for a
separate attached volume once more than a few regions are seeded.

## 4. API endpoints

No new public endpoints are needed. Existing endpoints change where they
read from:

| Endpoint | Change |
|---|---|
| `GET /trip/plan` | likely species from `species_frequency` (by week of the trip dates) + iNat records; live API only if the area isn't seeded |
| `GET /trip/hotspot-sightings` | local query by `ebird_loc_id` / distance + date window; replaces the day-by-day eBird calls |
| `GET /sightings/nearby` (Explore Map) | still live for recent windows; on a provider error or 429, fall back to seeded data and say "showing data as of <date>" |
| `GET /life-list/...` region checklist | species list per region from local data / `species_frequency` |
| *(admin)* `GET /admin/seed-datasets` | what's loaded, version, row counts, age, so a stale import is visible |

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| scripts | `backend/scripts/import_ebd.py` (**new**) | stream the EBD text file (it's large, so never load it whole); keep approved records; `COPY` into a staging table; upsert into `external_sightings`; compute `species_frequency` from complete checklists; record a `seed_datasets` row |
| scripts | `backend/scripts/import_gbif.py` (**new**) | read a GBIF Darwin Core archive (occurrence + multimedia), keep iNaturalist bird records with an open license, keep only open-licensed photos; upsert; record DOI + citation |
| scripts | `backend/scripts/import_taxonomy.py` (**new**) | load the yearly eBird taxonomy into `species` |
| `dao/` | `app/dao/seeded_repo.py` (**new**) | read queries: near a point + date window, by hotspot, frequencies by week |
| `services/` | `trip.py`, `sightings.py`, `life_list.py` (extend) | prefer seeded data for historical questions; live API for recent; fallback on provider failure |
| frontend | `SightingDetail.js` etc. (extend) | attribution per record (iNat observer + license) and dataset citation; an "as of <date>" note when showing fallback data |

Imports run **offline, as admin jobs**, never in a user request: on a
laptop or a scheduled job on the server, then upserted into production.

## 6. Build order

1. **Submit the eBird data request** describing OnlyBirds and asking the
   display question in [§2.1](#21-terms-what-we-may-store-and-show)
   (approval takes about a week, so start this first).
2. Migration; `import_taxonomy.py` (smallest, immediately useful).
3. `import_gbif.py` for one region; measure rows and disk.
4. Switch `GET /trip/hotspot-sightings` to local data for seeded regions:
   the biggest speed win, and it proves the path.
5. Once the EBD arrives: `import_ebd.py` + `species_frequency` for the
   same region; switch Plan a Trip's likely species.
6. Fallback path for Explore Map; "as of" labelling; admin dataset page.
7. Monthly refresh routine (new EBD release on the 15th; fresh GBIF
   download), with `superseded_at` and cleanup of old datasets.
8. Add regions one at a time, measuring each.

## 7. Related pages

- [External services & API risk](../external-services.md): why this exists
- [Plan a trip](plan-a-trip.md): the biggest beneficiary
- [Explore map](explore-map.md): fallback for live sightings; the `sighting_cache` this partly replaces
- [Life List page](life-list.md): region checklists
- [Production environment (self-hosted)](../production-environment.md): disk sizing
- [Database & migrations](database.md)

## 8. Open questions

1. **Which regions first?** Recommended: wherever the first users are
   (Washington?), then expand.
2. **How many years back?** Recommended: 3–5 years for "same dates last
   year(s)"; more only if a feature needs it.
3. **May we show individual eBird records?** Ask Cornell in the data
   request. Until then, aggregates only for eBird.
4. **Refresh cadence:** monthly (matching EBD) is the natural default.
5. **Who runs imports**, and from where (laptop vs scheduled job on the
   server)?
