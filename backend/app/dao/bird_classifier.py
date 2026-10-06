"""Local (self-hosted) photo classifier — no external network call per
request. See `docs/features/bird-id.md` for why this is self-hosted
(onnxruntime, no torch) instead of a third-party API.

The model (`dennisjooo/Birds-Classifier-EfficientNetB2`, Apache-2.0, 525
species) ships its own ready-to-run ONNX export on Hugging Face — no export
step was needed here, just a direct download, committed to
`app/data/bird_classifier.onnx`. Preprocessing below matches that model's
`preprocessor_config.json` exactly (resize 260x260 with PIL's NEAREST
filter — `resample: 0` — then `/255` rescale and the specific mean/std it
was trained with); confirmed end to end against a real photo (a Northern
Cardinal, correctly identified at 79% confidence) before this was wired up
any further.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.data.bird_classifier_labels import LABEL_TO_SPECIES, MODEL_LABELS

_MODEL_FILE = Path(__file__).resolve().parent.parent / "data" / "bird_classifier.onnx"
_INPUT_SIZE = 260
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.47853944, 0.4732864, 0.47434163], dtype=np.float32)

_session: ort.InferenceSession | None = None


def _get_session() -> ort.InferenceSession:
    # Lazy, module-level singleton — the first classify() call pays the
    # (~33 MB) model load, every call after reuses the same session. Not
    # loaded at import time so importing this module (e.g. in a test that
    # mocks classify() entirely) never touches the model file.
    global _session
    if _session is None:
        _session = ort.InferenceSession(str(_MODEL_FILE), providers=["CPUExecutionProvider"])
    return _session


def _preprocess(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((_INPUT_SIZE, _INPUT_SIZE), Image.NEAREST)
    arr = np.asarray(img).astype(np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    return arr.transpose(2, 0, 1)[None, ...]  # HWC -> CHW, add batch dim


def classify(image_bytes: bytes, top_k: int = 6) -> list[dict]:
    """Returns up to `top_k` `{scientific_name, common_name, species_code,
    confidence}` dicts, highest confidence first. Labels the model predicts
    with no crosswalk entry (`app/data/bird_classifier_labels.py` — ~18% of
    its 525, documented there) are skipped rather than surfaced with a
    missing/wrong species — so this walks the full ranked list rather than
    just the raw top `top_k` logits, to still return a full set most of the
    time.
    """
    session = _get_session()
    inputs = _preprocess(image_bytes)
    logits = session.run(None, {"pixel_values": inputs})[0][0]
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()

    ranked = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)

    out: list[dict] = []
    for i in ranked:
        species = LABEL_TO_SPECIES.get(MODEL_LABELS[i])
        if species is None:
            continue
        out.append({**species, "confidence": round(float(probs[i]), 4)})
        if len(out) >= top_k:
            break
    return out
