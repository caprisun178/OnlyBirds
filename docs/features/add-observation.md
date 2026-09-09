# Add Observation

> **Status:** Partial — `POST /observations` exists and stores a sighting. The
> identification flow (describe-and-guess, confirm, `identifications` row) is
> what's left.

## 1. What you're building

Logging that the user saw a bird. Two ways in:

1. **Photo** — the user submits a photo of the bird.
2. **Describe & guess** — the user describes the bird in words; the app returns
   its best guesses; the user confirms whether a guess is right.

Both paths end with a confirmed species and a new `Observation`
(`source = manual`).

### Flow

```text
choose method
   │
   ├── Photo ─────────► upload image ──► (CV suggestion) ──┐
   │                                                       ▼
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
  reed bed"), optionally plus structured hints (size bucket, dominant colour,
  habitat, region, was-it-singing).
- The **identification service** returns a ranked list of candidate species,
  each with a confidence score and a representative photo.
- The user selects a candidate or rejects them all, then answers a final
  **correct / incorrect** on the chosen species.
- That confirmation is stored (`identifications.outcome`) and feeds accuracy
  metrics and, later, model tuning. An incorrect guess still lets the user pick
  the right species manually before logging.

!!! note "Computer vision is descoped for MVP"
    Per the root `README.md`, iNaturalist's species-classification model has no
    supported public API. MVP ships the **describe & guess** path (served by a
    taxonomy search or an LLM) and manual species selection. The photo path
    stores the image and logs the observation now; automatic photo
    identification is wired in later behind the same `POST /identify/photo`
    endpoint.

### Observation lifecycle (`observations.status`)

| Value | Meaning |
|---|---|
| `draft` | method chosen, not yet identified |
| `identifying` | photo / description submitted, awaiting candidates |
| `confirmed` | user has locked a species |
| `logged` | fully persisted; life list + stickers have run |

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| Free-text description + structured hints | the user | `identifications.input` (jsonb) |
| Ranked candidate species | our `/identify/describe` service (taxonomy search or an LLM) — **not** an external CV API | `identifications.candidates` (jsonb) |
| The uploaded photo file | the user's device | **object storage** (S3 / Supabase Storage); the URL goes in `observations.photo_url` |
| Chosen species + correct/incorrect answer | the user | `identifications.chosen_species`, `identifications.outcome` |
| GPS point | the user's device / a map tap | `observations.lat` / `lng` and `observations.geom` |
| Region code for that point (e.g. `US-WA-033`) | derive it: eBird `GET /ref/region/...` reverse lookup, or a local point-in-polygon check | `observations.region` |
| Time, notes | the user | `observations.observed_at`, `observations.notes` |
| "Is this a lifer?" | our own data | computed — a lookup in `life_list_entries` |

The identification service is ours. The only external call on this screen is the
optional region-code lookup for the captured point.

## 3. Database changes (SQL)

Adds three columns to `observations` and one new table. See
[Database & migrations](database.md#how-to-apply-a-migration).

```sql
-- 0003_add_observation_identification.sql

-- 1. richer observation record
alter table observations add column region text;                    -- eBird regionCode, derived from lat/lng
alter table observations add column geom   geography(point, 4326);  -- PostGIS point for map + distance queries
alter table observations add column status text not null default 'logged'
    check (status in ('draft', 'identifying', 'confirmed', 'logged'));

-- backfill geom for any existing rows, then keep it in sync from the app layer
update observations set geom = st_setsrid(st_makepoint(lng, lat), 4326)::geography
    where geom is null;

create index observations_region_idx on observations (region);
create index observations_geom_idx   on observations using gist (geom);

