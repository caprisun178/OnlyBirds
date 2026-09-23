# Add Observation

> **Status:** Partial — `POST /observations`, the describe & guess flow
> (`POST /identify/describe`, `POST /identify/{id}/select`), and the
> field-notes photo upload (`POST /uploads/photo`) all work end to end.
> `observations` persists to Postgres (Neon) once `DATABASE_URL` is set, and
> falls back to an in-memory store when it isn't (local dev without a
> database, tests). What's left: the region/geom columns below.

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

- First choice: **"I saw it" or "I heard it"** (`sense: "sight" | "sound"`,
  defaults to `"sight"`). This only changes what media the candidates carry —
  a photo either way, plus a call/song recording in "heard it" mode — not the
  matching logic itself; see the note below.
- Input is free text ("a small brown streaky bird near the reeds", or just
  "a Blue Jay" — or, in sound mode, "a loud harsh call from the treetops"),
  optionally plus structured hints (size, dominant color, habitat).
- `POST /identify/describe` returns six candidate species, each with a
  confidence score and a photo (plus a recording, in sound mode), and an
  `identification_id` to reference on the next call.
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
- Either way, the outcome is kept (in memory, for the wizard session —
  `app/dao/identification_repo.py`) as `correct` / `incorrect` /
  `unconfirmed`, though nothing reads it back today. It doesn't outlive the
  session: once a species is confirmed, only the resulting `Observation`
  matters, not how it got identified.

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

!!! note "Candidate photos and audio come from Wikimedia Commons, not eBird or Macaulay"
    eBird's API has no media endpoint — that's Macaulay Library, a separate
    Cornell system. Macaulay's public catalog search (what a lot of hobby
    projects use in lieu of a real Cornell developer account) now sits behind
    an anti-bot challenge that a server-side call can't pass. So
    `app/dao/commons.py` looks up real media per species from Wikimedia
    Commons by scientific name instead — public, keyless, and stable, and it
    turns out to mirror a lot of Xeno-canto's call/song archive for exactly
    this reason. `app/dao/bird_photos.py` and `app/dao/bird_audio.py` each
    cache their result in-memory and carry the required Creative Commons
    attribution through to the frontend (`Candidate.photo_attribution` /
    `audio_attribution`, shown as a caption under the media). A photo falls
    back to a generated placeholder if Commons has nothing; **audio has no
    placeholder** — a fabricated bird call would actively mislead someone
    trying to identify one by ear, so `audio_url` is just `null` for a
    species with no recording, and the candidate card says so. Swap either
    out for cached Macaulay media (`species_content.media`, see
    `bird-info.md`) once real Cornell access exists — nothing downstream of
    `bird_photos.get_photo()` / `bird_audio.get_audio()` needs to change.

!!! note "Audio is only fetched in sound mode"
    Fetching a recording per candidate is another network round trip same as
    photos, so `app/dao/identify.py#_with_media` only calls
    `bird_audio.get_audio()` when `sense == "sound"` — sight-mode candidates
    always have `audio_url: null` without ever touching Commons for audio.

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
| "I saw it" / "I heard it" (`sense`) | the user | in memory, for the wizard session (`identification_repo.py`) |
| Free-text description + structured hints | the user | in memory, for the wizard session |
| Ranked candidate species | our `app/dao/identify.py` — matches a canned reference set (`app/data/birds.py`), **not** an external CV/LLM API yet | in memory, for the wizard session |
| Candidate photos + attribution | Wikimedia Commons (`app/dao/commons.py`), cached per species in-process (`app/dao/bird_photos.py`); falls back to a placeholder image | not persisted — re-fetched (or served from cache) on every `/identify/describe` call |
| Candidate call/song recordings + attribution (sound mode only) | Wikimedia Commons, cached per species (`app/dao/bird_audio.py`); **no** placeholder fallback | not persisted — same as photos |
| The uploaded photo file | the user's device | Supabase Storage (bucket `SUPABASE_STORAGE_BUCKET`); the public URL goes in `observations.photo_url` |
| Chosen species + correct/incorrect answer | the user's pick, graded against `target_species_code` when the text named a species outright | in memory only — doesn't outlive the wizard session; only the resulting `Observation` gets persisted |
| Sex, life stage, notes | the user (field-notes step) | `observations.sex`, `observations.life_stage`, `observations.notes` |
| Sight vs. sound (carried over from the describe step) | the user's earlier `sense` choice | `observations.detection_type` |
| Address search results | OpenStreetMap Nominatim (`app/dao/nominatim.py`, `GET /geocode/search`) | not persisted — only the pin the user drops from a result is saved |
| GPS point (address search navigates the map; the user then drops the exact pin) | the user, via the map | `observations.lat` / `lng` (not `geom` yet — see below) |
| Readable place label (auto-filled from the pin via reverse-geocode, or typed) | the user / OpenStreetMap Nominatim (`GET /geocode/reverse`) | `observations.location_name` |
| Region code for that point (e.g. `US-WA-033`) | derive it: eBird `GET /ref/region/...` reverse lookup, or a local point-in-polygon check | `observations.region` |
| Time | the user | `observations.observed_at` |
| "Is this a lifer?" | our own data | computed live from `observations` — no separate life-list table (`app/services/life_list.py`) |

