# Photo location & date (EXIF)

> **Status:** Built (backend + frontend), on `dev/experiment`. Unit tests
> cover read/strip/precedence, and a live `POST /identify/photo` with a
> GPS-tagged JPEG returned the right lat/lng/date. **Not yet done:** §6
> step 6, checking on a real iPhone and Android phone whether GPS survives
> our file input. No migration. [Bulk photo import](bulk-import.md) builds
> on this.

## 1. What you're building

Most phone and camera photos record **where** and **when** they were taken
in their EXIF metadata. Today the user re-types both in the When & Where step
of [Add Observation](add-observation.md), and often doesn't bother. Location
is optional, and the date defaults to "now". That matters more than it looks:
lat/lng + date are what widen photo ID's candidate pool to the region's real
eBird checklist ([Photo-based bird ID](bird-id.md) §9). Without them, the
model falls back to its ~430-name default pool.

This feature does two things with that metadata:

1. **Reads it.** When a photo goes through `POST /identify/photo` (or
   `POST /uploads/photo`), the backend pulls GPS lat/lng and the
   capture time out of the file. It uses them for the regional candidate
   pool when the form didn't supply any, and returns them so the frontend
   can pre-fill the When & Where fields.
2. **Strips it from the stored copy.** `POST /uploads/photo` saves files
   unchanged to a **public** Supabase bucket today. Anyone with an
   observation's `photo_url` can read the GPS position out of it, which is
   often the user's home or garden. The stored copy is re-saved without
   metadata. (This is the EXIF privacy fix Community already listed as a
   prerequisite. It's built here because reading the metadata and removing
   it happen in the same place.)

### Precedence: the user always wins

Photo metadata only **fills blanks**. It never overwrites something the user
entered:

| Field | Photo value is used when… |
|---|---|
| Location (`lat`/`lng`) | no pin has been dropped yet |
| Date/time (`observedAt`) | the field still holds its untouched "now" default (track a `observedAtTouched` flag, since the field is never empty) |

