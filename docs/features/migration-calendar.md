# Migration calendar

> **Status:** Planned, scoped — docs only, nothing built yet. The data source
> was checked against the live iNaturalist API on 2026-10-13 (§1, "Why this
> works"). The open questions at the end need answers before work starts.

## 1. What you're building

A page that answers **"what birds should be passing through here right
now, and when do the others show up?"** for any location the user picks.

Two views of the same data:

1. **This week** (the default). Three short lists for the user's location:
   - **Arriving:** migrants whose numbers are rising into this week.
   - **Peak now:** migrants at or near their high point for the year.
   - **Leaving:** migrants whose numbers are dropping off.

   Each row has the bird's photo, its pattern ("passes through", "summer
   visitor", "winter visitor") and a small 52-week bar strip. Year-round
   residents are left out; they don't migrate, and they would bury the
   interesting birds.
2. **Full year.** A species × week grid in the style of eBird's bar charts:
   one row per species, 52 week columns, bar thickness = how common it is
   that week. Filter by pattern (passage / summer / winter / resident) and,
   for a signed-in user, by **"not on my life list"**, which turns the
   calendar into a "when to go looking for a lifer" planner.

Every species row links to the [Bird information page](bird-info.md) and
has the existing [Pinned birds](pinned-birds.md) `PinButton`. Pinning a
bird that's arriving next week is the natural next step, and that feature
already handles the alerts.

**Choosing a location:** the same place search as Add Observation and
Explore Map (`GET /geocode/search`), plus "Use my location" (browser
geolocation) and the existing recent-location chips
(`Services/recentLocations.js`). The last location used is remembered in
`localStorage` so returning visitors land straight on their calendar.

### Why this works: iNaturalist, all years, by week

eBird's real frequency data (Status & Trends, and the bar charts on
ebird.org) **isn't reachable with our API key**. [Plan a trip](plan-a-trip.md)
and [Bird info](bird-info.md) both ran into this. Plan a trip settled for
"one year of iNaturalist data, last year only".

iNaturalist turns out to support more than that. `GET /observations/species_counts`
and `GET /observations` accept a **`week`** (1–53) or **`month`** filter
that applies **across every year at once**. Combined with point + radius,
that gives a multi-year, week-by-week species list for any location, from
the same keyless API `app/dao/inaturalist.py` already calls.

Checked live, 40 km around Raleigh, research-grade bird observations, by
week of year:

| Species | Weeks with observations | Pattern it shows |
|---|---|---|
| Blackpoll Warbler | 18–21 and 40–45 only | **passes through** (spring and fall), absent summer and winter |
| White-throated Sparrow | 42 → 17 (wrapping through winter), near-zero 18–41 | **winter visitor** |
| Chimney Swift | 15–41 | **summer visitor** |

Those are the textbook patterns for these species in central North
Carolina, from raw counts with no tuning, which is what makes the feature
viable.

### Normalizing for effort

Raw counts mostly measure **how many people were out**: Raleigh had 2,366
bird observations in week 19 (May) but only 973 in week 28 (July). A
species seen 20 times in each of those weeks is **more than twice as
common** in July. So each species' weekly count is divided by that week's
**total bird observations** (one extra `GET /observations?…&week=N&per_page=0`
call per week, which returns just `total_results`). The calendar shows
that **share**, never raw counts.

### Classifying a species

Computed per species from its 52 weekly shares, after a 3-week rolling
mean to smooth noise. A week counts as "present" when the share is at
least 15% of that species' own peak.

| Pattern | Rule (starting point; tune against known species) |
|---|---|
| **Resident** | present in ≥ 44 of 52 weeks |
| **Summer visitor** | present in most of weeks 22–30 (Jun–Jul), absent in most of weeks 1–8 (Jan–Feb) |
| **Winter visitor** | present in most of weeks 1–8, absent in most of weeks 22–30 |
| **Passes through** | absent in most of both weeks 1–8 *and* 22–30, present in a spring block (weeks 10–23) and/or a fall block (weeks 32–48) |
| **Irregular** | anything else, or fewer than **10 total observations** for the year (too little data to call). Shown in the full-year grid only, not in "This week" |

