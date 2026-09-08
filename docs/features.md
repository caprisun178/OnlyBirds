# Features

MVP feature breakdown. Each section is a spec: what the user sees, the data it
needs, the API surface, and how it maps onto the `Dao` / `Services` /
`Presenters` / `Components` layering.

**Status legend:** ✅ built · 🚧 partial · 📋 planned

| Feature | Status |
|---|---|
| [Life List page](#1-life-list-page) | 🚧 API returns entries; region filter + checklist view planned |
| [Add Observation](#2-add-observation) | 🚧 `POST /observations` exists; identification flow planned |
| [User profiles](#3-user-profiles) | 📋 planned |
| [Stickers](#4-stickers) | 📋 planned |

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
| `POST` | `/observations` |  exists — create the observation once species is confirmed |
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
| life list total | **derived** — count of the user's `LifeListEntry` rows |
| sticker collection | **derived** — the user's `UserSticker` rows |

No bio, no follower graph in MVP.

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

## Data model additions (summary)

| Model | Change |
|---|---|
| `User` | + `username`, `avatar_url`, `default_region` |
| `Identification` | **new** — `observation_id`, `method` (`photo` / `describe`), `input`, `candidates`, `chosen_species`, `confidence`, `outcome` (`correct` / `incorrect` / `unconfirmed`) |
| `RegionChecklist` | **new** (cache) — `region_code`, `species_codes[]`, `fetched_at` |
| `Sticker` | **new** — see [Models](#models) |
| `UserSticker` | **new** — award ledger |
| `Group` | **new** (data/fixture) — `code`, `kind` (`rank` / `set`), `rank_query` or `species_codes[]` |

## End-to-end flow

```
AddObservation → /identify/describe → user confirms species
      → POST /observations  (source = manual)
      → Services: is this a new species for the user?
            yes → create LifeListEntry
                → evaluate_stickers(user_id)
                      → award UserSticker rows + AwardToast
                → profile life_list_total / sticker_count recompute
      → LifeList page shows the species card filled in (was a MissingBird)
```