When metadata fills a field, Confirm shows a one-line note under it ("Filled
in from your photo, change it if that's wrong"). Both fields stay editable,
same as today. If the photo has nothing usable, nothing changes and the flow
behaves exactly as it does now.

On the backend, `identify_photo()` uses the same rule, field by field. Form
`lat`/`lng`/`observed_at` win, and EXIF values are only the fallback for
building the regional pool.

**The date needed one extra rule.** The Describe step's date is never empty
(it defaults to "now"), so if the frontend always sent it, the photo's date
could never be used. The photo flow therefore **leaves out a date that's
still the untouched default** (`currentLocation({ omitDefaultDate: true })`).
If neither the form nor the photo gives a date but a location is known, the
backend uses today's date, so the regional pool works exactly as it did
before. The describe flow is unchanged and still always sends the date.

### What counts as "usable" metadata

- **GPS:** `GPSLatitude`/`GPSLongitude` plus their `N/S`/`E/W` refs, in the
  GPS IFD. Treat exactly `0, 0` as missing; it's a common bad-default value.
  Reject anything outside ±90/±180.
- **Capture time:** `DateTimeOriginal` (Exif IFD) only. **Do not** fall back
  to the base `DateTime` tag, because that's the last-modified time and an
  edited photo would report the edit date. The value goes into the
  `datetime-local` field as the **photo's local wall-clock time**, which is
  what the user would type anyway. `OffsetTimeOriginal` is ignored and
  nothing is converted between timezones. The all-zero
  `0000:00:00 00:00:00` some cameras write when the clock isn't set counts
  as missing.
- **Everything else** (camera model, lens, altitude, direction) is ignored.

### Honest limits worth stating

- **Many photos won't have it.** Screenshots, photos sent through messaging
  apps (WhatsApp, iMessage, and others), and many social-media downloads have
  the metadata removed before we ever see them. Mobile browsers' photo pickers
  can also remove location: iOS has a per-share "Location" toggle, and recent
  Android photo pickers are reported to redact GPS unless the app has a
  special permission. **Unverified for our upload input. Test on a real iPhone
  and a real Android phone before promising anything in UI copy.** The
  fallback is today's manual entry, so a miss costs nothing.
- **Phone GPS can be off by tens of meters**, and a photo taken through a
  long lens is of a bird that may be far from the photographer. That's fine
  for region lookup and a map pin; the user can still drag the pin.
- **HEIC** (iPhone's native format) is accepted since bulk import and
  stored as JPEG. See [Bulk photo import](bulk-import.md), open question 2.
- **Camera JPEGs stored as MPO.** Many camera JPEGs, Fujifilm's included,
  open in Pillow as **MPO** (a JPEG plus an embedded preview frame). The
  first version of `strip()` rejected them as an unsupported format, so a
  real camera JPEG would have failed to upload. Fixed while building bulk
  import: MPO is stored as a plain JPEG of its main frame, and
  `test_mpo_camera_jpeg_is_read_and_stored_as_plain_jpeg` covers it.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| GPS lat/lng from the photo | the image file's EXIF GPS IFD, read with Pillow (already a dependency) | not stored as-is. Returned to the frontend as a suggestion; only ends up in `observations.lat`/`lng` if the user keeps it |
| Capture time from the photo | EXIF `DateTimeOriginal` | same: a suggestion for `observations.observed_at` |
| The stored photo | the user's upload, **re-saved without metadata** | Supabase Storage (unchanged bucket); URL in `observations.photo_url` as today |
| Bytes sent to `/identify/photo` | the user's upload | not stored (unchanged). Classified in memory and discarded |

No new external calls. The reverse-geocoded place label still comes from
the existing `GET /geocode/reverse` once the frontend sets the pin, same as
a manual map click.

## 3. Database changes (SQL)

**None.** The values land in existing `observations` columns via the
existing `POST /observations`. We deliberately **don't** record "this
location came from EXIF". Once the user confirms the location, where it came
from stops mattering, same reasoning as not persisting `identifications`
([Add Observation](add-observation.md) §3).

## 4. API endpoints

| Method | Path | Change |
|---|---|---|
| `POST` | `/identify/photo` | Response gains `photo_metadata: {lat, lng, taken_at} \| null` (each field individually nullable). Form `lat`/`lng`/`observed_at` still take precedence; EXIF values are only used for the regional pool when those are missing. |
| `POST` | `/uploads/photo` | Response gains the same `photo_metadata`. The stored object is re-saved without metadata (see §5). **New `400`** for bytes that aren't a readable image; this used to be stored as-is. The stored file's type and extension come from the decoded format, not the client's claim. |

```json
// POST /identify/photo response (additions only)
{
  "identification_id": "id_8f2a1c",
  "method": "photo",
  "sense": "sight",
  "candidates": [ ... ],
  "photo_metadata": { "lat": 35.7796, "lng": -78.6382, "taken_at": "2026-09-14T07:42:10" }
}
```

`photo_metadata` is `null` when the file had neither GPS nor a capture time.
`taken_at` is a naive local timestamp (see §1), so it drops straight into the
`datetime-local` input.

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/photo_metadata.py` | Pure functions, no network. `read(image_bytes) -> {lat, lng, taken_at} \| None` converts the GPS degree/minute/second rationals to decimal and applies the N/S/E/W sign. It never raises. `strip(image_bytes) -> (bytes, content_type)` applies `ImageOps.exif_transpose()` **first**, so the stored copy keeps its correct rotation once the orientation tag is gone (same bug class as bird-id.md §1). It then clears `img.info`, keeping only the ICC colour profile (Pillow falls back to `info` for XMP when saving), and re-encodes: JPEG and WebP at quality 90, PNG losslessly. GIFs and **animated** WebP/PNG pass through untouched, since re-encoding would keep only the first frame. That's a small known gap for animated WebP/PNG with EXIF, which bird photos almost never are. Raises `UnreadableImage` for non-images. |
| `models/` | `app/models/upload.py`, `app/models/identification.py` | A `PhotoMetadata` model; add an optional `photo_metadata` to `PhotoUploadResponse` and `IdentifyResponse` |
| `services/` | `app/services/uploads.py` (extend) | `read` → `strip` → `storage.upload_object`; returns the URL + metadata |
| `services/` | `app/services/identify.py` (extend) | `identify_photo()` calls `photo_metadata.read()` and falls back to its values for `_regional_candidates()` when the form fields are missing |
| `Services/` | `frontend/src/Services/uploads.js` | new `uploadPhotoWithMetadata()` returns `{photoUrl, photoMetadata}`. `uploadPhoto()` still returns just the URL, so `ObservationList.js` is untouched. `Services/identify.js` needed no change; it already passes the whole response through. |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` | `applyPhotoMetadata()` applies the §1 precedence rule to `state.fieldNotes`. The `observedAtTouched` flag is set by `wireObservedAtInput()` on both steps. The pin gets a reverse-geocoded label like a map click does (`fillLocationLabelFromPin()` when no map is on screen). `filledFromPhoto` drives the "filled in from your photo" hints, which clear once the user edits the date or moves the pin. Both the Describe-step photo path and Confirm's own photo picker use this. The identify photo's background upload ignores the metadata, since the identify response already applied it. |

The `dao/` layer is the right home even though nothing here makes a network
call. It's raw file-format parsing that services shouldn't touch, the same
way `bioclip_classifier.py` lives there.

## 6. Build order

Steps 1–5 are done. Tests: `test_photo_metadata.py`, new cases in
`test_uploads.py` and `test_identify.py`, and the shared image builder
`tests/photo_helpers.py`.

1. `app/dao/photo_metadata.py` with `read()` and `strip()`. Tests in
   `backend/tests/test_photo_metadata.py` build tiny images **in memory**
   with Pillow and write EXIF/GPS into them, so no fixture files are
   committed. Cover: N/E vs S/W signs, `0,0` treated as missing, no EXIF at
   all, `DateTime` present but `DateTimeOriginal` absent (must return no
   `taken_at`), and that `strip()` output has no EXIF **and** is
   correctly rotated.
2. Wire `strip()` into `app/services/uploads.py`. Extend `test_uploads.py`
   to check the bytes handed to the monkeypatched `storage.upload_object`
   contain no GPS.
3. Add `photo_metadata` to both response models and have both endpoints
   return it.
4. `identify_photo()` EXIF fallback for the regional pool. In tests, mock
   `_regional_candidates` and check it received the EXIF lat/lng when the form
   gave none, and the form values when both exist.
5. Frontend: the precedence rule, the `observedAtTouched` flag, the reverse
   geocode, and the inline note.
6. **Manual check on real devices** (iPhone Safari, Android Chrome, desktop):
   does GPS survive our file input? Write the result into §1's limits so UI
   copy doesn't over-promise.

## Related pages

- [Add Observation](add-observation.md): the When & Where and Confirm steps this pre-fills
- [Photo-based bird ID](bird-id.md): §9 explains why location makes photo ID better
- [Bulk photo import](bulk-import.md): builds on this; every imported photo goes through it
