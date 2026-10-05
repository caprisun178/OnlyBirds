# Bird information page

> **Status:** Planned, but de-risked — every data source below has been
> confirmed buildable with what this app already has (no waiting on Cornell
> licensing, no new paid API). Scoped precisely enough to build without
> re-deriving anything: see [§1](#1-what-youre-building) for the exact list
> of click targets, [§2](#2-where-the-data-comes-from-and-where-it-goes) for
> why the sourcing differs from earlier drafts of this page, and
> [§5](#5-how-the-code-is-layered) for how little of this is actually new
> code (most of it reuses `bird_photos.py`/`bird_audio.py`, already built
> for other features).

## 1. What you're building

A reference page for a single species — the app's field guide. Read-only;
the only user data on it is a "you have seen this" badge and the
[pin](pinned-birds.md) toggle (already built — `app/services/pins.py`,
`Components/MissingBird.js`'s pin button pattern).

### Entry points — every current click target, decided explicitly

A previous draft of this page said "reached by tapping any species anywhere
in the app," which sounds simple but isn't once you actually look: this
repo already has eight distinct places a species shows up, some of which
are *already* clickable for something else, and reusing the wrong attribute
name on a shared element is a real bug this app already hit once (a pin
button on `MissingBird.js` collided with `LifeList.js`'s own
`data-scientific-name` selector, firing both handlers on one click — see
that fix's commit for the exact failure mode). Don't repeat it. Each
surface below is decided, not left to guesswork:

| # | Surface | File | Decision | How to wire it without colliding |
|---|---|---|---|---|
| 1 | Life List, **seen** card | `Components/SpeciesCard.js` | **Add**, as a secondary action — the whole card already navigates to that species' observation log (`data-scientific-name`/`data-common-name`, wired by `LifeList.js#wireSpeciesCards()`), and that's still useful on its own | Add a distinct sub-element (e.g. the species name as its own link) with its own attributes — `data-action="view-profile"` + `data-profile-scientific-name` — and `e.stopPropagation()` in its own click handler so the card's existing navigate-to-log listener doesn't *also* fire |
| 2 | Life List, **unseen** card | `Components/MissingBird.js` | **Add**, on the whole card — nothing else claims a click on this card except the pin button | Wrap everything *except* the pin button in the click target, using a third, still-distinct attribute name (`data-profile-scientific-name`, not `data-scientific-name` or `data-pin-scientific-name` — both already mean something else). The pin button's own handler needs `e.stopPropagation()` added back (it doesn't need it today, but will the moment this card itself becomes clickable — a click on "Pin" would otherwise bubble up and *also* open the profile) |
| 3 | Add Observation candidate picker | `Components/CandidateList.js` | **Skip, deliberately** | This is an active selection flow (`data-species-code`, wired to pick that candidate) — navigating away mid-wizard would lose progress. Not worth a half-built "info" affordance without also designing how to return to the wizard where the user left off; leave it out rather than ship something confusing |
| 4 | Sighting detail panel | `Components/SightingDetail.js` (used by `ExploreMap.js`'s docked panel and `PlanATrip.js`'s hotspot drill-down) | **Add** — the species name/header isn't clickable today (only the photo is, via `data-action="enlarge-photo"`) | Make the name its own link with a new attribute, wired once inside `renderSightingDetail`'s own markup; both Presenters that mount this component need their existing wiring function updated (`ExploreMap.js`'s detail-panel wiring, `PlanATrip.js`'s hotspot-sighting-detail wiring) since each wires this shared component separately today |
| 5 | Plan a Trip "likely species" cards | `Presenters/PlanATrip.js` (inline markup, not a shared component) | **Add** — not clickable at all today, no collision risk | Wire the whole card |
| 6 | Bell dropdown notification row | `Components/NotificationBell.js` | **Skip, deliberately** | The whole row is already the click target (mark read + jump to the sighting on the map) — adding a second destination on the same click target is exactly the kind of ambiguous-click bug this app has already shipped and fixed once. If this is wanted later, it needs its own nested sub-element with `stopPropagation()`, not a reuse of the row's existing handler |
| 7 | Full notifications feed row | `Presenters/NotificationsFeed.js` | **Skip, deliberately** | Same reasoning as #6 |
| 8 | Explore Map species-filter autocomplete | `Presenters/ExploreMap.js` | **Skip, deliberately** | This is a filter-picker, not a species display — selecting a suggestion sets the active filter (`mousedown` on `data-species-suggestion`); navigating away would break the one thing this control does |

Also reached by **searching** directly (see below).

### What it shows

| Block | Content | Source |
|---|---|---|
| Header | common + scientific name, taxonomy (order / family) if known | our `species` table (eBird taxonomy, already populated by Life List) |
| Photo | one representative photo | **reuses** `app/dao/bird_photos.py#get_stock_photo()` — already built, Wikimedia Commons-backed, disk-cached, used by Life List/Plan a Trip/Explore Map today. Zero new dao code. |
| Sound | a call/song recording, if one exists | **reuses** `app/dao/bird_audio.py#get_audio()` — same deal; returns `None` cleanly if Commons has nothing (no placeholder — see that file's own docstring for why) |
| About | a short description paragraph | Wikipedia's REST summary API (see note below) — **new**, one dao function |
| Your status | "Seen — first on 3 May 2024" or "Not seen yet", plus the pin toggle | our `life_list_entries` (derived) / `pinned_birds` — both already exist |

Deliberately **not** in v1: a migration/range map. That needs eBird's
*Status & Trends* product, which — confirmed while building
[Plan a Trip](plan-a-trip.md)'s `region_for_point()` — is a separately
gated product, not reachable with the regular API key. Not worth blocking
this page on it; add it later if that access is ever obtained.

!!! note "Why Wikipedia instead of Cornell (All About Birds / Birds of the World)"
    The original plan for the About block was Cornell's own life-history
    text. That's licensed content, not a public API — All About Birds has
    no public endpoint, and Birds of the World needs an institutional
    subscription. Wikipedia's REST summary API
    (`GET https://en.wikipedia.org/api/rest_v1/page/summary/{title}`) is
    free, needs no auth, and is the same trust tier this app already
    accepted for photos/audio (Wikimedia Commons — same foundation,
    sibling project). The tradeoff is honest: Wikipedia's bird articles are
    general-audience, not a field guide's ID/behavior/habitat breakdown.
    Good enough for "what is this bird," which is this block's actual job;
    say so in the UI rather than imply field-guide depth the source
    doesn't have. **Implementation detail that matters:** Wikipedia article
    titles for birds are almost always the common name ("Black-capped
    chickadee"), not the scientific name — query by `common_name` first,
    and only fall back to `scientific_name` if that 404s or comes back
    ambiguous (a disambiguation page, detectable by the response shape).

### Search

- The query matches common name, scientific name, and family against the
  eBird taxonomy already loaded into the `species` table (for Life List).
- The **same search** can back manual species selection in
  [Add Observation](add-observation.md) — one search service, two entry
  points (not required for v1, worth doing once this exists).
- Results: common name, thumbnail (via the same `get_stock_photo()` reuse
  above), family; tap → the profile page.

## 2. Where the data comes from and where it goes

Endpoint details (auth, base URL, failure behavior) for eBird live on the
[eBird API](../ebird-api.md) page, not here.

| Data | Comes from | Stored where |
|---|---|---|
| Taxonomy: names, family, codes | eBird `GET /ref/taxonomy/ebird` | `species` table (already populated by Life List — no new fetch needed for species already in it) |
| Search matches | our `species` table | queried live with a trigram index (below) |
| Photo | Wikimedia Commons, via the existing `bird_photos.py` | its own existing cache (`species_photo_cache.json`) — **not** duplicated into a new table |
| Sound | Wikimedia Commons, via the existing `bird_audio.py` | its own existing in-memory cache — same reasoning |
| About text | Wikipedia REST summary API | `species_content.about` (new, small cache table — see below) |
| "Seen / not seen" + pin state | our own data | `life_list_entries` (derived) / `pinned_birds` |

## 3. Database changes (SQL)

One small cache table, plus a search index on the existing `species` table.
Numbered `0006` — the next real migration after
`0005_pinned_birds_and_notifications.sql` (an earlier draft of this page
said `0007`, written before migrations `0004`/`0005` existed). See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0006_species_content.sql

create extension if not exists pg_trgm;   -- fuzzy text search for the species search box

-- fast "search as you type" over species names
create index if not exists species_common_name_trgm on species using gin (common_name gin_trgm_ops);
create index if not exists species_sci_name_trgm    on species using gin (scientific_name gin_trgm_ops);

-- cached About text, one row per species. No media here — photos/audio
-- already have their own caches (bird_photos.py / bird_audio.py);
-- duplicating that into this table would just be a second cache to keep in
-- sync for no benefit.
create table if not exists species_content (
    scientific_name  text primary key,   -- matches this app's established identity key for a species
                                          -- (see pinned-birds.md's note on why scientific_name, not an
                                          -- eBird-only code, is the one field every source reliably has)
    about            text,                -- Wikipedia summary extract; null is fine — UI falls back to taxonomy only
    about_source_url text,                -- the Wikipedia page, for the required outbound attribution link
    fetched_at       timestamptz not null default now()
);
```

| Column | Meaning |
|---|---|
| `scientific_name` | Primary key — same identity convention `pinned_birds` already established, so this page can be looked up from every entry point in §1 (several of which only ever have a scientific name on hand, not an eBird code). |
| `about` / `about_source_url` | The Wikipedia extract and the page it came from (required for attribution and lets the UI link out to the full article). Null `about` just means the page shows taxonomy + photo/sound with no About block — not an error state. |
| `fetched_at` | Refresh when this is older than ~30 days (Wikipedia summaries change rarely, but not never). |
| `species_*_trgm` indexes | Make `where common_name ilike '%heron%'` fast enough to run on every keystroke in the search box. |

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/species/search?q=` | search → `[{scientific_name, common_name, family, photo_url}]`. Already exists today pointed at iNaturalist's autocomplete for Add Observation's manual search — decide whether this feature repoints that same endpoint at our own `species` table (one search, two callers) or adds a separate one; repointing is the cleaner long-term answer but touches Add Observation, so treat that as its own decision, not implied by this page |
| `GET` | `/species/profile?scientific_name=` | full profile: taxonomy (if the species is in our `species` table — gracefully omitted if not, e.g. an iNaturalist-only species never logged via eBird), `about`, `about_source_url`, `photo_url`, `audio_url` |

Query-param, not a path segment like `/species/{code}` — deliberately, since
most of §1's real entry points only ever have a `scientific_name` on hand,
never an eBird code (`SightingDetail.js`, `PlanATrip.js`'s likely-species
cards, and others in the survey have no species code at all). Keying the
lookup on the one field that's actually always present avoids a
lookup-by-code endpoint that half of its real callers can't use.

### Example — `GET /species/profile?scientific_name=Poecile atricapillus`

```json
{
  "scientific_name": "Poecile atricapillus",
  "common_name": "Black-capped Chickadee",
  "family": "Paridae",
  "photo_url": "https://upload.wikimedia.org/...",
  "photo_attribution": "...",
  "audio_url": "https://upload.wikimedia.org/...",
  "audio_attribution": "...",
  "about": "The black-capped chickadee is a small, non-migratory, North American songbird...",
  "about_source_url": "https://en.wikipedia.org/wiki/Black-capped_chickadee"
}
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/wikipedia.py` (**new**) | `get_summary(title)` — the one genuinely new external call this feature needs |
| `dao/` | `app/dao/bird_photos.py`, `app/dao/bird_audio.py` (reuse, **no changes**) | already do exactly what the Photo/Sound blocks need |
| `dao/` | `app/dao/species_repo.py` (**new**, small) | read/write `species_content`; look up a `species` row by `scientific_name` |
| `services/` | `app/services/species.py` (extend) | assemble one profile: taxonomy (if known) + cached/fetched About + photo + audio + the caller's seen/pinned status |
| `routers/` | `app/routers/species.py` (extend) | `GET /species/profile`, and `GET /species/search` if repointed (see §4) |
| `Dao/` | `frontend/src/Dao/species.js` (extend) | `getProfile(scientificName)` |
| `Services/` | `frontend/src/Services/species.js` (**new**) | UI-shaped profile model |
| `Presenters/` | `Presenters/SpeciesPage.js` (**new**) | the profile screen; owns fetching, the pin toggle, the seen/unseen badge |
| `Components/` | extend `SpeciesCard.js`, `MissingBird.js`, `SightingDetail.js` per §1's table; `PlanATrip.js`'s inline cards (not a shared component — edit directly) | the new click targets, each exactly as specified in §1 — nothing beyond that table |

## 6. Build order

1. Write and run `backend/migrations/0006_species_content.sql`.
2. Add `app/dao/wikipedia.py#get_summary(title)` — confirm live once against
   a real species (common name first, scientific name fallback — see the
   note in §1), then mock it in tests per the offline-tests rule
   (`docs/ebird-api.md`).
3. Add `app/dao/species_repo.py`.
4. Extend `app/services/species.py` to assemble the profile — call
   `bird_photos.get_stock_photo()` / `bird_audio.get_audio()` directly, no
   new media code.
5. Add the `GET /species/profile` route.
6. Tests: canned Wikipedia payload + a known `species` row; assert the
   merged profile shape; assert a graceful (not error) response for a
   `scientific_name` not in our `species` table at all.
7. Frontend: `Dao/species.js` → `Services/species.js` → `Presenters/SpeciesPage.js`.
8. Register the route (`species-profile` in `preview.js`'s `SCREENS`,
   passing `{ scientificName }`).
9. Wire each entry point in §1's table **exactly as decided there** — rows
   marked "Skip, deliberately" are not oversights to "complete" later
   without first re-deciding the UX tradeoff written next to them.

## Related pages

- [Life List page](life-list.md) — populates `species`, hosts the seen/unseen cards this links from
- [Add Observation](add-observation.md) — candidate picker deliberately not linked (§1); shares the species search if repointed
- [Pinned birds](pinned-birds.md) — the pin toggle on this page; also the precedent for keying on `scientific_name`
- [Explore map](explore-map.md) / [Plan a trip](plan-a-trip.md) — `SightingDetail.js` and the likely-species cards link here
- [Database & migrations](database.md)
