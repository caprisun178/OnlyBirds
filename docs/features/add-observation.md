# Add Observation

> **Status:** Partial — `POST /observations`, the describe & guess flow
> (`POST /identify/describe`, `POST /identify/{id}/select`), and the
> field-notes photo upload (`POST /uploads/photo`) all work end to end
> against the in-memory store. What's left: wiring this to PostgreSQL
> (roadmap step 3) and the region/geom columns below.

## 1. What you're building

Logging that the user saw a bird. Two ways in:

1. **Photo** — the user submits a photo of the bird. Stores the image and logs
   the observation; automatic photo identification isn't built yet (see the
   note below).
2. **Describe & guess** — the user describes the bird in words; the app shows
   six candidate photos; the user picks the one they saw.

Both paths end with a confirmed species and a new `Observation`
(`source = manual`).

### Flow

```text
describe the bird (free text + optional size/color/habitat)
                │
                ▼
      POST /identify/describe
                │
                ▼
      six candidate photos
                │
   user picks one, or "none of these"
                │
                ▼
    POST /identify/{id}/select
                │
       ┌────────┼────────┐
       ▼        ▼         ▼
   correct  incorrect  unconfirmed
       │    (try again  (no named
       │     on the     target to
       │     same six,  grade against
       │     or search  — the pick is
       │     manually)  trusted as-is)
       │        │         │
       └────────┴────┬────┘
                      ▼
      field notes: date/time, location,
      sex, life stage, photo, notes
                      │
                      ▼
             POST /observations
                      │
                      ▼
        is it a new life-list species?
```

### Describe & guess

- Input is free text ("a small brown streaky bird near the reeds", or just
  "a Blue Jay"), optionally plus structured hints (size, dominant color,
  habitat).
- `POST /identify/describe` returns six candidate species, each with a
  confidence score and a photo, plus an `identification_id` to reference on
  the next call.
- **If the text names a species outright**, that species is one of the six
  and the app already knows the "right answer." The user's pick is graded:
  - **Correct** — they picked the named species. The wizard moves straight to
    field notes.
  - **Incorrect** — they picked a different one of the six. The app tells
    them what they actually picked and lets them try again on the same set of
    photos, or fall back to a manual species search (`GET /species/search`).
- **If the text is generic** ("small brown streaky bird"), there's no known
  answer to grade against. The six candidates are just ranked suggestions —
  the pick is recorded as `unconfirmed` and trusted at face value, and the
  wizard moves on to field notes.
- Either way, `identifications.outcome` records what happened, which is there
  for later accuracy metrics / model tuning even though nothing reads it yet.

!!! note "Computer vision is descoped for MVP"
    Per the root `README.md`, iNaturalist's species-classification model has no
    supported public API, and there's no taxonomy-search or LLM call behind
    `/identify/describe` yet either. Candidates come from matching the
    description against a small hand-picked reference set
    (`app/data/birds.py`, grouped by which species look alike — "blue birds,"
    "brown streaky sparrows," and so on). Swapping in a real matching service
    later only touches `app/dao/identify.py` — the `Candidate` shape callers
    see doesn't change. The photo path stores the image and logs the
    observation now; automatic photo identification is wired in later behind
    `POST /identify/photo`.

!!! note "Candidate photos come from Wikimedia Commons, not eBird or Macaulay"
    eBird's API has no photo endpoint — that's Macaulay Library, a separate
    Cornell system. Macaulay's public catalog search (what a lot of hobby
    projects use in lieu of a real Cornell developer account) now sits behind
    an anti-bot challenge that a server-side call can't pass. So
    `app/dao/commons.py` looks up a real photo per species from Wikimedia
    Commons by scientific name instead — public, keyless, and stable — and
    `app/dao/bird_photos.py` caches the result in-memory and carries the
    required Creative Commons attribution string through to the frontend
    (`Candidate.photo_attribution`, shown as a caption under the photo).
    Falls back to a generated placeholder image if Commons has nothing for a
    species or the request fails. Swap this out for cached Macaulay media
    (`species_content.media`, see `bird-info.md`) once real Cornell access
    exists — nothing downstream of `bird_photos.get_photo()` needs to change.