-- 2. how the species was identified, and whether the guess was right
create table identifications (
    id              uuid primary key default gen_random_uuid(),
    observation_id  uuid references observations(id) on delete cascade,
    method          text not null check (method in ('photo', 'describe')),
    input           jsonb not null default '{}',   -- {text, size, colour, habitat, region, singing}
    candidates      jsonb not null default '[]',   -- [{species, confidence, photo_url}]
    chosen_species  text,                          -- eBird speciesCode the user locked in
    confidence      numeric,                       -- score of the chosen candidate, 0..1
    outcome         text not null default 'unconfirmed'
                      check (outcome in ('correct', 'incorrect', 'unconfirmed')),
    created_at      timestamptz not null default now()
);
create index identifications_observation_idx on identifications (observation_id);
```

| Column (new) | Meaning |
|---|---|
| `observations.region` | eBird region code the sighting falls in. [Stickers](stickers.md) and [Pinned birds](pinned-birds.md) match on this, so it must be filled on every insert. |
| `observations.geom` | The same point as `lat`/`lng`, as a PostGIS value. This is what [Explore map](explore-map.md) queries with a bounding box. Set it in the DAO on every insert: `st_setsrid(st_makepoint(lng, lat), 4326)`. |
| `observations.status` | Where the observation is in the wizard. Only `logged` rows count toward the life list. |
| `identifications.input` | Whatever the user gave us — free text and hints — as JSON. |
| `identifications.candidates` | The ranked list we showed them, as JSON, so we can review guesses later. |
| `identifications.outcome` | The final correct/incorrect answer. `unconfirmed` = they never answered. |

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/describe` | body: `{text, hints?}` → `{candidates: [{species, confidence, photo_url}]}` |
| `POST` | `/identify/photo` | multipart image → same candidate shape (stub returns `[]` until CV is added) |
| `POST` | `/observations` | **exists** — create the observation once the species is confirmed |
| `POST` | `/observations/{id}/confirm` | record `correct` / `incorrect` on the linked identification |

### Example — `POST /identify/describe`

```json
// request
{ "text": "small brown bird, streaky chest, thin beak, in reeds",
  "hints": { "size": "sparrow", "habitat": "wetland", "region": "US-WA" } }

// response
{ "candidates": [
    { "species": "sonspa", "common_name": "Song Sparrow",   "confidence": 0.71, "photo_url": "https://..." },
    { "species": "savspa", "common_name": "Savannah Sparrow","confidence": 0.18, "photo_url": "https://..." }
] }
```

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/identify.py` (**new**) | call the taxonomy search / LLM that produces candidates |
| `dao/` | `app/dao/observation_repo.py` (extend) | write `region`, `geom`, `status`; add `identifications` read/write |
| `dao/` | `app/dao/ebird.py` (extend) | `region_for_point(lat, lng)` |
| `services/` | `app/services/observation.py` (extend) | orchestrate identify → confirm → create; return `{observation, is_new_species}` so the UI can celebrate a lifer; call the sticker + pin engines |
| `routers/` | `app/routers/observations.py` (extend) | add `/identify/*` and `/observations/{id}/confirm` |
| `Dao/` | `frontend/src/Dao/identify.js` (**new**), `Dao/observations.js` | raw calls |
| `Services/` | `frontend/src/Services/observations.js` | wizard orchestration; returns `{observation, isNewSpecies}` |
| `Presenters/` | `frontend/src/Presenters/AddObservation.jsx` | wizard state: method, description, candidate pick, place/time |
| `Components/` | `CandidateList`, `SpeciesConfirm`, `PhotoPicker`, `PlacePicker` | presentational only |

## 6. Build order

1. Write and run `backend/migrations/0003_add_observation_identification.sql`.
2. Update the observation repo so **every** insert sets `geom` and `region`.
3. Add `app/dao/identify.py` returning canned candidates first (real logic
   later).
4. Add `POST /identify/describe` + `POST /observations/{id}/confirm` routes.
5. Extend `app/services/observation.py`: after a successful insert, check for a
   lifer, insert the `life_list_entries` row, then call
   `evaluate_stickers(user_id)` and `evaluate_pins(observation)`.
6. Tests: canned identify payload; assert an `identifications` row and the
   correct `status`.
7. Frontend wizard: `Dao/identify.js` → `Services/observations.js` →
   `Presenters/AddObservation.jsx` → components.

## Related pages

- [Life List page](life-list.md) — deep-links here with a target species
- [Stickers](stickers.md) and [Pinned birds](pinned-birds.md) — run after a log
- [Explore map](explore-map.md) — consumes `observations.geom`
- [Database & migrations](database.md)
