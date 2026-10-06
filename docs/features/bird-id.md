# Photo-based bird ID

> **Status:** Planned, scoped. Slots into the existing describe & guess flow
> rather than building a parallel one — `app/models/identification.py`'s own
> docstring already says this was designed for exactly this swap: "Computer
> vision is descoped for MVP... These models are shaped so that DAO can be
> swapped out later without touching the service or router layer." This page
> is that swap. See [§5](#5-how-the-code-is-layered) for how little of
> `app/services/identify.py` / `app/routers/identify.py` actually changes.

## 1. What you're building

A third way into the same candidate-picker flow [Add Observation](add-observation.md)
already has for "I saw it" (free text) and "I heard it" (free text): **"Upload
a photo."** Skips the text description entirely — upload a photo, get back
the same shape of ranked candidates (`IdentifyResponse`), pick one the same
way, same confirm step (`POST /identify/{id}/select`). Nothing downstream of
candidate selection changes at all.

Not a separate screen, not a separate model keyed differently — `method`
on `Identification`/`IdentifyResponse` grows a third value (`"photo"`,
alongside today's `"describe"`), same as `sense` already distinguishes
"sight" vs "sound" text.

### Why self-hosted, not a third-party API

Decided over chat: training our own classifier from scratch isn't realistic
(no labeled dataset, no GPU training infra — this would dwarf every other
feature in this app). A paid third-party endpoint (Hugging Face Inference
Endpoints) was the other option on the table but means a recurring $/month
bill for a beta feature and cold-start latency after idle. Landed on:
**run a pretrained, permissively-licensed open model ourselves**, via
`onnxruntime` (no `torch` — see §5's dependency note), same "lean on
existing free resources" posture as every other external data source in
this app.

**Model:** [`dennisjooo/Birds-Classifier-EfficientNetB2`](https://huggingface.co/dennisjooo/Birds-Classifier-EfficientNetB2)
— Apache-2.0, 525 species, trained on Kaggle's well-known "100 bird species"
dataset (its name predates its growth to 525 classes), decent North American
coverage. Not deployed on Hugging Face's free Inference Providers (confirmed
— its model page says so directly), so it's exported to ONNX and run
in-process instead of called over HTTP.

### What happens on upload

1. User picks/takes a photo (same `<input type="file">` + validation as
   `POST /uploads/photo` — JPEG/PNG/WebP/GIF, 8 MB max).
2. `POST /identify/photo` — the image is classified locally (no network
   call), top 6 labels by softmax confidence are mapped to this app's
   `scientific_name` identity (the label crosswalk — see §2) and hydrated
   with a stock photo/audio exactly like describe-flow candidates are
   (`bird_photos.get_photo()` / `bird_audio.get_audio()` — **reused
   unchanged**, not reimplemented).
3. Response is a normal `IdentifyResponse` (`method: "photo"`). The
   existing `CandidateList.js` picker renders it with zero changes — it
   already only cares about the `candidates` array's shape, not how it
   was produced.
4. Pick a candidate → existing `POST /identify/{id}/select` — unchanged.

### An honest limit worth stating in the UI

The model's 525 species is a fixed set baked in at export time — a vagrant
or regional specialty outside that set will never be the top (or any)
candidate, no matter how good the photo is. Unlike describe-flow's generic
path (which ranks *every* species in `app/data/birds.py`/the full taxonomy
and always returns *something*, just maybe low-confidence), a photo of a
species truly outside the model's 525 will return confidently-wrong
candidates — there's no "none of the above, for real" signal from softmax
alone. Worth a line of copy near the upload button ("best for common North
American species") rather than implying field-guide-grade coverage.

## 2. Where the data comes from and where it goes

| Data | Comes from | Stored where |
|---|---|---|
| The model itself | `dennisjooo/Birds-Classifier-EfficientNetB2` (Hugging Face), exported to ONNX once, committed to the repo | `backend/app/data/bird_classifier.onnx` (expect ~30-35 MB for an EfficientNetB2 ONNX export — small enough to commit directly; Render's filesystem is ephemeral per-deploy, so fetching it from object storage at startup would just be a slower version of the same thing) |
| Label → our identity crosswalk | The model's `id2label` (in its `config.json` on Hugging Face) matched against the `species` table's `common_name` | `backend/app/data/bird_classifier_labels.py` (**new**, static) — a plain dict, `{model_label: scientific_name}`. Built once during export (§6 step 1); **not every one of the 525 labels will auto-match** (Kaggle-dataset common names drift from eBird's — e.g. casing, "ROCK DOVE" vs eBird's "Rock Pigeon"). Auto-match on normalized (lowercased, punctuation-stripped) common name first; whatever doesn't match gets resolved by hand once, not re-derived per request. |
| Candidates' photo/audio | Wikimedia Commons, via existing `bird_photos.py`/`bird_audio.py` | their own existing caches — **zero new code** |
| The identification record | our own data | `identifications` table — **already supports this**, no migration (see `app/models/identification.py`'s docstring) |

No new external network call happens per classification — the whole point
of self-hosting is that inference is local CPU work, not a dependency on
another service's uptime.

## 3. Database changes (SQL)

**None.** `identifications.method` already exists as a plain column (see
`database.md`); it just gets a second value written to it (`"photo"`
alongside `"describe"`). No migration file for this feature.

## 4. API endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/identify/photo` | multipart `file` → `IdentifyResponse` (`method: "photo"`, `sense: "sight"` always, `candidates`). Same validation as `POST /uploads/photo` (type/size) — reuse `app/services/uploads.py`'s constants rather than redeclaring them. |
| `POST` | `/identify/{id}/select` | **unchanged** — already generic over `method`. |

No change to `IdentifyRequest`/`SelectCandidateRequest`/`SelectCandidateResponse`.
`IdentifyResponse.method` and `Identification.method` widen from
`Literal["describe"]` to `Literal["describe", "photo"]`.

### Example — `POST /identify/photo`

```json
{
  "identification_id": "id_8f2a1c",
  "method": "photo",
  "sense": "sight",
  "candidates": [
    {
      "species_code": "norcar",
      "common_name": "Northern Cardinal",
      "scientific_name": "Cardinalis cardinalis",
      "confidence": 0.94,
      "photo_url": "https://upload.wikimedia.org/...",
      "photo_attribution": "...",
      "audio_url": null,
      "audio_attribution": null
    }
  ]
}
```

Confidence here is the model's actual softmax probability — unlike
describe-flow's heuristic hand-tuned scores, this one means something
(though see §1's note on out-of-set species: a confident wrong answer is
still possible).

## 5. How the code is layered

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/bird_classifier.py` (**new**) | Loads the ONNX session once (module-level, lazy — first request pays the load cost, not every request); `classify(image_bytes) -> list[{label, confidence}]` — preprocess (resize/normalize to the model's expected input, confirmed during export), `session.run()`, softmax if not already applied, top 6 |
| `data/` | `app/data/bird_classifier_labels.py` (**new**) | The static label → `scientific_name` crosswalk (§2) |
| `services/` | `app/services/identify.py` (extend) | `identify_photo(image_bytes)` — mirrors `describe_bird()`: classify → look up each label's `scientific_name` in the crosswalk (skip any that don't resolve — see §2) → `Candidate`s via the same `_with_media`-equivalent photo/audio hydration describe already does → `identification_repo.add(method="photo", ...)` |
| `routers/` | `app/routers/identify.py` (extend) | `POST /identify/photo`, mirroring `POST /uploads/photo`'s file validation |
| `models/` | `app/models/identification.py` (extend) | widen the two `method` `Literal`s |
| `Dao/` | `frontend/src/Dao/identify.js` (extend) | `identifyPhoto(file)` — multipart, same pattern as `Dao/uploads.js` (**reuse its `BASE_URL` import**, don't redeclare it — see the fix in `apiClient.js`/`uploads.js` for exactly why a second hardcoded copy is a real bug, not a style nitpick) |
| `Services/` | `frontend/src/Services/identify.js` (extend) | validation mirroring `uploadsService` (type/size) before the network call |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` (extend) | a third option alongside "I saw it"/"I heard it" — "Upload a photo" — skips straight to the candidate-picker step, same `CandidateList.js` render |

**New backend dependency:** `onnxruntime` (CPU) + `Pillow` (image
preprocessing) + `numpy`. Deliberately **not** `torch`/`transformers` —
those pull in hundreds of MB to multiple GB, likely too heavy for Render's
plan; `onnxruntime`'s CPU wheel is tens of MB and doesn't need the original
training framework at all once the model's exported.

## 6. Build order

1. **Export the model to ONNX** (one-time, local, not part of the app's
   runtime) — pull `dennisjooo/Birds-Classifier-EfficientNetB2` from
   Hugging Face, confirm its actual input preprocessing (image size,
   normalization) from its `preprocessor_config.json`, export via
   `torch.onnx.export` (torch is fine as a one-time *export-tooling*
   dependency on a dev machine — it's the *runtime* dependency on Render
   this is avoiding), verify the ONNX output matches the original model's
   output on a few sample images before trusting it.
2. Build `app/data/bird_classifier_labels.py` from the model's `id2label` —
   auto-match against the `species` table's `common_name`, hand-resolve
   whatever doesn't match (expect this to be a real, non-trivial chunk of
   the 525 — budget time for it).
3. Commit the `.onnx` file to `backend/app/data/`.
4. `app/dao/bird_classifier.py` — load + `classify()`. Test directly
   against a couple of known sample images before wiring it any further.
5. Widen the two `method` `Literal`s in `app/models/identification.py`.
6. `app/services/identify.py#identify_photo()`.
7. `POST /identify/photo` route.
8. Tests: canned ONNX output (mock the dao's `classify()`, not the model
   itself — no test should actually run inference, same offline-tests
   rule as everything else, and a real model run is slow besides) → assert
   the assembled `IdentifyResponse` shape; assert a label with no crosswalk
   entry is skipped, not a 500.
9. Frontend: `Dao/identify.js` → `Services/identify.js` → the new
   "Upload a photo" entry point in `AddObservation.js`.

## Related pages

- [Add Observation](add-observation.md) — the flow this slots into
- [Bird information page](bird-info.md) — same `scientific_name` identity
  convention as the crosswalk here
- [Database & migrations](database.md)