Southern-hemisphere locations flip summer and winter. The rule set takes
the hemisphere from the location's latitude and swaps the two blocks.

**Arriving / peak / leaving** (migrants only, i.e. everything except
residents and irregulars), for the current week *w*:

- **Peak now:** share at *w* ≥ 70% of the species' peak share.
- **Arriving:** share at *w* ≥ 15% of peak and rising (share at *w* > share at *w*−2), not already peak.
- **Leaving:** share at *w* ≥ 15% of peak and falling, not already peak.

### Honest limits worth stating in the UI

- **iNaturalist is photo-based.** Birds that are hard to photograph
  (nocturnal migrants, distant shorebirds, birds identified only by song)
  are under-represented compared with eBird checklists. A small line under
  the calendar: "Based on iNaturalist photo observations, all years; birds
  that are hard to photograph may appear rarer than they are."
- **Data-poor areas.** Rural areas can have very few observations. When a
  location's yearly total is under **2,000 bird observations**, show a
  "Not much data here yet, so this calendar may be incomplete" banner. If
  it's under 300, show a "try a larger radius or a nearby city" message
  instead of the calendar.
- **It's typical timing, not a forecast.** Weather shifts migration by
  days to weeks each year. The copy says "usually passes through", not
  "will arrive".

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Species × week observation counts for a location | iNaturalist `GET /observations/species_counts?lat=&lng=&radius=&taxon_id=3&quality_grade=research&week=N&per_page=500`, once per week (53 calls) | `migration_calendar_counts` |
| Total bird observations per week | iNaturalist `GET /observations?…&week=N&per_page=0` → `total_results` (53 calls) | `migration_calendar_weeks` |
| Species identity (scientific + common name, iNat taxon id) | the same `species_counts` response | `migration_calendar_counts` |
| Pattern + arriving/peak/leaving | **computed** from the stored counts at read time (cheap: a few hundred species × 52 numbers) | not stored |
| Species photos | existing `bird_photos.get_stock_photo()` (Wikimedia Commons, cached) | its existing cache |
| "Not on my life list" | existing `life_list` service | not stored |
| The user's chosen location | the user | `localStorage` only (no account needed) |

**Grid cells, so locations share one cache.** A location snaps to a
**0.5° × 0.5° grid cell** (about 55 × 45 km in the mid-US), and the calendar is
built for that cell's centre with a **40 km radius**. Everyone in the same
cell shares one calendar, so iNaturalist is called once per cell, not once
per user.

**Cost of building a cell:** ~106 iNaturalist requests. iNaturalist asks
API clients to stay around 1 request/second, so a cold cell takes **about
2 minutes**. It's built in the background (§4) and kept. **Refresh:** a
cell older than **90 days** is rebuilt in the background the next time
someone views it, and the stale version is served meanwhile. Seasonal
patterns barely move within a year; 90 days just picks up new observations.

## 3. Database changes (SQL)

```sql
-- 0007_migration_calendar.sql   (renumber if bulk import's 0007 lands first)

create table if not exists migration_calendars (
    cell_id      text primary key,                -- 'lat:lng' of the cell's SW corner, e.g. '35.5:-79.0'
    center_lat   double precision not null,
    center_lng   double precision not null,
    radius_km    int not null default 40,
    status       text not null default 'building'
        check (status in ('building', 'ready', 'failed')),
    total_obs    int,                             -- whole-year bird observations; drives the data-poor banners
    built_at     timestamptz,                     -- null until the first successful build
    updated_at   timestamptz not null default now()
);

create table if not exists migration_calendar_weeks (
    cell_id      text not null references migration_calendars (cell_id) on delete cascade,
    week         smallint not null check (week between 1 and 53),
    total_obs    int not null,                    -- all bird observations that week, the share denominator
    primary key (cell_id, week)
);

create table if not exists migration_calendar_counts (
    cell_id          text not null references migration_calendars (cell_id) on delete cascade,
    scientific_name  text not null,               -- the app's species identity (same as bird-info / pins)
    common_name      text,
    inat_taxon_id    int,
    week             smallint not null check (week between 1 and 53),
    obs_count        int not null,
    primary key (cell_id, scientific_name, week)
);
```

