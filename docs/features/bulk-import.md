# Bulk photo import

> **Status:** Built (backend + frontend) on `working/sparisi/BulkImport`.
> Backend tests cover `store=true`, HEIC, undo and the 7-day pin rule, and the
> import logic in `Services/bulkImport.js` was exercised in Node with
> stubbed responses. Migration `0009` is applied to the Neon database
> (2026-10-13). It's numbered after the `0007`/`0008` bug-report migrations
> already applied from another branch. **Not yet done:** §6 step 7, a live
> run in the browser with a real trip's worth of photos. Decisions are recorded under "Open questions" below.

## 1. What you're building

Someone comes back from a trip with 40 bird photos. Today that's 40 runs
through the Add Observation wizard. Bulk import turns it into:

```text
pick many photos (multi-select)
          │
          ▼
for each photo, in the browser, 2 at a time:
  POST /identify/photo  →  top guesses + EXIF lat/lng/date
  (photo also stored, stripped of metadata — see §4)
          │
          ▼
review screen — one card per photo:
  thumbnail · top guess (+ alternates) · confidence
  date/time · location · include ☑
  flags: "no location", "low confidence", "possible duplicate"
          │
   user fixes what's wrong, unticks what to skip
          │
          ▼
"Log N observations"  →  POST /observations, one per ticked card
          │
          ▼
summary: N logged, M new life-list species
```

**Nothing is logged without the user reviewing it.** The model is good but
not field-guide-grade ([Photo-based bird ID](bird-id.md) §1, §9), and
auto-logging 40 guesses would quietly pollute the life list. The review
screen is the main thing being built, not an extra.

### The review card

| Element | Behavior |
|---|---|
| Species | Top guess preselected. A dropdown offers the other 5 candidates `/identify/photo` already returned, plus "Search…" (the existing `GET /species/search` fallback from Add Observation). |
| Confidence | Shown as today in the photo flow. Below a threshold (start at 50%, tune later) the card gets a **low confidence** flag and starts **unticked**, so the user must actively confirm it. |
| Date/time | From EXIF `taken_at`. If missing, falls back to a batch-wide date the user sets once at the top of the screen (default: today). Editable per card. |
| Location | From EXIF GPS. If missing, the card is flagged **no location**. Allowed, since `lat`/`lng` are optional on observations, but region tagging and pin matching need it. "Apply a location to all flagged cards" opens one `LocationPicker` map and fills every card missing a location. A single card can be edited the same way. |
| Sex / life stage / notes | Default `unknown` / `unknown` / empty. Editable per card, collapsed by default to keep the grid scannable. |
| Possible duplicate | Flagged when another card has the same species within ~10 minutes and ~200 m. A burst of shots of one bird is common. Flagging only; the user decides whether to untick it. Duplicates aren't merged automatically. |

**One photo = one observation.** Grouping several photos into a single
observation would need multi-photo observations, which don't exist
(`observations.photo_url` is a single column). Out of scope.

### Why the browser drives the loop (no server job queue)

Each photo is one ordinary `POST /identify/photo` call, and the browser
works through the list itself. Once the model is warm a call takes about
0.4 s ([Photo-based bird ID](bird-id.md) §9), so 40 photos is well under a
minute plus upload time. That means:

- **No new infrastructure.** No worker, no job table, no polling endpoint.
  Render's free tier is already unconfirmed for BioCLIP's memory
  (bird-id.md §9). Processing one request at a time doesn't add to that,
  where a server-side batch holding many images would.
- **Region cost is paid once.** Photos from one trip share a region, so
  only the first photo pays the regional checklist's cold-embedding cost.
- **The catch:** the tab must stay open until the scan finishes. Fine for
  dozens of photos; not for a 2,000-photo archive. If that use case turns up,
  revisit with a real background job (see open questions). Not before.

Cold start is the one slow moment: the first request after the Render
service has been asleep can take 35–40 s plus Render's own wake-up time.
The screen shows "Warming up the bird model…" on the first photo rather
than looking stuck.

### Cap per import

