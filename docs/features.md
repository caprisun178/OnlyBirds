# Features

MVP feature breakdown. Each section is a spec: what the user sees, the data it
needs, the API surface, and how it maps onto the `Dao` / `Services` /
`Presenters` / `Components` layering.

**Status** is one of *Partial* (some API already exists) or *Planned* (not
started). Nothing here is fully built yet.

| Feature | Status |
|---|---|
| [Life List page](#1-life-list-page) | Partial — API returns entries; region filter + checklist view planned |
| [Add Observation](#2-add-observation) | Partial — `POST /observations` exists; identification flow planned |
| [User profiles](#3-user-profiles) | Planned |
| [Stickers](#4-stickers) | Planned |
| [Pinned birds](#5-pinned-birds) | Planned |
| [Bird information page](#6-bird-information-page) | Planned |
| [Explore map](#7-explore-map) | Planned |

---

## 1. Life List page

### What it is

The user's personal index of every bird species. It is a **completion view**,
not just a log: it shows the full checklist of birds for a region, with the ones
the user has observed filled in and the rest shown as placeholders. This is the
home screen for a signed-in user.

### Region filter

The checklist is scoped by region, selectable from a hierarchy backed by eBird
region codes:

```
world → country (US) → subnational1 (US-WA) → subnational2 / county (US-WA-033)
```

- Changing the region changes **which species set** is shown and the
  denominator of the progress bar (e.g. "142 / 511 in Washington").
- The user's default region is remembered on their profile.
- "Life list (worldwide)" is the special case `region = world`.

Backing data:

- Region list — eBird `GET /ref/region/list/{type}/{parentCode}`
- Species checklist for a region — eBird `GET /product/spplist/{regionCode}`
  (returns species codes), joined to names via `GET /ref/taxonomy/ebird`
- The user's seen species — our `LifeListEntry` rows

These are cached in `dao/` (region checklists change rarely).

### Missing-bird placeholder

Every species in the region checklist renders as a card:

| State | Card shows |
|---|---|
| Observed | user's `photo_url` (or the species' representative photo), common name, `first_observed_at` |
| Not yet observed | greyed **missing-bird silhouette**, common name, "Not seen yet" |

The placeholder is a single shared asset rendered by a pure
`Components/MissingBird` component whenever a species has no observation for this
user. Tapping a missing card deep-links into [Add Observation](#2-add-observation)
pre-filled with that species as the target.

### UI states

- **Grid** (default) and **list** toggle
- **Progress**: `seen / total` for the active region, plus a bar
- **Sort**: taxonomic (default), most recent, alphabetical
- **Empty**: brand-new user sees the full checklist as all-missing with a "Log
  your first bird" call to action

### API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{user_id}/life-list?region={code}` | entries, newest first; `region` optional, defaults to profile region |
| `GET` | `/regions?parent={code}&type={type}` | region picker options |
| `GET` | `/regions/{code}/checklist` | full species list for the region (names + codes + whether photographed) |

The client composes the completion view by zipping `/regions/{code}/checklist`
with `/users/{user_id}/life-list`.

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/lifelist.js`, `Dao/regions.js` | fetch entries + checklist from our API |
| `Services/lifeList.js` | zip checklist × entries → `{species, seen, observation}` rows; compute progress; apply region + sort |
| `Presenters/LifeList.jsx` | owns region filter, sort, grid/list toggle state |
| `Components/` | `SpeciesCard`, `MissingBird`, `ProgressBar` — presentational only |

---

## 2. Add Observation

### What it is

Logging that the user saw a bird. Two ways in:

1. **Photo** — the user submits a photo of the bird.
2. **Describe & guess** — the user describes the bird in words; the app returns
   its best guess; the user confirms whether the guess is right.

Both paths end with a confirmed species and a new `Observation`
(`source = manual`).

### Flow

```
choose method
   │
   ├── Photo ──────────► upload image ──► (CV suggestion) ──┐
   │                                                        ▼
   └── Describe ──► free-text traits ──► identification ──► ranked candidates
                                                            │
                                    user picks one / says "none of these"
                                                            ▼
                                             confirm species (yes / no)
                                                            ▼
                             add place (lat/lng + derived region), time, notes
                                                            ▼
                                    POST /observations  →  LifeListEntry?  →  sticker engine
```

### Describe & guess

- Input is free text ("small brown bird, streaky chest, sharp thin beak, in a
  reed bed") optionally plus structured hints (size bucket, dominant colour,
  habitat, region, was-it-singing).
- The **identification service** returns a ranked list of candidate species,
  each with a confidence score and a representative photo, so the user can
  eyeball them.
- The user either selects a candidate or rejects them all; then answers a final
  **correct / incorrect** on the chosen species.
- That confirmation is stored (`Identification.outcome`) and feeds accuracy
  metrics and, later, model tuning. An incorrect guess still lets the user pick
  the right species manually before logging.

!!! note "Computer vision is descoped for MVP"
    Per the root `README.md`, iNaturalist's species-classification model has no
    supported public API. MVP ships the **describe & guess** path (text-based,
    can be served by a taxonomy search or an LLM) and manual species selection.
    The photo path stores the image and logs the observation now; automatic
    photo identification is wired in later behind the same
    `POST /identify/photo` endpoint (self-hosted `inatVisionAPI` or the public
    "small" model — see README).

### Observation lifecycle

| State | Meaning |
|---|---|
| `draft` | method chosen, not yet identified |
| `identifying` | photo/description submitted, awaiting candidates |
| `confirmed` | user has locked a species |
| `logged` | persisted as an `Observation`; life list + stickers updated |

### Fields captured

`user_id`, `species` / `species_id`, `lat`, `lng`, `region` (derived),
`observed_at`, `source` (`manual`), `photo_url` (photo path), `notes`, and the
linked `Identification` (method, input, chosen candidate, confidence, outcome).

### API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/describe` | body: text + optional hints → `{candidates: [{species, confidence, photo_url}]}` |
| `POST` | `/identify/photo` | multipart image → same candidate shape (stub returns empty list until CV is added) |
| `POST` | `/observations` | exists today — create the observation once species is confirmed |
| `POST` | `/observations/{id}/confirm` | record correct/incorrect on the identification |

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/identify.js`, `Dao/observations.js` | raw calls to the endpoints above |
| `Services/observations.js` | orchestrates identify → confirm → `create`; returns `{observation, isNewSpecies}` so the UI can celebrate a lifer |
| `Presenters/AddObservation.jsx` | wizard state: method, description input, candidate selection, place/time |
| `Components/` | `CandidateList`, `SpeciesConfirm`, `PhotoPicker`, `PlacePicker` |

---

## 3. User profiles

### What it is

A deliberately small profile:

| Field | Source |
|---|---|
| `username` | chosen at signup, unique, immutable-ish |
| `avatar_url` | uploaded image |
| `default_region` | picked by the user from the eBird region hierarchy |
| life list total | **derived** — count of the user's `LifeListEntry` rows |
| sticker collection | **derived** — the user's `UserSticker` rows |

No bio, no follower graph in MVP.

### Default region

The user selects a **default region** — a single eBird region code chosen from
the same hierarchy as the [Life List region filter](#region-filter)
(`world → country → subnational1 → subnational2`). It is the app-wide default for
anything that is region-scoped, so the user is not re-picking a location on every
screen:

- **Life List page** — the checklist and progress denominator load for this
  region when no explicit `region` query param is given.
- **Add Observation** — the place picker and its map centre/zoom start on this
  region, and it seeds the `region` hint sent to `/identify/describe`.
- **Maps** — any map view opens centred on this region's bounds instead of a
  world view.
- **Candidate ranking** — describe & guess biases toward species on this
  region's checklist.

Set at first sign-in (defaulting to a coarse guess, e.g. country from locale)
and editable any time from the profile via `PATCH /users/{id}`. Individual
screens can still override it locally for a session without changing the saved
default. `region = world` is the valid "no regional bias" choice.

### Auth

Auth is delegated to a hosted provider (Auth0 / Supabase Auth). On first sign-in
we create a `User` keyed by `auth_provider_id`; the user then picks a
`username`. The base server currently trusts `auth_provider_id` as passed —
token verification is a follow-up.

### Views

- **Own profile**: editable avatar + username, life list total (links to the
  [Life List page](#1-life-list-page)), full sticker shelf.
- **Public profile** (`/u/{username}`): same read-only, for sharing.

### API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/users` | create after first auth: `{auth_provider_id, username, email?}` |
| `GET` | `/users/{username}` | public profile: username, avatar, `life_list_total`, `sticker_count` |
| `PATCH` | `/users/{id}` | update avatar / default region |
| `GET` | `/users/{id}/stickers` | full sticker collection (earned + locked, see below) |

### Model changes

`User` gains `username`, `avatar_url`, `default_region`. Totals are computed, not
stored.

---

## 4. Stickers

### What it is

The reward layer. As users fill in their life list they earn **stickers** for
milestones — first bird, first owl, first eagle, all eagles, and so on. Stickers
live on the [profile](#3-user-profiles) as a collectible shelf.

### Rule types

Every sticker is one rule type plus `criteria`:

| Rule type | Awards when… | Example | `criteria` |
|---|---|---|---|
| `first_ever` | the user's first life-list entry of any bird | **First Bird** | — |
| `first_in_group` | first life-list entry whose species is in a group | **First Owl**, **First Eagle** | `{group: "owls"}` |
| `group_complete` | the user has seen **every** species in a set | **All Eagles**, **All North American Owls** | `{group: "eagles"}` |
| `count_milestone` | life list total reaches N | **25 Club**, **Century (100)** | `{threshold: 100}` |
| `region_complete` | life list covers a region's full checklist | **Washington Sweep** | `{region: "US-WA"}` |
| `first_in_region` | first bird logged in a given region | **Hello, California** | `{region: "US-CA"}` |

### Groups and sets

- Some groups are clean taxonomic ranks — **owls** = order *Strigiformes*. These
  resolve straight from the eBird/iNat taxonomy.
- Some are folk categories that span the taxonomy — **eagles** are spread across
  *Aquila*, *Haliaeetus*, *Aquila*, sea-eagles, etc. Those are stored as an
  explicit curated **set of species codes**, versioned in the repo, not inferred
  from a rank.
- `criteria.group` names a group; the group definition (rank query *or*
  species-code set) is data the sticker engine loads.

### Models

**`Sticker`** (catalog, seeded from a fixture):

| Field | Notes |
|---|---|
| `code` | stable id, e.g. `first_owl` |
| `name`, `description` | display |
| `image_url` | the sticker art; a locked sticker shows a greyed version |
| `rule_type` | one of the table above |
| `criteria` | JSON (group / threshold / region) |
| `rarity` | `common` \| `uncommon` \| `rare` — drives shelf sorting |
| `sort_order` | within rarity |

**`UserSticker`** (award ledger):

| Field | Notes |
|---|---|
| `user_id`, `sticker_code` | unique together (idempotent awards) |
| `awarded_at` | timestamp |
| `observation_id` | the observation that completed it — for "earned by seeing a Bald Eagle on 3 May" |

### The engine

- Runs **after every new `LifeListEntry`** (i.e. after a lifer, not every
  observation).
- Loads the user's life list + the set of stickers they have **not** yet earned,
  evaluates each rule, writes `UserSticker` rows for any that now pass, and emits
  an award notification per sticker.
- Idempotent: the unique `(user_id, sticker_code)` constraint means re-running it
  is safe. `count_milestone` and `group_complete` can only ever go from
  locked → earned.
- Exposed for tests/backfill as an internal `evaluate_stickers(user_id)` in
  `Services/stickers` (no public "grant" endpoint).

### API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/stickers` | the full catalog |
| `GET` | `/users/{id}/stickers` | `{earned: [...], locked: [...]}` so the shelf can show progress |

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/stickers.js` | catalog + user stickers |
| `Services/stickers.js` | merge catalog with earned rows → shelf model; compute "3 / 8 eagles" style progress for `group_complete` stickers |
| `Presenters/StickerShelf.jsx` | shelf layout, filter by rarity/earned |
| `Components/` | `Sticker` (earned vs locked art), `AwardToast` |

### Starter catalog

| code | name | rule |
|---|---|---|
| `first_bird` | First Bird | `first_ever` |
| `first_owl` | Night Owl | `first_in_group {owls}` |
| `first_eagle` | Eagle Eye | `first_in_group {eagles}` |
| `first_raptor` | Bird of Prey | `first_in_group {raptors}` |
| `first_waterfowl` | Duck Duck | `first_in_group {waterfowl}` |
| `all_eagles` | Eagle Collector | `group_complete {eagles}` |
| `owls_na` | Parliament | `group_complete {owls_north_america}` |
| `species_25` | 25 Club | `count_milestone {25}` |
| `species_100` | Century | `count_milestone {100}` |
| `region_wa` | Washington Sweep | `region_complete {US-WA}` |

---

## 5. Pinned birds

### What it is

A **want-to-see list**. The user pins a species they are chasing; when someone
else logs that species in the user's region, the user gets a notification —
"A Snowy Owl was just reported in US-WA". Turns the
[Life List](#1-life-list-page) placeholders from a passive checklist into active
targets.

### Pinning

- Any not-yet-observed species can be pinned — from its `MissingBird` card on the
  Life List, or from a species detail view.
- A pin carries a **region scope**, defaulting to the user's
  [`default_region`](#default-region). The user can widen it (e.g. pin at `US`
  while travelling) or narrow it (`US-WA-033`).
- Pinning a species the user has already logged is a no-op — nothing to chase.
- A pin auto-clears when the species lands on the user's life list: they have
  seen it, so stop chasing it. Manual unpin any time.

### Match + notify

Runs **after every logged `Observation`** (not just lifers — someone else seeing
a common bird is still a sighting the user might chase), alongside the sticker
engine:

```
POST /observations  (logged, by user O, derived region R, species S)
        │
        ▼
find PinnedBird rows where
      species = S
  AND pin.region is an ancestor-or-equal of R   (world ⊇ US ⊇ US-WA ⊇ US-WA-033)
  AND pin.user_id != O                           (don't notify the reporter)
        │
        ▼
for each → create Notification(kind = "pin_hit", ...) → deliver
```

- **Region containment** is eBird-code prefix matching: `world` matches
  everything; otherwise `R` matches `pin.region` when `R == pin.region` or `R`
  starts with `pin.region + "-"`.
- **Dedupe**: at most one `pin_hit` per `(user, species, region, day)` — a
  twitchy species reported five times in a morning is one nudge, with a count
  ("reported 5× today").
- Location is coarsened to the region for MVP — never exact lat/lng, and the
  reporter's username is shown only if their profile is public.

### Notifications

This feature introduces the app's first real **notification feed**, which
[Stickers](#4-stickers) award toasts also fold into.

| Field | Notes |
|---|---|
| `user_id` | recipient |
| `kind` | `pin_hit` \| `sticker_awarded` |
| `payload` | JSON — for `pin_hit`: `{species, region, observation_id, count}` |
| `read_at` | null until the user opens the feed / dismisses |
| `created_at` | |

- **Delivery**: in-app feed (bell icon with unread count) for MVP. `payload`
  carries enough to render without a join; a deep link opens the species card or
  the observation's region on the map.
- Push / email are a follow-up — the `Notification` row is the source of truth
  and an out-of-band sender can drain unread rows later.

### API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/users/{id}/pins` | pinned species + region scope |
| `POST` | `/users/{id}/pins` | `{species, region?}`; `region` defaults to `default_region`; idempotent per `(user, species)` |
| `PATCH` | `/users/{id}/pins/{species}` | change region scope |
| `DELETE` | `/users/{id}/pins/{species}` | unpin |
| `GET` | `/users/{id}/notifications?unread=true` | feed, newest first |
| `POST` | `/users/{id}/notifications/read` | mark all (or `{ids: [...]}`) read |

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/pins.js`, `Dao/notifications.js` | CRUD against the endpoints above |
| `Services/pins.js` | `evaluate_pins(observation)` — region-containment query, dedupe, write `Notification` rows; `pin(user, species, region)` with the "already on life list" guard |
| `Services/notifications.js` | feed model, unread count, mark-read; shared by pins + stickers |
| `Presenters/` | `PinToggle` state on the Life List card; `NotificationsFeed.jsx` |
| `Components/` | `PinButton`, `NotificationBell`, `NotificationList` |

### Model changes

| Model | Change |
|---|---|
| `PinnedBird` | **new** — `user_id`, `species` / `species_id`, `region`, `created_at`; unique `(user_id, species)` |
| `Notification` | **new** — see [Notifications](#notifications); also emitted by the sticker engine |

---

## 6. Bird information page

### What it is

A reference page for a single species — the app's field guide. Reached by
**searching** ("herons", "Buteo", "Great Blue") or by tapping any species
anywhere in the app (`SpeciesCard`, `MissingBird`, `CandidateList`, a sticker, a
`pin_hit` notification). Read-only; the only user data on it is a "you have seen
this" badge and the pin toggle.

### What it shows

| Block | Content | Source |
|---|---|---|
| Header | common + scientific name, taxonomy (order / family), size | eBird taxonomy |
| Images | representative photos, swipeable | Macaulay Library |
| Sounds | call + song audio with an inline player | Macaulay Library |
| Migration | text summary + weekly relative-abundance / range map | eBird Status & Trends |
| About | identification, habitat, behavior, diet — a few short paragraphs | Cornell (All About Birds / Birds of the World) |
| Your status | "Seen — first on 3 May 2024" or "Not seen yet", plus a [pin](#5-pinned-birds) toggle | our `LifeListEntry` / `PinnedBird` |

### Search

- Query matches common name, scientific name, and family against the eBird
  taxonomy (`GET /ref/taxonomy/ebird`), which we already cache for the
  [Life List](#1-life-list-page).
- The same index backs manual species selection in
  [Add Observation](#2-add-observation) — one search service, two entry points.
- Results: common name, thumbnail, family; tap → species page.

### Data sourcing

!!! note "Content beyond taxonomy is not a single clean API"
    eBird's public API gives **taxonomy and observation data**, not life-history
    text. Rich content comes from other Cornell properties:

    - **Media** (photos, audio) — Macaulay Library asset API, keyed by species
      code; store asset IDs + credit, hot-link the media.
    - **Migration / abundance** — eBird Status & Trends (per-species range and
      weekly abundance maps).
    - **Descriptive text** — All About Birds (free) or Birds of the World
      (licensed). MVP pulls a short summary; with no licensed source the About
      block degrades to taxonomy plus a link out.

    All fetched content is cached in `SpeciesContent` and shown with the
    required **Cornell Lab / Macaulay Library attribution**.

### API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/species?q={query}` | search → `[{code, common_name, sci_name, family, thumb_url}]` |
| `GET` | `/species/{code}` | full profile: names, taxonomy, `about`, `migration`, media refs, `attribution` |
| `GET` | `/species/{code}/media?type=photo\|audio` | Macaulay asset list for the carousel / player |

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/species.js` | taxonomy lookup + Macaulay / Status & Trends / About fetches; writes the `SpeciesContent` cache |
| `Services/species.js` | merge taxonomy + content + media into one profile model; attach the user's seen / pinned status |
| `Presenters/SpeciesSearch.jsx`, `Presenters/SpeciesPage.jsx` | search box + results; the profile page and its media / pin interactions |
| `Components/` | `SearchBar`, `SpeciesHeader`, `MediaCarousel`, `AudioPlayer`, `RangeMap`, `AttributionFooter` |

### Model changes

| Model | Change |
|---|---|
| `SpeciesContent` | **new** (cache) — `species_code`, `about`, `migration`, `media[]` (`{type, macaulay_id, thumb_url, credit}`), `attribution`, `fetched_at` |

---

## 7. Explore map

### What it is

A full-screen slippy map for browsing **who saw what, where**. Opens centred on
the user's [`default_region`](#default-region) bounds; the user pans and zooms
anywhere in the world and the map shows recent bird sightings for whatever is in
view — the user's own, plus the wider birding record pulled from eBird and
iNaturalist.

### Behaviour

- **Viewport-driven**: pan / zoom settles → refetch sightings for the visible
  bounding box and the active date window. A debounce + a minimum zoom (no
  "whole planet" fetch) keeps request volume sane.
- **Clustered pins**: dense areas collapse into count bubbles; tap a cluster to
  zoom in, tap a pin for a popup — species (links to its
  [info page](#6-bird-information-page)), date, source badge (eBird / iNat /
  OnlyBirds), observer name where public, and a **pin this species** action.
- **Tap-to-log**: long-press / tap an empty spot to start
  [Add Observation](#2-add-observation) with that lat/lng prefilled.
- **Layers**: individual sightings (default) or a heat / abundance overlay at low
  zoom.

### Filters

| Filter | Options |
|---|---|
| Date | last 7 / 30 days (default 7), custom range |
| Species | free-text → restrict to one species; deep-linked from a species page's "recent sightings nearby" |
| Source | eBird, iNaturalist, OnlyBirds — any combination |
| Notable only | eBird's rare / notable observations for the region |

### Data sources

!!! note "Sightings are read-through from external APIs, not stored as our data"
    - **eBird** — recent observations by region
      (`GET /data/obs/{regionCode}/recent`) or by point + radius
      (`GET /data/obs/geo/recent?lat=&lng=`), plus `.../recent/notable` for the
      notable filter.
    - **iNaturalist** — `GET /v1/observations?taxon_id=3&nelat=&nelng=&swlat=&swlng=`
      (taxon 3 = Aves), verifiable/research-grade only.
    - **OnlyBirds** — our own `Observation` rows in the same bounding box.

    All three are normalised to one `Sighting` shape and **deduped** (same
    species + place + day reported to more than one service collapses to a
    single pin with multiple source badges). Coordinates that iNaturalist
    **obscures** for sensitive taxa are shown at their coarse point and flagged,
    never un-obscured. External APIs are rate-limited, so viewport queries are
    tile-and-time-bucket cached in `dao/`; results carry the required eBird /
    iNaturalist attribution.

### API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/sightings?bbox={w,s,e,n}&since={date}&species={code}&source={list}&notable={bool}` | merged, deduped, normalised sightings for the viewport |
| `GET` | `/sightings/{source}/{source_id}` | single sighting detail for the popup |

### Layering

| Layer | Responsibility |
|---|---|
| `Dao/sightings.js` | fetch eBird + iNat + internal observations; normalise to `Sighting`; tile / time-bucket cache |
| `Services/map.js` | viewport → query params; merge + dedupe across sources; apply filters; cluster server-side when counts are large |
| `Presenters/ExploreMap.jsx` | map camera (seeded from `default_region`), filter state, pin selection, tap-to-log hand-off |
| `Components/` | `MapCanvas`, `SightingCluster`, `SightingPin`, `SightingPopup`, `MapFilters`, `MapLegend`, `AttributionFooter` |

### Model changes

| Model | Change |
|---|---|
| `Sighting` | **normalised shape, not persisted** — `{source, source_id, species, common_name, lat, lng, observed_at, observer, obscured}` |
| `SightingCache` | **new** (cache) — `tile`, `since_bucket`, `source`, `sightings[]`, `fetched_at` |

---

## Data model additions (summary)

| Model | Change |
|---|---|
| `User` | + `username`, `avatar_url`, `default_region` |
| `Identification` | **new** — `observation_id`, `method` (`photo` / `describe`), `input`, `candidates`, `chosen_species`, `confidence`, `outcome` (`correct` / `incorrect` / `unconfirmed`) |
| `RegionChecklist` | **new** (cache) — `region_code`, `species_codes[]`, `fetched_at` |
| `Sticker` | **new** — see [Models](#models) |
| `UserSticker` | **new** — award ledger |
| `Group` | **new** (data/fixture) — `code`, `kind` (`rank` / `set`), `rank_query` or `species_codes[]` |
| `PinnedBird` | **new** — `user_id`, `species`, `region`, `created_at`; unique `(user_id, species)` |
| `Notification` | **new** — `user_id`, `kind` (`pin_hit` / `sticker_awarded`), `payload`, `read_at`, `created_at` |
| `SpeciesContent` | **new** (cache) — `species_code`, `about`, `migration`, `media[]`, `attribution`, `fetched_at` |
| `SightingCache` | **new** (cache) — `tile`, `since_bucket`, `source`, `sightings[]`, `fetched_at`; `Sighting` is a normalised read-through shape, not persisted |

## End-to-end flow

```
AddObservation → /identify/describe → user confirms species
      → POST /observations  (source = manual)
      → Services: is this a new species for the user?
            yes → create LifeListEntry
                → evaluate_stickers(user_id)
                      → award UserSticker rows + AwardToast
                → profile life_list_total / sticker_count recompute
      → evaluate_pins(observation)
            → other users with a PinnedBird for this species whose region
              scope contains the derived region  (and != the reporter)
                  → Notification(pin_hit) each, deduped per user/species/day
      → LifeList page shows the species card filled in (was a MissingBird)
```