| Table | Why |
|---|---|
| `migration_calendars` | One row per grid cell: where it is, whether it's built, how much data it had. `status = 'building'` is how a second visitor knows a build is already running, so it isn't started twice. |
| `migration_calendar_weeks` | The effort denominator (§1, "Normalizing for effort"). |
| `migration_calendar_counts` | The raw weekly counts. Only non-zero weeks are stored, which is a few thousand rows per cell. |

Patterns and arriving/peak/leaving are **not stored**. They're a pure
function of the counts, so tuning the thresholds later needs no migration
and no rebuild.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/migration/calendar?lat=&lng=` | Snaps to the cell. **Ready:** `200` with the full-year data (below). **Not built yet:** starts a background build, returns `202` `{status: "building", cell_id}`; the frontend polls every 10 s. **Stale (> 90 days):** `200` with the old data plus `refreshing: true`, and a background rebuild starts. |
| `GET` | `/migration/now?lat=&lng=&week=&user_id=` | The "This week" view: `{arriving, peak, leaving}` lists. `week` defaults to the current week. `user_id` (optional) adds `on_life_list` to each species. Same `202` behavior when the cell isn't built. |

```json
// GET /migration/calendar?lat=35.78&lng=-78.64   (200)
{
  "cell_id": "35.5:-79.0",
  "status": "ready",
  "built_at": "2026-10-13T15:02:11Z",
  "refreshing": false,
  "data_quality": "good",            // "good" | "limited" (< 2,000 obs/yr) | "insufficient" (< 300)
  "species": [
    {
      "scientific_name": "Setophaga striata",
      "common_name": "Blackpoll Warbler",
      "pattern": "passage",          // resident | summer | winter | passage | irregular
      "weekly": [0, 0, 0, …, 0.42, 1.0, 0.55, …],   // 52 values, share relative to this species' own peak (0–1)
      "photo_url": "https://upload.wikimedia.org/…",
      "photo_attribution": "…"
    }
  ]
}
```

`weekly` is **relative to each species' own peak**, which is what a bar
chart row needs. Absolute shares aren't exposed; they mean little to a
user.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/inaturalist.py` (extend) | `get_species_counts()` gains an optional `week`; new `count_observations(lat, lng, radius_km, week)` → `total_results`. Both raw calls only. |
| `dao/` | `app/dao/migration_repo.py` (**new**) | Read/write the three tables (Postgres via `db.py`, in-memory fallback like the other repos). `claim_build(cell_id)` flips a cell to `building` **only if** it isn't already, so concurrent visitors can't start two builds. |
| `services/` | `app/services/migration.py` (**new**) | `cell_for(lat, lng)`; `build_cell(cell_id)` (the ~106 paced calls, 1/s, then one write; marks `failed` on error so the next visit retries); `classify(weekly_counts, weekly_totals, hemisphere)` and `this_week(...)`, **pure functions** that hold all the §1 rules, so they're unit-testable with plain lists. |
| `routers/` | `app/routers/migration.py` (**new**) | The two endpoints; starts `build_cell` with FastAPI `BackgroundTasks` |
| `models/` | `app/models/migration.py` (**new**) | response models |
| `Dao/` | `frontend/src/Dao/migration.js` (**new**) | raw calls |
| `Services/` | `frontend/src/Services/migration.js` (**new**) | polling while `building`; current week-of-year; remembering the last location |
| `Presenters/` | `frontend/src/Presenters/MigrationCalendar.js` (**new**) | location picker → "This week" ↔ "Full year" tabs; building and data-quality states |
| `Components/` | `frontend/src/Components/MigrationBarStrip.js` (**new**) | one species' 52-week bar row (used in both views); reuses `PinButton` |

