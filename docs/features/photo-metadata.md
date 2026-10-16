# Photo location & date (EXIF)

> **Status:** Planned, scoped — docs only, nothing built yet. Nothing here
> needs a migration. [Bulk photo import](bulk-import.md) depends on it, so
> build this first.

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

On the backend, `identify_photo()` uses the same rule. Form `lat`/`lng`/
`observed_at` win, and EXIF values are only the fallback for building the
regional pool.

### What counts as "usable" metadata

- **GPS:** `GPSLatitude`/`GPSLongitude` plus their `N/S`/`E/W` refs, in the
  GPS IFD. Treat exactly `0, 0` as missing; it's a common bad-default value.
  Reject anything outside ±90/±180.
- **Capture time:** `DateTimeOriginal` (Exif IFD) only. **Do not** fall back
  to the base `DateTime` tag, because that's the last-modified time and an
  edited photo would report the edit date. If `OffsetTimeOriginal` is present,
  keep it, but the value goes into a `datetime-local` field as the
  **photo's local wall-clock time**. That's what the user would type anyway.
  No timezone conversion.
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
- **HEIC** (iPhone's native format) is not in `ALLOWED_CONTENT_TYPES`. iOS
  Safari usually converts to JPEG when picking from the photo library, but a
  `.heic` file dragged in on a desktop is rejected today. Out of scope here.
  See the open questions in [Bulk photo import](bulk-import.md), where it
  matters more.

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
| `POST` | `/uploads/photo` | Response gains the same `photo_metadata`. The stored object is re-saved without metadata (see §5). The `400`/`503` behavior is unchanged. |

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
| `dao/` | `app/dao/photo_metadata.py` (**new**) | Pure functions, no network. `read(image_bytes) -> {lat, lng, taken_at}` converts the GPS degree/minute/second rationals to decimal and applies the N/S/E/W sign. `strip(image_bytes, content_type) -> bytes` applies `ImageOps.exif_transpose()` **first**, so the stored copy keeps its correct rotation once the orientation tag is gone (same bug class as bird-id.md §1), then re-encodes without `exif`/`xmp`. JPEG at quality ~90; PNG and WebP losslessly where possible; GIF passed through untouched (no EXIF, and re-encoding would drop animation frames). |
| `models/` | `app/models/upload.py`, `app/models/identification.py` (extend) | A `PhotoMetadata` model; add an optional `photo_metadata` to `PhotoUploadResponse` and `IdentifyResponse` |
| `services/` | `app/services/uploads.py` (extend) | `read` → `strip` → `storage.upload_object`; returns the URL + metadata |
| `services/` | `app/services/identify.py` (extend) | `identify_photo()` calls `photo_metadata.read()` and falls back to its values for `_regional_candidates()` when the form fields are missing |
| `Services/` | `frontend/src/Services/identify.js`, `Services/uploads.js` (extend) | pass `photo_metadata` through |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` (extend) | Apply the §1 precedence rule to `state.fieldNotes`. Add the `observedAtTouched` flag. Reverse-geocode the pin for a label like a map click does. Show the "filled in from your photo" note. Both the Describe-step photo path and Confirm's own photo input use this. |

The `dao/` layer is the right home even though nothing here makes a network
call. It's raw file-format parsing that services shouldn't touch, the same
way `bioclip_classifier.py` lives there.

## 6. Build order

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