The identification logic itself is ours. External calls on this screen: the
Wikimedia Commons photo lookup above, OpenStreetMap Nominatim for address
search/reverse-geocode, OpenStreetMap tile servers (loaded directly by the
browser via Leaflet — not proxied), Supabase Storage for the field-notes
photo, and (not wired up yet) deriving an eBird region code for the dropped
pin.

## 3. Database changes (SQL)

Adds columns to `observations` — no new table. This is committed as
`backend/migrations/0002_add_observation_identification.sql` and applied.
See [Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0002_add_observation_identification.sql

alter table observations add column if not exists location_name   text;         -- readable label — typed, or auto-filled from the dropped pin via reverse-geocode
alter table observations add column if not exists sex             text
    check (sex in ('male', 'female', 'unknown'));
alter table observations add column if not exists life_stage      text
    check (life_stage in ('adult', 'juvenile', 'fledgling', 'unknown'));
alter table observations add column if not exists detection_type  text
    check (detection_type in ('sight', 'sound'));
alter table observations add column if not exists status          text not null default 'logged'
    check (status in ('draft', 'identifying', 'confirmed', 'logged'));
alter table observations alter column lat drop not null;   -- null only for observations logged before the map picker existed
alter table observations alter column lng drop not null;
```

No `identifications` table: how a bird was identified (candidates shown,
which one was picked, whether the guess was right) only matters for the
wizard session that produced it, not afterwards — it stays in memory
(`app/dao/identification_repo.py`) rather than a table that would just
accumulate rows nothing reads.

`region` and `geom` (for [Explore map](explore-map.md) / [Stickers](stickers.md))
aren't in this migration yet — they need the map-picker work first and are
still tracked as "left to build" above.

| Column (new) | Meaning |
|---|---|
| `observations.location_name` | Readable place label — typed, or auto-filled from the dropped map pin via reverse-geocode. Independent of `lat`/`lng`; the user can edit it freely. |
| `observations.sex` / `observations.life_stage` | Optional field-notes detail; `unknown` is a valid, explicit choice, distinct from "not answered" (`null`). |
| `observations.detection_type` | `'sight'` or `'sound'` — carried over from the describe step's choice. `null` for anything logged before this existed. |
| `observations.status` | Where the observation is in the wizard. Only `logged` rows count toward the life list. |

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/describe` | body: `{text, hints?, sense?}` (`sense`: `"sight"` \| `"sound"`, default `"sight"`) → `{identification_id, sense, candidates: [{species_code, common_name, scientific_name, confidence, photo_url, photo_attribution, audio_url, audio_attribution}]}` |
| `POST` | `/identify/{id}/select` | body: `{species_code}` (`null` = "none of these") → `{chosen_species, outcome, is_match}` |
| `POST` | `/identify/photo` | not built — photo-based identification is still descoped |
| `POST` | `/uploads/photo` | multipart `file` → `{photo_url}`; `503` if Supabase Storage isn't configured, `400` for an unsupported type or a file over 8 MB |
| `GET` | `/geocode/search?q=` | free text → `[{display_name, lat, lng}]`, proxying Nominatim; navigates the field-notes map |
| `GET` | `/geocode/reverse?lat=&lng=` | a point → `{display_name, lat, lng}` or `null`; auto-fills the location label after a plain map click |
| `POST` | `/observations` | create the observation once a species is confirmed; accepts `location_name`, `lat`, `lng`, `sex`, `life_stage`, `detection_type`, `status` alongside the existing fields |

### Example — `POST /identify/describe` (sound mode)

```json
// request
{ "text": "a loud harsh call from a tree near the water", "sense": "sound",
  "hints": { "size": "small", "color": "brown", "habitat": "wetland" } }

// response
{ "identification_id": "a1b2c3...", "sense": "sound",
  "candidates": [
    { "species_code": "sonspa", "common_name": "Song Sparrow", "scientific_name": "Melospiza melodia", "confidence": 0.52,
      "photo_url": "https://upload.wikimedia.org/...", "photo_attribution": "Jane Doe / Wikimedia Commons (CC BY-SA 3.0)",
      "audio_url": "https://upload.wikimedia.org/.../Melospiza_melodia_-_Song_Sparrow.mp3", "audio_attribution": "John Smith / Wikimedia Commons (CC BY 2.0)" },
    { "species_code": "savspa", "common_name": "Savannah Sparrow", "scientific_name": "Passerculus sandwichensis", "confidence": 0.44,
      "photo_url": "https://upload.wikimedia.org/...", "photo_attribution": "John Smith / Wikimedia Commons (CC BY 2.0)",
      "audio_url": null, "audio_attribution": null }
  ] }
```

`photo_attribution` is `null` when Commons had nothing and a candidate fell
back to its placeholder image. In sight mode (the default), `audio_url` /
`audio_attribution` are always `null` for every candidate — the audio lookup
never runs at all. In sound mode, `audio_url` is `null` specifically when
Commons has no recording for that species (Savannah Sparrow above) — there's
no placeholder fallback for audio the way there is for photos.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `data/` | `app/data/birds.py` | canned reference species, grouped by visual-confusion; fallback placeholder photos |
| `dao/` | `app/dao/identify.py` | match free text (+ hints) against `birds.py`; named match vs. generic ranking; attaches real photos concurrently |
| `dao/` | `app/dao/commons.py` | raw Wikimedia Commons search — one photo or audio file + attribution per scientific name; shared hidden-screen-reader-text stripping and attribution formatting |
| `dao/` | `app/dao/bird_photos.py` | in-memory cache in front of `commons.py`'s photo search; falls back to `birds.py`'s placeholder |
| `dao/` | `app/dao/bird_audio.py` | in-memory cache in front of `commons.py`'s audio search; no fallback — caches misses as `None` too |
| `dao/` | `app/dao/identification_repo.py` | in-memory only — candidates/outcome never outlive the wizard session, no SQL table |
| `dao/` | `app/dao/observation_repo.py` | persists `location_name`, `sex`, `life_stage`, `status`; Postgres (Neon) when `DATABASE_URL` is set, in-memory otherwise (`app/dao/db.py`) |
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
| `Components/` | `frontend/src/Components/CandidateList.js` | presentational candidate grid; shows `photo_attribution` as a caption, and (sound mode) an `<audio controls>` player per candidate — see the accessibility note below |
| `Components/` | `frontend/src/Components/LocationPicker.js` | owns a live Leaflet map + marker; loads Leaflet from a CDN at runtime; reports position changes via a callback rather than importing Dao/Services itself |
| `testData/` | `frontend/src/testData/testProfile.js` | stand-in "current user" until `user-profiles.md` ships |

Still to build: `region`/`geom` on `observations` and the sticker/pin engine
calls after a successful log.

!!! note "Candidate cards are `div[role=button]`, not real `<button>`s"
    HTML doesn't allow interactive content — an `<audio controls>` player
    counts — to nest inside a real `<button>`; a browser silently breaks the
    button open if you try, which breaks the whole card's click handling.
    So in sound mode a candidate card needs its own audio player *and* to
    stay clickable as a whole, which a real button can no longer do.
    `CandidateList.js` renders each card as a `div` with `role="button"` /
    `tabindex="0"` instead, and `AddObservation.js` wires both a `click` and
    a `keydown` (Enter/Space) listener by hand to keep it keyboard-accessible
    — a real button gets that for free, a div doesn't. Interacting with the
    audio player itself calls `stopPropagation()` so pressing play doesn't
    also select the card.

## 6. Build order

For the next feature that follows this shape:

1. `app/data/birds.py` — canned species grouped by visual confusion, with a
   generated placeholder photo per species as the fallback.
2. `app/dao/identify.py` — text/hints matching; `app/dao/identification_repo.py`
   — in-memory store.
3. `app/services/identify.py` + `app/routers/identify.py` —
   `POST /identify/describe`, `POST /identify/{id}/select`.
4. Extend `Observation`/`ObservationCreate` with `location_name`, `sex`,
   `life_stage`, `status`; make `lat`/`lng` optional.
5. Tests in `backend/tests/test_identify.py`: named-species grading, generic
   suggestions, rejecting all candidates, the full wizard → life list flow.
6. `backend/migrations/0002_add_observation_identification.sql` — applied;
   `app/dao/observation_repo.py`'s `PostgresObservationRepo` is what actually
   uses these columns once `DATABASE_URL` is set.
7. `app/dao/storage.py` (raw Supabase Storage calls) + `app/services/uploads.py`
   (type/size validation) + `app/routers/uploads.py` — `POST /uploads/photo`.
   Tests in `backend/tests/test_uploads.py` cover validation and the
   not-configured (`503`) path without needing real Supabase credentials, plus
   the success path with `storage.upload_object` monkeypatched.
8. `app/dao/commons.py` (Wikimedia Commons search) + `app/dao/bird_photos.py`
   (cache + fallback), wired into `identify.py`'s candidate builder. Tests in
   `backend/tests/test_bird_photos.py` cover the cache/fallback logic with
   `commons.search_photo` monkeypatched; `conftest.py`'s autouse
   `no_live_media_lookups` fixture keeps the rest of the suite offline.
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
12. Sight vs. sound: `app/dao/commons.py` generalized to search `filetype:audio`
    too (shared `_search()` helper, shared `format_attribution()`); new
    `app/dao/bird_audio.py` (cache, no fallback); `IdentifyRequest.sense` /
    `Candidate.audio_url` / `audio_attribution` added to the models;
    `identify.py#_with_media` only fetches audio when `sense == "sound"`.
    Extended `Observation`/`ObservationCreate` with `detection_type`. Tests:
    `test_bird_audio.py` (cache + no-fallback behavior), `test_commons.py`
    (pure `_strip_html`/`format_attribution` logic — including a regression
    for a real duplicated-attribution bug hit while testing against live
    data, see below), and new cases in `test_identify.py` (sight mode never
    calls the audio lookup at all; sound mode does, for every candidate).
    Frontend: the sight/sound toggle in the describe step, `CandidateList.js`
    rendering an `<audio controls>` player per candidate, and the
    div-instead-of-button restructuring described above.

Not yet done: `region`/`geom` derivation (`geom` needs the `lat`/`lng` this
step now collects — it's just not computed yet) and the sticker/pin engine
calls. `POST /uploads/photo` is fully wired but returns `503` until a
Supabase project's `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are set
locally — see the note under "Field notes" above.

!!! note "A real Commons data-quality bug, found by testing against live data"
    Wikimedia Commons' "Unknown author" template embeds a hidden
    screen-reader duplicate of itself — the raw `Artist` field for at least
    one real recording used here came back as `'Unknown author<span
    style="display: none;">Unknown author</span>'`. Stripping HTML tags alone
    left "Unknown authorUnknown author" in the credit line. `commons.py`'s
    `_strip_html` now drops any `display:none` span *before* stripping tags.
    Worth knowing if another Commons field ever reads doubled — check for a
    hidden span before assuming it's a bug in our own formatting.

## Related pages

- [Life List page](life-list.md) — deep-links here with a target species
- [Stickers](stickers.md) and [Pinned birds](pinned-birds.md) — run after a log
- [Explore map](explore-map.md) — consumes `observations.geom`
- [Database & migrations](database.md)