**50 photos per import** to start. That keeps the review screen usable, the
in-browser state small, and a mistaken import cheap to undo (§3). The UI
says so before the picker opens; if more are picked, it takes the first 50
and says so.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| The photos | the user's device (multi-select file input) | Classified in memory (`/identify/photo`). The stored copy goes to Supabase Storage **with metadata stripped** (via [photo-metadata](photo-metadata.md)); URL in `observations.photo_url` |
| Candidate species + confidence | BioCLIP via `/identify/photo`, unchanged | in browser memory for the review screen; plus the existing in-memory `identification_repo` record per photo (not read back) |
| Date/time, location | EXIF via `photo_metadata`, else the batch-wide default / the user | `observations.observed_at`, `lat`/`lng` |
| Place label | `GET /geocode/reverse` once per **distinct** location (round to ~3 decimals and cache in the browser, so 40 photos from one park make 1–2 Nominatim calls rather than 40; Nominatim's usage policy is 1 req/s) | `observations.location_name` |
| Region code | `ebird.region_for_point()`, server-side in `log_observation()`, unchanged | `observations.region` |
| Import batch id | generated by the frontend per import | `observations.import_batch_id` (§3) |
| "Is it a lifer?" | the existing life-list check, done once per import (not per card) before logging | not stored; shown in the summary |

## 3. Database changes (SQL)

One nullable column, so a whole import can be listed and undone together:

```sql
-- 0009_observation_import_batch.sql

alter table observations add column if not exists import_batch_id text;   -- null for anything not logged via bulk import
create index if not exists observations_import_batch_idx
    on observations (user_id, import_batch_id)
    where import_batch_id is not null;
```

| Column (new) | Meaning |
|---|---|
| `observations.import_batch_id` | Same value on every observation from one import (a UUID made in the browser). Lets "Undo this import" delete exactly that set, and lets a future "My imports" view group them. `null` for wizard-logged observations. |

Optional, not a prerequisite: everything else here works without it. But
without it, undoing a bad import means deleting up to 50 observations one at
a time, so it's recommended.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/photo` | **One addition:** an optional `store=true` form field. When set, the endpoint also strips and stores the photo (same code path as `POST /uploads/photo`) and returns `photo_url` in the response. Without it, every photo would be uploaded twice (once to identify, once to store), which is 2× the bandwidth on a phone over cellular. The existing wizard can adopt it too, but doesn't have to. |
| `POST` | `/observations` | **Unchanged in shape.** Called once per ticked card. Accepts the new `import_batch_id`. |
| `DELETE` | `/users/{user_id}/imports/{import_batch_id}` | **New.** Deletes every observation with that batch id for that user. Returns `{deleted: N}`. Stored photos are left alone (see the orphan note below). |

A `POST /observations/bulk` endpoint was considered and **not** recommended
for the MVP. At most 50 sequential calls is fine, it keeps
`log_observation()`'s per-observation logic (region lookup, pin evaluation)
in one place, and a partial failure is easy to show per card ("3 failed,
retry"). Revisit if this shows up as slow in practice.

**Orphaned photos:** with `store=true`, photos for cards the user unticks
(or for imports abandoned halfway) stay in the bucket without an
observation pointing at them. Today's wizard already has the same issue
(it uploads before the user commits). Accept it for now; a periodic cleanup
of unreferenced objects is a separate, later task for both flows.

### Pin notifications for back-dated sightings

`app/services/pins.py#evaluate_pins()` runs on every logged observation and
**doesn't look at `observed_at`**. Importing last spring's trip would send
other users "someone just saw your pinned bird" alerts about sightings that
are months old. That's already possible with one back-dated wizard entry,
but bulk import makes it routine.

**Recommendation:** in `log_observation()`, skip `evaluate_pins()` when
`observed_at` is more than **7 days** before now, for every observation,
not just imports. A pin alert is only useful if the bird might still be
there. This is a small behavior change to [Pinned birds](pinned-birds.md),
so get the owner's sign-off.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/photo_metadata.py` | from [photo-metadata](photo-metadata.md), reused unchanged |
| `dao/` | `app/dao/observation_repo.py` (extend) | persist `import_batch_id`; `delete_by_import_batch(user_id, batch_id) -> int` |
| `services/` | `app/services/identify.py` (extend) | `identify_photo(..., store=False)`: when set, hands bytes to `uploads.py`'s strip-and-store path and includes `photo_url` |
| `services/` | `app/services/observation.py` (extend) | the 7-day pin rule (§4); `undo_import()` |
| `models/` | `app/models/observation.py`, `app/models/identification.py` (extend) | `import_batch_id`; optional `photo_url` on `IdentifyResponse` |
| `routers/` | `app/routers/identify.py`, `app/routers/observations.py` (extend) | `store` form field; the `DELETE` route |
| `Dao/` | `frontend/src/Dao/identify.js`, `Dao/observations.js` (extend) | `store` flag; undo call |
| `Services/` | `frontend/src/Services/bulkImport.js` (**new**) | The queue: concurrency 2, per-photo status (`queued` / `identifying` / `ready` / `failed`), retry. Duplicate and low-confidence flagging. Reverse-geocode cache. Logging the ticked cards in order and collecting per-card failures. Pure logic, no DOM, so it's testable on its own. |
| `Presenters/` | `frontend/src/Presenters/BulkImport.js` (**new**) | The screen: picker → progress → review grid → summary (+ "Undo this import") |
| `Components/` | `frontend/src/Components/ImportReviewCard.js` (**new**) | one presentational card. Reuses `LocationPicker.js` for the per-card / apply-to-flagged map instead of writing a new one |

Entry points: an "Import several photos" link on Add Observation's Describe
step, next to "Upload a photo". Possibly also on Life List later.

## 6. Build order

1. **[Photo location & date (EXIF)](photo-metadata.md), fully.** Hard prerequisite.
2. `store=true` on `POST /identify/photo` (+ test: stored bytes have no
   GPS, response has `photo_url`; without the flag nothing is stored).
3. The 7-day pin rule in `log_observation()` (+ tests both sides of the
   cutoff), after the Pinned birds owner agrees.
4. Migration `0009_observation_import_batch.sql`, `import_batch_id` on the
   models + repo, and the `DELETE` undo route (+ tests: deletes only that
   user's batch, returns the count).
5. `Services/bulkImport.js`: queue, flags, geocode cache. Most of the
   logic lives here.
6. `Components/ImportReviewCard.js` → `Presenters/BulkImport.js` → entry link.
7. **Live run** with a real trip's worth of photos (~30, mixed: some with
   GPS, some screenshots without, a burst of one bird) against the deployed
   Render service. Write the measured timings and cold-start behavior back
   into §1, the way bird-id.md §9 records its real numbers.

## Open questions

Decide these before starting. Each has a recommendation, but they're product
calls.

**Decided 2026-10-13** (Sarah): questions 1–3 as recommended, plus the
7-day pin rule in §4.

1. ~~**8 MB limit.**~~ **Decided: 25 MB for both photo endpoints; the stored
   copy is shrunk to a 2048 px longest edge** during the metadata strip
   (`app/services/uploads.py`: `MAX_BYTES`, `STORED_MAX_EDGE`). EXIF reading
   stays server-side in one place.
2. ~~**HEIC.**~~ **Decided: accepted** via `pillow-heif`, registered once in
   `app/dao/photo_metadata.py`. HEIC is stored as JPEG, since only Safari can
   display HEIC. Windows browsers often send `.heic` files with no MIME type,
   so both the server (`uploads.normalize_content_type`) and the browser
   (`Services/uploads.js#validateImageFile`) fall back to the file extension.
   In the review grid a HEIC card shows the stored JPEG once it's uploaded,
   since the local preview won't render outside Safari.
3. ~~**50-photo cap.**~~ **Decided: 50.** Revisit after the live run.
4. **Folder picking.** `<input webkitdirectory>` lets a desktop user pick a
   whole folder. Cheap to add, but mobile doesn't support it. Nice-to-have,
   not MVP.
5. **Large archives (hundreds–thousands of photos).** Would need a real
   server-side job (upload all, process in the background, notify when
   done) and very likely a paid Render plan. Explicitly **not** this
   feature; revisit only if people actually ask for it.

## Related pages

- [Photo location & date (EXIF)](photo-metadata.md): prerequisite
- [Photo-based bird ID](bird-id.md): the model, its accuracy, and its cold-start numbers
- [Add Observation](add-observation.md): the one-at-a-time flow this complements; reuses its `LocationPicker` and species search
- [Pinned birds](pinned-birds.md): affected by the 7-day rule in §4
- [Database & migrations](database.md)
