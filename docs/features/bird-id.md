# Photo-based bird ID

> **Status:** **Completed and live** — `POST /identify/photo` and the
> "Upload a photo" entry point in `AddObservation.js` are built and working
> end to end. The model behind it has changed twice since this page was
> first written: a real bug from a Green Heron upload (missing EXIF
> orientation handling) was **fixed** (§1), and the underlying 525-species
> classifier that bug partly exposed has since been **replaced entirely**
> by BioCLIP, a zero-shot model with no fixed label set — see
> [§9](#9-bioclip-replacing-the-525-label-model) for why and what changed.
> §1's model description is now historical (marked inline); §8 still
> describes live behavior, but for describe-flow only — photo-flow's
> regional handling moved to §9's richer mechanism after a live regression
> §9 documents in full.

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

> **Superseded — see [§9](#9-bioclip-replacing-the-525-label-model).** The
> rest of this subsection (§1's original model choice) is kept for the
> history — why self-hosting over a paid API was right, and still is — but
> `dennisjooo/Birds-Classifier-EfficientNetB2` itself is no longer what
> `POST /identify/photo` runs. §9 covers what replaced it and why.

**Model (original, now replaced — see above):** [`dennisjooo/Birds-Classifier-EfficientNetB2`](https://huggingface.co/dennisjooo/Birds-Classifier-EfficientNetB2)
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

**Confirmed, not just theoretical — but the story turned out to be two
separate bugs, not one.** A real upload of a Green Heron came back with
six completely unrelated species (a grouse, an African lapwing, a goshawk,
a falcon, a crane, an Australian honeyeater) at collapsing, near-0%
confidence — not the "confidently near-right" failure mode this section
originally predicted. Reproducing it directly against
`app/dao/bird_classifier.py#classify()` (bypassing the HTTP layer) found
two independent things:

1. **A real bug, now fixed:** `_preprocess()` never called
   `ImageOps.exif_transpose()`. Phone photos routinely store orientation as
   EXIF metadata rather than rotating the pixel data — fed in unrotated,
   the model sees the bird sideways or upside down. Confirmed directly:
   the exact same photo, correctly oriented, puts four herons/wading birds
   in the top 4 (Great Blue Heron 47%, Squacco Heron 18%, Crane Hawk 9%,
   Chinese Pond-Heron 8%); rotated 90° with nothing else changed, the top
   result becomes Vulturine Guineafowl at 77% — the same
   "wildly-unrelated-species, cascading-to-0%" pattern as the real report.
   This is very likely what actually happened. Fixed in
   `app/dao/bird_classifier.py#_preprocess()` — one `exif_transpose()`
   call before resizing.
2. **The coverage gap is still real, just less catastrophic than
   expected:** even on a correctly-oriented photo, Green Heron itself
   never appears — it's genuinely not one of the model's 525 labels (no
   `GREEN HERON` entry anywhere in `app/data/bird_classifier_labels.py`,
   confirmed). But the degradation is graceful, not nonsensical: the top
   candidate is Great Blue Heron, a real relative, at real confidence —
   exactly the "confidently-wrong-but-plausible" failure mode this section
   already described, not random noise. The UI changes already made
   (confidence numbers, the photo-flow warning banner, the "None of these
   match" fallback) are aimed at *this* failure mode. §7 covers what
   actually widening the 525 would take, if that gap is worth closing
   beyond "the UI makes a wrong guess easy to reject."

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
| `POST` | `/identify/photo` | multipart `file` (+ optional `lat`, `lng`, `observed_at` form fields) → `IdentifyResponse` (`method: "photo"`, `sense: "sight"` always, `candidates`). Same validation as `POST /uploads/photo` (type/size) — reuse `app/services/uploads.py`'s constants rather than redeclaring them. |
| `POST` | `/identify/{id}/select` | **unchanged** — already generic over `method`. |

`IdentifyResponse.method` and `Identification.method` widen from
`Literal["describe"]` to `Literal["describe", "photo"]`.

**`lat`/`lng`/`observed_at` (both endpoints, all optional):** implemented —
see §8. `IdentifyRequest` (the describe-flow body) gained the same three
fields. All-or-nothing in practice: given without each other, or when the
region/checklist lookup fails, they're simply ignored rather than erroring —
identification works exactly as before with none of them set.

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

> Historical — describes the original ONNX/EfficientNetB2 build. The `dao/`
> row changed with [§9](#9-bioclip-replacing-the-525-label-model)
> (`bird_classifier.py` → `bioclip_classifier.py`); everything else in this
> table is still accurate.

| Layer | File | Responsibility |
|---|---|---|
| `dao/` | `app/dao/bird_classifier.py` (**new**, superseded — see §9) | Loads the ONNX session once (module-level, lazy — first request pays the load cost, not every request); `classify(image_bytes) -> list[{label, confidence}]` — preprocess (resize/normalize to the model's expected input, confirmed during export), `session.run()`, softmax if not already applied, top 6 |
| `data/` | `app/data/bird_classifier_labels.py` (**new**, still used — now `bioclip_classifier.DEFAULT_CANDIDATES`' source) | The static label → `scientific_name` crosswalk (§2) |
| `services/` | `app/services/identify.py` (extend) | `identify_photo(image_bytes)` — mirrors `describe_bird()`: classify → look up each label's `scientific_name` in the crosswalk (skip any that don't resolve — see §2) → `Candidate`s via the same `_with_media`-equivalent photo/audio hydration describe already does → `identification_repo.add(method="photo", ...)` |
| `routers/` | `app/routers/identify.py` (extend) | `POST /identify/photo`, mirroring `POST /uploads/photo`'s file validation |
| `models/` | `app/models/identification.py` (extend) | widen the two `method` `Literal`s |
| `Dao/` | `frontend/src/Dao/identify.js` (extend) | `identifyPhoto(file)` — multipart, same pattern as `Dao/uploads.js` (**reuse its `BASE_URL` import**, don't redeclare it — see the fix in `apiClient.js`/`uploads.js` for exactly why a second hardcoded copy is a real bug, not a style nitpick) |
| `Services/` | `frontend/src/Services/identify.js` (extend) | validation mirroring `uploadsService` (type/size) before the network call |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` (extend) | a third option alongside "I saw it"/"I heard it" — "Upload a photo" — skips straight to the candidate-picker step, same `CandidateList.js` render |

**Original dependency choice (historical):** `onnxruntime` (CPU) + `Pillow`
+ `numpy`, deliberately not `torch`/`transformers` for size reasons — see
[§9](#9-bioclip-replacing-the-525-label-model) for why `torch` +
`open_clip_torch` were added anyway once BioCLIP replaced this model, and
what that tradeoff actually costs.

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

## 7. Widening coverage beyond the 525 (planned, not started)

The 525-species ceiling is a property of *this specific model's* fixed
output layer, not something tunable without swapping the model. Researched
two ways out; one is ruled out, the other is real but not free.

### Ruled out: iNaturalist's computer vision API

Their species-from-photo model (what their own app uses) is not a public
API — confirmed current as of this research: it's undocumented, and
iNaturalist has only granted fee-based access to a small number of
outside orgs on request. That reopens exactly the tradeoff already
rejected in §1 ("Why self-hosted, not a third-party API") — a recurring
bill and a dependency on someone else's uptime for a beta feature — so
this isn't a live option unless that earlier decision gets revisited for
other reasons too.

### Real option: BioCLIP (open, MIT-licensed) — but not a drop-in

[BioCLIP](https://huggingface.co/imageomics/bioclip) is a CLIP-style
vision-language model (Imageomics Institute, ViT-B/16, fine-tuned from
OpenAI's CLIP) trained on 10M+ images across 450,000+ taxa — birds, yes,
but also everything else in the tree of life. Confirmed MIT-licensed, so
no licensing blocker like Cornell's data.

The reason this would actually fix the problem, not just enlarge it:
BioCLIP classifies **zero-shot** — it embeds the photo and compares it
against embeddings of whatever species names you hand it, rather than
predicting from a label set baked in at training time. Pointed at this
app's own `species` table (the full eBird taxonomy, already loaded for
Life List) instead of a fixed 525-label head, coverage would stop being
"whatever this one Kaggle dataset happened to include" and become
"whatever species this app already knows about" — Green Heron included,
since it's already an eBird species. This is a structural fix to the
problem in §1, not a bigger patch over it.

**What it would actually cost, confirmed:**

- The checkpoint (`open_clip_pytorch_model.bin`) is **~571 MB** (checked
  directly via Hugging Face's API) — over 15x the current ~30-35 MB ONNX
  file, and bigger than Render's **free-tier** instance has RAM for at all
  (`render.yaml` currently runs this service on `plan: free`). This alone
  means the free tier stops being an option for this feature if BioCLIP
  goes in as-is.
- It's distributed as an OpenCLIP/PyTorch checkpoint, not ONNX. Running it
  as shipped means adding `torch` + `open_clip_torch` — precisely the
  "hundreds of MB to multiple GB" runtime dependency §5 deliberately chose
  `onnxruntime` to avoid. An ONNX export (same approach already used for
  the current model, §6 step 1) is possible in principle but is its own
  unverified chunk of work — CLIP's dual image/text encoder structure
  doesn't export as simply as a single-head classifier like
  EfficientNetB2 did.
- Text-side embeddings (one per candidate species name) can be precomputed
  once, offline, and shipped as a small static file — that part doesn't
  cost anything per request. The image encoder is the one actually running
  per upload, and is a comparable compute class to the current
  EfficientNetB2 (both mid-size CPU-inference vision models), so latency
  isn't expected to be the blocker — memory footprint is.
- There are newer, larger successors (BioCLIP 2, BioCLIP 2.5) with better
  accuracy, but bigger checkpoints still — original BioCLIP (ViT-B/16) is
  the realistic candidate for a CPU/free-tier-adjacent budget, not the
  newer "Huge" variants.

**This is a cost/benefit call, not a code task to just start on:** it
trades "Green Heron (and anything else outside the 525) actually
identifies correctly" against "heavier dependencies, a bigger deploy, and
likely a paid Render plan instead of free." Worth deciding deliberately —
same as §1's original self-hosted-vs-API call — rather than defaulting
into it. If the §1/§3 UI fixes (confidence numbers, the photo-flow warning
banner, the existing manual-search fallback) are enough to make the
525-species limit a minor annoyance instead of a trust problem, that may
be the better use of effort for now.

If this does move forward, the shape of the work is: (1) confirm an ONNX
export path for BioCLIP's image encoder (or accept the `torch` runtime
dependency and a paid plan), (2) precompute and ship text embeddings for
every species in the `species` table, (3) replace
`bird_classifier.py#classify()`'s body (same function signature — nothing
above it in `services/identify.py` needs to change) with an embedding
similarity lookup instead of a softmax over a fixed label list, (4) drop
`bird_classifier_labels.py`'s crosswalk entirely — zero-shot against our
own `species` table's identities makes the whole "model label doesn't
match our label" problem disappear along with the coverage gap.

## 8. Regional plausibility reorder (implemented — describe-flow only)

> **Scope correction:** this section originally covered both describe-flow
> and photo-flow — they used the same reorder mechanism when first built.
> Photo-flow's version was superseded by [§9](#9-bioclip-replacing-the-525-label-model)'s
> candidate-pool merge, which replaced the model entirely and needed a
> different (safer — see §9's regression writeup) approach to using
> regional data. Everything below describes **describe-flow's generic
> (no-named-target) path only**, which still works exactly as written here.

A smaller, already-built mitigation for the same gap §7 is scoped to fix
properly — this doesn't touch describe-flow's matching logic or ranking
scheme at all, it just reorders what that text matcher already returns,
using data this app already had a DAO for.

**Why this exists:** the garbage results that led to this whole page's §1
rewrite had a second cause beyond the EXIF bug — several candidates were
real species, just ones with no plausible connection to where the photo was
actually taken (an African lapwing, an Australian honeyeater). The model
has no idea where in the world the photo was taken; it ranks purely on
visual similarity across all 525 species globally.

**What it does:** [Add Observation](add-observation.md)'s wizard now
collects date/location *first* (its own "When & where" step, before
identification — see that page's flow diagram), instead of after, in Field
Notes. When both are given, `app/services/identify.py` calls
`ebird.region_for_point(lat, lng)` then `ebird.get_historic_checklist()`
(both already built for [Plan a Trip](plan-a-trip.md)) to get every species
eBird recorded in that region on that calendar day, and **reorders**
describe-flow's generic-path candidates toward that set — species confirmed
for the region/day move to the front; everything else follows in its
original order. It never *drops* a candidate: one day's regional checklist
is a real signal but an incomplete one (a common resident can go unreported
on any given day), so treating absence as "ruled out" would sometimes
demote a correct species for a data gap, not a real implausibility (§9
found a live, concrete case of exactly this when photo-flow's first version
tried using a checklist *exclusively* — worth reading if touching this
logic again).

**Deliberately not applied to describe-flow's named-match path:** when the
free text names a species outright ("I saw a Blue Jay"), that candidate is
already graded against a known target at real confidence
(`target_species_code`, §1 of `add-observation.md`) — reordering it by an
incomplete regional checklist could demote a *correct* named match for a
data gap, which would make the feature actively harmful there. The reorder
only ever applies to describe-flow's generic (no named target) path.

**Where it lives:**

| Layer | File | What changed |
|---|---|---|
| `services/` | `app/services/identify.py` | `_regional_checklist()` (shared eBird fetch, degrades to `None` on any failure — never blocks identification), `_regional_species_codes()` (the set this section's reorder uses), and `_reorder_by_region()` (the stable partition) — all used by `describe_bird()` only; `identify_photo()` uses `_regional_candidates()` instead, see §9 |
| `dao/` | `app/dao/identify.py` | `describe()` split into `get_candidates()` (matching/scoring, no media) and `attach_media()` (the old back half) — so the service can reorder/trim *before* paying for photo/audio lookups, not after |
| `models/` | `app/models/identification.py` | `IdentifyRequest` gained optional `lat`/`lng`/`observed_at` |
| `routers/` | `app/routers/identify.py` | `/identify/photo` gained the same three as optional multipart form fields |
| `Presenters/` | `frontend/src/Presenters/AddObservation.js` | new `STEP.WHEN_WHERE` (first step); carries its values into both the identify calls and, read-only, into Field Notes |
| `Services/`, `Dao/` | `frontend/src/{Services,Dao}/identify.js` | `location`/`regional` param threaded through to the request |

Tests: `backend/tests/test_identify.py`'s `test_describe_generic_reorders_toward_regional_species`
and `test_describe_named_match_is_never_reordered_by_region` cover the
reorder, the no-drop guarantee, and the named-path exclusion, via
`monkeypatch` on `ebird.region_for_point`/`get_historic_checklist` — no live
network call in the suite. (Photo-flow's equivalent tests were rewritten for
§9's different mechanism — see that section.)

## 9. BioCLIP: replacing the 525-label model

§7 scoped this without building it (cost/benefit call, not a code task —
see that section). This branch being explicitly experimental, it went
further: built, tested against progressively more realistic conditions,
caught a real regression along the way, fixed it, and shipped. As of this
section, `POST /identify/photo` runs on `app/dao/bioclip_classifier.py`
(BioCLIP, zero-shot) — `app/dao/bird_classifier.py` (the old
EfficientNetB2 model) is no longer imported anywhere, though the file is
left in place rather than deleted, in case this ever needs reverting.

### What changed, functionally

- **No fixed label set.** The old model could never return a species
  outside its 525 training labels, period. BioCLIP embeds the photo and
  compares it against embeddings of whatever species names it's handed at
  inference time — there's no training-time ceiling to hit.
- **The candidate pool is now two layers, not one:** a default pool
  (`bioclip_classifier.DEFAULT_CANDIDATES` — the same ~430-name crosswalk
  the old model used, plus a short hand-confirmed list of species known to
  be missing from it) that's always included, plus — when the user gave a
  location and date in the When & Where step — that region's real eBird
  checklist for that day, **added to** the default pool, never replacing
  it. `app/services/identify.py#identify_photo()` builds the regional half
  (`_regional_candidates()`); `bioclip_classifier.classify()` does the
  merge.

### Why "added to, never replacing" — a confirmed regression, not a guess

The first working version did the simpler thing: when a location/date was
given, the region's checklist *was* the whole candidate pool. That tested
fine against curated cases, then failed on a real one: the same Green Heron
photo, given real North Carolina coordinates and a real date, lost to
**Great Blue Heron**. Checked why directly against the live eBird API — that
county's checklist for that specific day had 88 species on it, and Green
Heron, a real resident there, simply wasn't one of them; nobody happened to
log it that day. A single day's regional checklist is a real signal but an
incomplete one — exactly the reasoning §8's describe-flow reorder already
built in (absence isn't disqualifying) — and using it as the *entire* pool
for photo-ID threw that principle away. Fixed by having
`bioclip_classifier.classify()` always start from its default pool and
union in whatever the region adds, deduplicated by species code; re-ran the
identical North Carolina request afterward and Green Heron was back on top
at 99.97%. Both the regression and the fix are from live runs against the
real eBird API, not mocked tests.

### What was tested, and the result

Same real Green Heron photo throughout:

| Test | Candidate pool | Result |
|---|---|---|
| Toy sanity check | 8 hand-picked species | Green Heron, 99.97% |
| Realistic scale | The full 431-name default pool (no location given) | **Green Heron, rank 1 of 431, 99.97%** — next 5 are all real relatives (American Bittern, Great Blue Heron, Chinese Pond-Heron, Squacco Heron, Anhinga), zero unrelated-species noise |
| Live, real region, first attempt | Default pool *replaced* by a real North Carolina checklist (88 species) | **Regression:** Great Blue Heron wins — Green Heron wasn't on that day's checklist |
| Live, real region, after the fix | Default pool + that same checklist, merged | Green Heron back to 99.97% — confirms the merge doesn't just avoid the regression, it fully recovers the original result |

This directly answers §7's open question: BioCLIP's zero-shot matching
measurably wins on the exact case that started this whole investigation, at
a candidate-pool scale matching real usage — and the region-scoping idea
from §8 generalizes to photo-ID too, once it respects the same
"real-but-incomplete-data" caution §8 was already written around.

**Performance, measured, not assumed:** cold start (model load + embedding
the ~430-name default pool): ~35-40s. A region's checklist adds only its
*new* species to that (most common ones are already in the default pool),
so a region's own first request is cheaper than the initial cold start, not
an equally expensive repeat of it. Every request after the relevant
pool(s) are warm: ~0.4s — in the same ballpark as the old ONNX model.

### What's still a known gap, not solved here

- **The default pool is still the old 430-name crosswalk plus a short
  hand-added list.** A user who skips the optional When & Where step gets
  only this pool — the old model's structural ceiling, with a couple of
  proven exceptions tacked on. Giving a location is what actually broadens
  coverage.
- **No embedding cache on disk.** Each distinct pool's embeddings are kept
  in memory per-process (`bioclip_classifier._text_feature_cache`), not
  persisted — fine for the handful of regions one process sees, not yet
  suited to many regions across restarts or multiple instances.
- **Render's free tier is still unconfirmed** for this dependency/memory
  footprint — §7's original concern, unchanged by any of this.
- **No ONNX export attempted** — runs as plain PyTorch/open_clip, the way
  its own example code does. §7 flagged this as "unverified... CLIP's dual
  image/text encoder structure doesn't export as simply" — still true.
- **Tests mock `bioclip_classifier.classify()` directly** (same
  offline-tests rule as the old model — no test runs real inference), so
  the merge-with-default logic itself isn't covered by the automated suite,
  only by the live runs documented above. Worth a lower-level unit test
  later if this code changes again.

## Related pages

- [Add Observation](add-observation.md) — the flow this slots into
- [Bird information page](bird-info.md) — same `scientific_name` identity
  convention as the crosswalk here
- [Database & migrations](database.md)