Entry point: a "Migration" link in the `Home` header next to Life List,
registered in `preview.js`'s route table.

!!! note "Background builds and Render's free tier"
    `BackgroundTasks` runs inside the web process. If Render puts the
    service to sleep mid-build (15 minutes idle, which is unlikely while
    someone's page is polling every 10 s), the cell is left in `building`.
    `claim_build()` therefore treats a `building` row whose `updated_at` is
    older than 10 minutes as abandoned and lets a new build claim it.

## 6. Build order

1. **Validate the classifier before building any UI.** Write a throwaway
   script that pulls three or four real cells (Raleigh, a coastal cell
   like Wilmington, a data-poor rural cell, one in another region) and
   runs `classify()` on them. Check the result against species whose
   pattern is known locally: the three in §1, plus a resident (Northern
   Cardinal) and a few borderline ones (American Robin and Eastern Bluebird,
   partly migratory). Tune §1's thresholds until they agree. Record the
   result in this page, the way bird-id.md §9 records its live runs.
2. `classify()` and `this_week()` with unit tests built from synthetic
   weekly lists (a clean resident, a clean passage migrant, a winter
   visitor wrapping round week 53→1, a southern-hemisphere summer
   visitor, too-little-data → irregular).
3. Migration `0007_migration_calendar.sql` + `migration_repo.py`
   (+ test: `claim_build` refuses a fresh `building` row and accepts an
   abandoned one).
4. `inaturalist.py` extensions + `build_cell()` (tests mock the DAO; no
   live calls, per the offline-tests rule).
5. Router + models; tests for `200` / `202` / stale-`refreshing`.
6. Frontend: Dao → Services → `MigrationBarStrip` → `MigrationCalendar`
   presenter → Home link.
7. Live run: build two real cells end to end on the deployed service and
   note the measured build time.

## Open questions

1. ~~**Week or month?**~~ **Decided (2026-10-13): weekly.** It matches
   eBird's bar charts, and short passages like Blackpoll Warbler's ~4-week
   window stay visible. It costs ~106 calls (about 2 minutes) per cold cell,
   which the background build and shared cache absorb.
2. **Cell size / radius.** 0.5° cells with a 40 km radius are a guess
   that suits metro areas. Coastal cells mix beach and inland birds. Revisit
   after step 1's validation.
3. **eBird Status & Trends, later.** **Decided (2026-10-13): request
   access** (Sarah). Cornell offers its modelled weekly abundance free for
   non-commercial use, by **data access request**. It comes as downloadable
   data products, not a REST API; see `app/dao/status_trends.py`'s
   docstring. It's better data, especially for hard-to-photograph birds.
   v1 still ships on iNaturalist. Once access is granted, it can become the
   source behind the same tables. Nothing above the DAO would need to
   change, but turning the downloaded rasters into per-cell weekly values
   is its own offline processing step, to be scoped when access arrives.
   Record the access status here when it comes back.
4. **Notifications.** "Painted Bunting usually arrives in your area next
   week" would fit the existing notification bell, but needs a saved home
   location per user. Profiles only have `default_region` (an eBird
   region code), not a point. Out of scope for v1.

## Related pages

- [Plan a trip](plan-a-trip.md): could use this calendar for its date range instead of "last year only", as a follow-on
- [Bird information page](bird-info.md): could show the species' bar strip for the user's area, as a follow-on
- [Pinned birds](pinned-birds.md): the `PinButton` on every row
- [Life List page](life-list.md): the "not on my life list" filter
- [Database & migrations](database.md)
