"""Zero-shot photo classifier — replaces `bird_classifier.py`'s fixed
525-label model. See `docs/features/bird-id.md` §7/§9 for the full story;
short version here.

**Why this exists:** the previous model (`bird_classifier.py`, an
EfficientNetB2 fine-tune) has a 525-label head fixed at training time — a
species outside that set (confirmed: Green Heron) can never be the top
prediction, no matter the photo. BioCLIP (`imageomics/bioclip`, MIT, a
CLIP-style vision/text model trained on TreeOfLife-10M) has no fixed label
set — it embeds the photo and compares it against embeddings of whatever
species names it's handed at *inference* time. That's what `candidates`
below is for: `app/services/identify.py#identify_photo()` passes the real
eBird checklist for the photo's region/day when it has one (built from the
same `get_historic_checklist()` call §8's regional reorder already made for
describe-flow — see `_regional_candidates()` there). Those get **added to**
`_DEFAULT_CANDIDATES`, not used instead of it — see `classify()`'s
docstring for why the first version of this (region replacing the default
pool) was a confirmed-live regression, not just a theoretical risk.

**Confirmed against the real Green Heron photo that started this
investigation:** ranked #1 of 431 at 99.97% against the same realistic-scale
candidate pool `bird_classifier_labels.py` already used (not a toy 8-way
test) — see `docs/features/bird-id.md` §9 for the full experiment notes,
including a live run through this exact module via `POST /identify/photo`.

**What's still a known gap, not solved here:**

- **The default pool (always included, and the only pool when no
  location/date is given) is still the old 430-name crosswalk plus a short
  hand-added list (`_EXTRA_SPECIES`).** A region's checklist only ever adds
  to this, so a user who skips the optional When & Where step is back to
  the old model's structural ceiling, just with a couple of proven
  exceptions tacked on — giving a location is what actually broadens
  coverage, not using this module instead of the old one by itself.
- **No embedding cache on disk.** Each unique candidate pool's text
  embeddings are computed once per process (`_text_feature_cache`, keyed by
  the pool's species codes) and kept in memory — fine for a handful of
  regions in one running process, not yet suited to many regions across
  restarts or multiple instances. Encoding ~430 names took ~30s on CPU in
  testing; a region's checklist is typically much smaller (dozens to low
  hundreds), so per-region cold cache misses are cheaper than that, but
  still real latency on a region's first request.
- **Dependencies are heavy.** `torch` + `open_clip_torch` (`requirements.txt`
  — moved in from the now-removed `requirements-bioclip.txt` once this
  stopped being experimental) are exactly what `bird_classifier.py`'s
  choice of `onnxruntime` was meant to avoid. The ~570MB checkpoint
  downloads from Hugging Face on first use, unlike `bird_classifier.onnx`
  which is committed to the repo.
- **Render's free tier is still unconfirmed** for this memory/dependency
  footprint — see `bird-id.md` §7's original concern. Not resolved by any
  of the above.
"""

from __future__ import annotations

import io
import threading

import open_clip
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from app.data.bird_classifier_labels import LABEL_TO_SPECIES

_MODEL_ID = "hf-hub:imageomics/bioclip"

# The no-location fallback pool: the existing crosswalk, plus species
# confirmed missing from it by hand (see module docstring — this list
# doesn't grow without someone hitting the gap and checking, same as
# bird_classifier_labels.py's own crosswalk gaps).
_EXTRA_SPECIES = [
    {"scientific_name": "Butorides virescens", "common_name": "Green Heron", "species_code": "greeheron"},
]
_DEFAULT_CANDIDATES = list(LABEL_TO_SPECIES.values()) + _EXTRA_SPECIES

_TEMPLATES = [
    lambda c: f"a photo of a {c}.",
    lambda c: f"a photo of a {c}, a type of bird.",
]

_lock = threading.Lock()
_model = None
_tokenizer = None
_preprocess = None