### Field notes

Once a species is confirmed, the wizard asks for: date/time, a location
(address search + an interactive map — see below), sex
(male/female/unknown), life stage (adult/juvenile/fledgling/unknown), an
optional photo, and free-text notes. Submitting this calls
`POST /observations`, which the frontend also uses to check the user's
existing life list first, so it can tell them whether this is a new species.

**Location** works like iNaturalist's: type an address or place name and hit
Search (`GET /geocode/search`, proxying OpenStreetMap's Nominatim) to
navigate the map there, then click anywhere on the map to drop a pin for
exactly where the sighting happened — that pin's coordinates become
`observations.lat`/`lng`. Dropping a pin without an address search first (a
plain map click) reverse-geocodes it (`GET /geocode/reverse`) to fill in a
readable label automatically; either way, the label stays in a plain text
field the user can edit or overwrite. If geolocation permission is granted,
the map opens centered on the user's current location instead of a
country-wide default view.

!!! note "The map is a real Leaflet instance, not re-rendered markup"
    Every other piece of this screen is a template string rebuilt on every
    state change (`container.innerHTML = ...`). A live map can't work that
    way — recreating it on every keystroke elsewhere in the form would reset
    its pan/zoom/pin every time. `Components/LocationPicker.js` owns its own
    Leaflet instance outside of `state`, and the field-notes photo-upload
    status updates (the one thing on this step that used to trigger frequent
    re-renders) now patch just their own DOM subtree instead of doing a full
    re-render, specifically so the map isn't torn down while a photo
    uploads. The map *does* get recreated after an actual `POST /observations`
    submit failure (a full re-render, but rare) — `fieldNotes.lat`/`lng` are
    kept in `state` so the pin reappears in the same place either way.

Choosing a photo uploads it immediately (`POST /uploads/photo`, to a Supabase
Storage bucket) rather than waiting for the final submit — the wizard shows a
local preview right away and swaps in the real photo URL once the upload
finishes. If storage isn't configured or the upload fails, the field notes
form stays fully usable: the user sees a warning and can still submit without
a photo, since it's optional.

!!! note "Object storage needs a Supabase project"
    `POST /uploads/photo` returns `503` until `SUPABASE_URL` and
    `SUPABASE_SERVICE_ROLE_KEY` are set (see `backend/.env.example`) and a
    **public** bucket named `SUPABASE_STORAGE_BUCKET` (default
    `observation-photos`) exists in that project. Nothing else in the wizard
    depends on it — the field notes form works with or without it.

### Observation lifecycle (`observations.status`)

| Value | Meaning |
|---|---|
| `draft` | method chosen, not yet identified |
| `identifying` | photo / description submitted, awaiting candidates |
| `confirmed` | user has locked a species |
| `logged` | fully persisted; life list + stickers have run |

Every observation created through the wizard today goes straight to `logged`
— the earlier statuses exist for a future save-and-resume flow, not because
anything currently pauses mid-wizard.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Free-text description + structured hints | the user | `identifications.input` (jsonb) |
| Ranked candidate species | our `app/dao/identify.py` — matches a canned reference set (`app/data/birds.py`), **not** an external CV/LLM API yet | `identifications.candidates` (jsonb) |
| Candidate photos + attribution | Wikimedia Commons (`app/dao/commons.py`), cached per species in-process (`app/dao/bird_photos.py`); falls back to a placeholder image | not persisted — re-fetched (or served from cache) on every `/identify/describe` call |
| The uploaded photo file | the user's device | Supabase Storage (bucket `SUPABASE_STORAGE_BUCKET`); the public URL goes in `observations.photo_url` |
| Chosen species + correct/incorrect answer | the user's pick, graded against `target_species_code` when the text named a species outright | `identifications.chosen_species_code`, `identifications.outcome` |
| Sex, life stage, notes | the user (field-notes step) | `observations.sex`, `observations.life_stage`, `observations.notes` |
| Address search results | OpenStreetMap Nominatim (`app/dao/nominatim.py`, `GET /geocode/search`) | not persisted — only the pin the user drops from a result is saved |
| GPS point (address search navigates the map; the user then drops the exact pin) | the user, via the map | `observations.lat` / `lng` (not `geom` yet — see below) |
| Readable place label (auto-filled from the pin via reverse-geocode, or typed) | the user / OpenStreetMap Nominatim (`GET /geocode/reverse`) | `observations.location_name` |
| Region code for that point (e.g. `US-WA-033`) | derive it: eBird `GET /ref/region/...` reverse lookup, or a local point-in-polygon check | `observations.region` |
| Time | the user | `observations.observed_at` |
| "Is this a lifer?" | our own data | computed — a lookup in `life_list_entries` |

The identification logic itself is ours. External calls on this screen: the
Wikimedia Commons photo lookup above, OpenStreetMap Nominatim for address
search/reverse-geocode, OpenStreetMap tile servers (loaded directly by the
browser via Leaflet — not proxied), Supabase Storage for the field-notes
photo, and (not wired up yet) deriving an eBird region code for the dropped
pin.

## 3. Database changes (SQL)

Adds columns to `observations` and one new table. This is committed as
`backend/migrations/0002_add_observation_identification.sql`, ready to apply
once step 3 (PostgreSQL) lands — the app layer doesn't use it yet, only the
in-memory repos. See [Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0002_add_observation_identification.sql

-- 1. richer observation record
alter table observations add column if not exists location_name text;         -- readable label — typed, or auto-filled from the dropped pin via reverse-geocode
alter table observations add column if not exists sex          text
    check (sex in ('male', 'female', 'unknown'));
alter table observations add column if not exists life_stage   text
    check (life_stage in ('adult', 'juvenile', 'fledgling', 'unknown'));
alter table observations add column if not exists status       text not null default 'logged'
    check (status in ('draft', 'identifying', 'confirmed', 'logged'));
alter table observations alter column lat drop not null;   -- null only for observations logged before the map picker existed
alter table observations alter column lng drop not null;

-- 2. how the species was identified, and whether the guess was right
create table if not exists identifications (
    id                   uuid primary key default gen_random_uuid(),
    observation_id       uuid references observations(id) on delete cascade,
    method               text not null check (method in ('photo', 'describe')),
    input                jsonb not null default '{}',   -- {text, hints}
    candidates           jsonb not null default '[]',   -- [{species_code, common_name, confidence, photo_url}]
    target_species_code  text,                          -- known only when the text named a species outright
    chosen_species_code  text,                          -- the candidate the user picked
    outcome              text not null default 'unconfirmed'
                           check (outcome in ('correct', 'incorrect', 'unconfirmed')),
    created_at           timestamptz not null default now()
);
create index if not exists identifications_observation_idx on identifications (observation_id);
```

`region` and `geom` (for [Explore map](explore-map.md) / [Stickers](stickers.md))
aren't in this migration yet — they need the map-picker work first and are
still tracked as "left to build" above.

| Column (new) | Meaning |
|---|---|
| `observations.location_name` | Readable place label — typed, or auto-filled from the dropped map pin via reverse-geocode. Independent of `lat`/`lng`; the user can edit it freely. |
| `observations.sex` / `observations.life_stage` | Optional field-notes detail; `unknown` is a valid, explicit choice, distinct from "not answered" (`null`). |
| `observations.status` | Where the observation is in the wizard. Only `logged` rows count toward the life list. |
| `identifications.input` | Whatever the user gave us — free text and hints — as JSON. |
| `identifications.candidates` | The six candidates we showed them, as JSON, so we can review guesses later. |
| `identifications.target_species_code` | Set only when the description named a species outright — this is what the user's pick gets graded against. `null` for a generic description. |
| `identifications.outcome` | `correct` / `incorrect` when there was a target to grade against, `unconfirmed` when there wasn't (or the user rejected all six). |

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/describe` | body: `{text, hints?}` → `{identification_id, candidates: [{species_code, common_name, scientific_name, confidence, photo_url}]}` |
| `POST` | `/identify/{id}/select` | body: `{species_code}` (`null` = "none of these") → `{chosen_species, outcome, is_match}` |
| `POST` | `/identify/photo` | not built — photo-based identification is still descoped |
| `POST` | `/uploads/photo` | multipart `file` → `{photo_url}`; `503` if Supabase Storage isn't configured, `400` for an unsupported type or a file over 8 MB |
| `GET` | `/geocode/search?q=` | free text → `[{display_name, lat, lng}]`, proxying Nominatim; navigates the field-notes map |
| `GET` | `/geocode/reverse?lat=&lng=` | a point → `{display_name, lat, lng}` or `null`; auto-fills the location label after a plain map click |
| `POST` | `/observations` | create the observation once a species is confirmed; accepts `location_name`, `lat`, `lng`, `sex`, `life_stage`, `identification_id`, `status` alongside the existing fields |

### Example — `POST /identify/describe`

```json
// request
{ "text": "small brown streaky bird, thin beak, in the reeds",
  "hints": { "size": "small", "color": "brown", "habitat": "wetland" } }

// response
{ "identification_id": "a1b2c3...",
  "candidates": [
    { "species_code": "sonspa", "common_name": "Song Sparrow", "scientific_name": "Melospiza melodia", "confidence": 0.52,
      "photo_url": "https://upload.wikimedia.org/...", "photo_attribution": "Jane Doe / Wikimedia Commons (CC BY-SA 3.0)" },
    { "species_code": "savspa", "common_name": "Savannah Sparrow", "scientific_name": "Passerculus sandwichensis", "confidence": 0.44,
      "photo_url": "https://upload.wikimedia.org/...", "photo_attribution": "John Smith / Wikimedia Commons (CC BY 2.0)" }
  ] }
```

`photo_attribution` is `null` when Commons had nothing and a candidate fell
back to its placeholder image — there's no Commons content to credit in that
case.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `data/` | `app/data/birds.py` | canned reference species, grouped by visual-confusion; fallback placeholder photos |
| `dao/` | `app/dao/identify.py` | match free text (+ hints) against `birds.py`; named match vs. generic ranking; attaches real photos concurrently |
| `dao/` | `app/dao/commons.py` | raw Wikimedia Commons search — one photo + attribution per scientific name |
| `dao/` | `app/dao/bird_photos.py` | in-memory cache in front of `commons.py`; falls back to `birds.py`'s placeholder |
| `dao/` | `app/dao/identification_repo.py` | in-memory `identifications` store (same shape as `observation_repo.py`) |
| `dao/` | `app/dao/observation_repo.py` | persists `location_name`, `sex`, `life_stage`, `identification_id`, `status` |
| `dao/` | `app/dao/storage.py` | raw Supabase Storage HTTP calls — upload bytes, return the public URL |
| `dao/` | `app/dao/nominatim.py` | raw OpenStreetMap Nominatim calls — address search, reverse-geocode |
| `services/` | `app/services/identify.py` | describe → candidates; select → grade against a known target, if any |
| `services/` | `app/services/uploads.py` | validates content type / size before handing bytes to `storage.py` |
| `services/` | `app/services/geocoding.py` | normalizes Nominatim's raw JSON into `PlaceResult` |
| `routers/` | `app/routers/identify.py` | `POST /identify/describe`, `POST /identify/{id}/select` |
| `routers/` | `app/routers/uploads.py` | `POST /uploads/photo` |
| `routers/` | `app/routers/geocoding.py` | `GET /geocode/search`, `GET /geocode/reverse` |
| `Dao/` | `frontend/src/Dao/identify.js`, `Dao/species.js`, `Dao/uploads.js`, `Dao/geocoding.js` | raw calls |
| `Services/` | `frontend/src/Services/identify.js` | validates the description before calling the API |
| `Services/` | `frontend/src/Services/uploads.js` | validates type/size client-side before uploading |
| `Services/` | `frontend/src/Services/geocoding.js` | skips the search API call for a too-short query; no debounce needed since search is button/Enter-triggered, not per-keystroke |
| `Services/` | `frontend/src/Services/observations.js` | `createFromWizard()` — builds the payload, checks the life list first so `isNewSpecies` is accurate |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` | the whole wizard: describe → candidates → (manual search fallback) → field notes (map, address search, photo upload) → done |
| `Components/` | `frontend/src/Components/CandidateList.js` | presentational candidate grid; shows `photo_attribution` as a caption when present |
| `Components/` | `frontend/src/Components/LocationPicker.js` | owns a live Leaflet map + marker; loads Leaflet from a CDN at runtime; reports position changes via a callback rather than importing Dao/Services itself |
| `testData/` | `frontend/src/testData/testProfile.js` | stand-in "current user" until `user-profiles.md` ships |

Still to build: `region`/`geom` on `observations` and the sticker/pin engine
calls after a successful log.

## 6. Build order

For the next feature that follows this shape:

1. `app/data/birds.py` — canned species grouped by visual confusion, with a
   generated placeholder photo per species as the fallback.
2. `app/dao/identify.py` — text/hints matching; `app/dao/identification_repo.py`
   — in-memory store.
3. `app/services/identify.py` + `app/routers/identify.py` —
   `POST /identify/describe`, `POST /identify/{id}/select`.
4. Extend `Observation`/`ObservationCreate` with `location_name`, `sex`,
   `life_stage`, `identification_id`, `status`; make `lat`/`lng` optional.
5. Tests in `backend/tests/test_identify.py`: named-species grading, generic
   suggestions, rejecting all candidates, the full wizard → life list flow.
6. `backend/migrations/0002_add_observation_identification.sql` — SQL parity
   for when PostgreSQL is wired up (not applied anywhere yet).
7. `app/dao/storage.py` (raw Supabase Storage calls) + `app/services/uploads.py`
   (type/size validation) + `app/routers/uploads.py` — `POST /uploads/photo`.
   Tests in `backend/tests/test_uploads.py` cover validation and the
   not-configured (`503`) path without needing real Supabase credentials, plus
   the success path with `storage.upload_object` monkeypatched.
8. `app/dao/commons.py` (Wikimedia Commons search) + `app/dao/bird_photos.py`
   (cache + fallback), wired into `identify.py`'s candidate builder. Tests in
   `backend/tests/test_bird_photos.py` cover the cache/fallback logic with
   `commons.search_photo` monkeypatched; `conftest.py`'s autouse
   `no_live_photo_lookups` fixture keeps the rest of the suite offline.
9. `app/dao/nominatim.py` + `app/services/geocoding.py` + `app/routers/geocoding.py`
   — `GET /geocode/search`, `GET /geocode/reverse`. Tests in
   `backend/tests/test_geocoding.py` mock `nominatim.search`/`nominatim.reverse`
   directly (no autouse fixture needed — geocoding is only called from these
   two endpoints, not on some other hot path like the Commons photo lookup).
10. `Components/LocationPicker.js` (Leaflet map + marker, CDN-loaded) +
    `Dao/geocoding.js` + `Services/geocoding.js`, wired into
    `Presenters/AddObservation.js`'s field-notes step: address search box,
    persistent map, reverse-geocode on a plain pin drop.
11. Frontend, the rest: `Dao/identify.js` + `Dao/species.js` + `Dao/uploads.js`
    → `Services/identify.js` + `Services/species.js` + `Services/uploads.js` +
    extended `Services/observations.js` → `Presenters/AddObservation.js` →
    `Components/CandidateList.js` (renders `photo_attribution` as a caption).

Not yet done: `region`/`geom` derivation (`geom` needs the `lat`/`lng` this
step now collects — it's just not computed yet) and the sticker/pin engine
calls. `POST /uploads/photo` is fully wired but returns `503` until a
Supabase project's `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are set
locally — see the note under "Field notes" above.

## Related pages

- [Life List page](life-list.md) — deep-links here with a target species
- [Stickers](stickers.md) and [Pinned birds](pinned-birds.md) — run after a log
- [Explore map](explore-map.md) — consumes `observations.geom`
- [Database & migrations](database.md)
