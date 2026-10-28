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
- **No embedding cache on disk.** Text embeddings are cached in memory
  **per species** (`_species_feature_cache`, keyed by species code) and
  computed in batches, so a new region/date only pays for species this
  process hasn't seen yet, instead of re-encoding its whole checklist (the
  original per-pool cache did that, which made every photo from a new
  place or day slow). Encoding the ~430-species default pool is the one
  big cost (~30s on a fast CPU, longer on Render), so the build step
  (`python -m app.dao.bioclip_classifier`) saves those embeddings to
  `_EMBEDDINGS_FILE` and `warm_up()` loads them at startup instead of
  recomputing (app/main.py runs it in a background thread).
- **Dependencies are heavy.** `torch` + `open_clip_torch` (`requirements.txt`
  — moved in from the now-removed `requirements-bioclip.txt` once this
  stopped being experimental) are exactly what `bird_classifier.py`'s
  choice of `onnxruntime` was meant to avoid. The ~570MB checkpoint
  downloads from Hugging Face on first use, unlike `bird_classifier.onnx`
  which is committed to the repo.
- **Memory:** loading the model needs well over 512MB. Confirmed live:
  Render's 512MB instances run out of memory on the first photo ID, so the
  backend needs a 2GB instance, or PHOTO_ID_ENABLED=false (app/config.py).
- **`classify()` is CPU-bound and blocking.** Callers must run it off the
  event loop (`asyncio.to_thread`, see app/services/identify.py), or one
  photo ID freezes every other request to the server while it runs.
"""

from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

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

logger = logging.getLogger(__name__)

# Precomputed default-pool embeddings, written by the build step (see
# `__main__` below). Next to the Hugging Face cache by default, so it lives
# wherever the model weights do; override with BIOCLIP_EMBEDDINGS_FILE.
_EMBEDDINGS_FILE = Path(
    os.environ.get("BIOCLIP_EMBEDDINGS_FILE")
    or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "bioclip_text_embeddings.pt"
)

# Texts per forward pass when encoding species names — batching is far
# faster than one encode_text() call per species on CPU.
_ENCODE_BATCH_TEXTS = 128

_lock = threading.Lock()
_model = None
_tokenizer = None
_preprocess = None

# species_code -> that species' normalized text embedding (1-D tensor).
# Per species, not per candidate pool, so overlapping pools (every region
# shares most of its birds with its neighbours and with the default pool)
# reuse each other's work. Unbounded, but tops out at the ~11k species in
# the eBird taxonomy (a few tens of MB).
_species_feature_cache: dict[str, torch.Tensor] = {}


def _get_model():
    global _model, _tokenizer, _preprocess
    if _model is None:
        with _lock:
            if _model is None:  # re-check inside the lock
                model, _, preprocess = open_clip.create_model_and_transforms(_MODEL_ID)
                model.eval()
                _model, _tokenizer, _preprocess = model, open_clip.get_tokenizer(_MODEL_ID), preprocess
    return _model, _tokenizer, _preprocess


def _dedupe(candidates: list[dict]) -> list[dict]:
    """First occurrence of each species code wins, order kept."""
    seen: set[str] = set()
    pool = []
    for c in candidates:
        if c["species_code"] not in seen:
            seen.add(c["species_code"])
            pool.append(c)
    return pool


def _encode_species(species_list: list[dict]) -> None:
    """Embed each species' name under every template, average the
    templates, and store one normalized vector per species. Same math as
    the original one-species-at-a-time loop, just batched."""
    model, tokenizer, _ = _get_model()
    texts = [t(s["common_name"]) for s in species_list for t in _TEMPLATES]
    chunks = []
    with torch.no_grad():
        for start in range(0, len(texts), _ENCODE_BATCH_TEXTS):
            emb = model.encode_text(tokenizer(texts[start:start + _ENCODE_BATCH_TEXTS]))
            chunks.append(F.normalize(emb, dim=-1))
    per_template = torch.cat(chunks).reshape(len(species_list), len(_TEMPLATES), -1)
    averaged = F.normalize(per_template.mean(dim=1), dim=-1)
    for species, emb in zip(species_list, averaged):
        _species_feature_cache[species["species_code"]] = emb


def _get_text_features(candidates: list[dict]) -> tuple[torch.Tensor, list[dict]]:
    """`(features, pool)`: `features` is `[dim, len(pool)]`, one column per
    species in `pool` (the deduped candidates). Only species not already
    cached get encoded."""
    pool = _dedupe(candidates)
    missing = [c for c in pool if c["species_code"] not in _species_feature_cache]
    if missing:
        with _lock:
            # Re-check inside the lock: another request may have encoded them.
            missing = [c for c in missing if c["species_code"] not in _species_feature_cache]
            if missing:
                _encode_species(missing)
    features = torch.stack([_species_feature_cache[c["species_code"]] for c in pool], dim=1)
    return features, pool


def _load_saved_embeddings() -> int:
    """Fill the cache from `_EMBEDDINGS_FILE` if it exists. Returns how many
    species it loaded (0 if there was no usable file)."""
    if not _EMBEDDINGS_FILE.exists():
        return 0
    try:
        saved = torch.load(_EMBEDDINGS_FILE, map_location="cpu")
    except Exception:  # noqa: BLE001 — a bad file just means recomputing
        logger.warning("Ignoring unreadable %s", _EMBEDDINGS_FILE)
        return 0
    if saved.get("model_id") != _MODEL_ID or saved.get("templates") != len(_TEMPLATES):
        return 0  # made by a different model/template set — recompute
    for code, emb in saved["embeddings"].items():
        _species_feature_cache.setdefault(code, emb)
    return len(saved["embeddings"])


def save_embeddings() -> None:
    """Write the currently cached embeddings to `_EMBEDDINGS_FILE`."""
    _EMBEDDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"model_id": _MODEL_ID, "templates": len(_TEMPLATES), "embeddings": dict(_species_feature_cache)},
        _EMBEDDINGS_FILE,
    )


def warm_up() -> None:
    """Load the model and the default pool's embeddings now, so the first
    photo ID doesn't pay for them: from `_EMBEDDINGS_FILE` when the build
    step saved one, otherwise by encoding (slow). Called in a background
    thread at startup (app/main.py); blocking, so never call it on the
    event loop."""
    _get_model()
    loaded = _load_saved_embeddings()
    _get_text_features(_DEFAULT_CANDIDATES)  # encodes only what wasn't loaded
    logger.info("Photo ID ready (%d species embeddings loaded from disk)", loaded)


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
    # Default pool first, regional extras after it (duplicates dropped).
    text_features, pool = _get_text_features(_DEFAULT_CANDIDATES + (candidates or []))

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")  # same orientation fix as bird_classifier.py
    tensor = preprocess(img).unsqueeze(0)

    with torch.no_grad():
        image_features = model.encode_image(tensor)
        image_features = F.normalize(image_features, dim=-1)
        probs = (100.0 * image_features @ text_features).softmax(dim=-1)[0]

    ranked = sorted(range(len(pool)), key=lambda i: -probs[i].item())[:top_k]
    return [{**pool[i], "confidence": round(probs[i].item(), 4)} for i in ranked]


if __name__ == "__main__":
    # `python -m app.dao.bioclip_classifier` — run at build time on Render:
    # downloads the model weights into the Hugging Face cache (HF_HOME) and
    # saves the default pool's embeddings, so a restart neither re-downloads
    # ~570MB nor re-encodes ~430 species names before the first photo ID.
    warm_up()
    save_embeddings()
    print(f"Saved {len(_species_feature_cache)} species embeddings to {_EMBEDDINGS_FILE}")