# Keyed by a stable identity for the candidate pool (its species codes,
# joined) so a region's checklist and the default pool each get their own
# cached embeddings instead of recomputing per request. Unbounded for now —
# acceptable for the handful of regions one process sees in practice; see
# module docstring's "no embedding cache on disk" note for the real limit.
_text_feature_cache: dict[str, torch.Tensor] = {}
_candidate_list_cache: dict[str, list[dict]] = {}


def _get_model():
    global _model, _tokenizer, _preprocess
    if _model is None:
        with _lock:
            if _model is None:  # re-check inside the lock
                model, _, preprocess = open_clip.create_model_and_transforms(_MODEL_ID)
                model.eval()
                _model, _tokenizer, _preprocess = model, open_clip.get_tokenizer(_MODEL_ID), preprocess
    return _model, _tokenizer, _preprocess


def _pool_key(candidates: list[dict]) -> str:
    return "|".join(c["species_code"] for c in candidates)


def _get_text_features(candidates: list[dict]) -> tuple[torch.Tensor, list[dict]]:
    """Lazy, per-pool singleton — same reasoning as
    `bird_classifier.py#_get_session()`: pay the embedding cost once per
    distinct candidate pool, not per request."""
    key = _pool_key(candidates)
    if key not in _text_feature_cache:
        with _lock:
            if key not in _text_feature_cache:
                model, tokenizer, _ = _get_model()
                with torch.no_grad():
                    embeddings = []
                    for species in candidates:
                        texts = tokenizer([t(species["common_name"]) for t in _TEMPLATES])
                        emb = model.encode_text(texts)
                        emb = F.normalize(emb, dim=-1).mean(dim=0)
                        embeddings.append(emb / emb.norm())
                    _text_feature_cache[key] = torch.stack(embeddings, dim=1)
                    _candidate_list_cache[key] = candidates
    return _text_feature_cache[key], _candidate_list_cache[key]


def classify(image_bytes: bytes, top_k: int = 6, candidates: list[dict] | None = None) -> list[dict]:
    """Same return shape as the old `bird_classifier.classify()` —
    `{scientific_name, common_name, species_code, confidence}` dicts,
    highest confidence first.

    `candidates` (optional): `{scientific_name, common_name, species_code}`
    dicts — typically a region's real eBird checklist
    (`app/services/identify.py#_regional_candidates()`) — **added to**
    `_DEFAULT_CANDIDATES`, not used instead of it.

    This was tried the other way first (region checklist *replacing* the
    default pool) and confirmed live to be a real regression, not just a
    theoretical one: a Green Heron photo, given real North Carolina
    coordinates and date, lost to Great Blue Heron — not because the photo
    was ambiguous, but because that one county's one day's checklist (88
    species) genuinely didn't include Green Heron, a real local species
    nobody happened to log that day. A single day's regional checklist is a
    real signal but an incomplete one — exactly the same "absence isn't
    disqualifying" reasoning `app/services/identify.py#_regional_checklist()`
    already applies to describe-flow's reorder, which this now matches:
    region data can only ever add candidates here, never remove the
    default pool's.
    """
    model, _, preprocess = _get_model()
    default_features, default_pool = _get_text_features(_DEFAULT_CANDIDATES)

    if candidates:
        default_codes = {c["species_code"] for c in default_pool}
        extra = [c for c in candidates if c["species_code"] not in default_codes]
        if extra:
            extra_features, extra_pool = _get_text_features(extra)
            text_features = torch.cat([default_features, extra_features], dim=1)
            pool = default_pool + extra_pool
        else:
            text_features, pool = default_features, default_pool
    else:
        text_features, pool = default_features, default_pool

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")  # same orientation fix as bird_classifier.py
    tensor = preprocess(img).unsqueeze(0)

    with torch.no_grad():
        image_features = model.encode_image(tensor)
        image_features = F.normalize(image_features, dim=-1)
        probs = (100.0 * image_features @ text_features).softmax(dim=-1)[0]

    ranked = sorted(range(len(pool)), key=lambda i: -probs[i].item())[:top_k]
    return [{**pool[i], "confidence": round(probs[i].item(), 4)} for i in ranked]
