"""Describe & guess matching — no external CV/LLM call (descoped for MVP).

Two paths, both driven off the canned reference set in `app/data/birds.py`:

- **Named**: the free text names a species outright ("I saw a blue jay").
  We know the answer, so the six candidates are that species plus five
  visually-similar ones, and the eventual pick can be graded correct/incorrect.
- **Generic**: the text is vague ("small brown streaky bird"). We have no
  ground truth, so we just rank every species by how well its colour / size /
  habitat and name overlap the description and hints, and return the top six
  as suggestions.
"""

from __future__ import annotations

import asyncio
import re

from app.dao import bird_audio, bird_photos
from app.data.birds import all_birds, get_bird

_WORD_RE = re.compile(r"[a-z]+")

# Free text says "big," "marsh," "yard" — the data says "large," "wetland,"
# "backyard." Map common synonyms onto the vocabulary birds.py actually uses
# so a generic description matches on more than an exact word.
_SIZE_SYNONYMS = {
    "small": {"small", "little", "tiny", "petite"},
    "medium": {"medium", "mid", "midsize", "midsized"},
    "large": {"large", "big", "huge", "giant"},
}
_HABITAT_SYNONYMS = {
    "wetland": {"wetland", "marsh", "pond", "lake", "swamp", "river", "shore", "shoreline", "water"},
    "woodland": {"woodland", "forest", "woods", "trees"},
    "backyard": {"backyard", "yard", "garden", "feeder"},
    "grassland": {"grassland", "field", "prairie", "meadow", "open"},
    "urban": {"urban", "city", "downtown", "park", "street"},
}
_COLOR_ALIASES = {"grey": "gray"}


def _words(text: str) -> set[str]:
    found = _WORD_RE.findall(text.lower())
    return {_COLOR_ALIASES.get(w, w) for w in found}


def _matches_size(bird_size: str, tokens: set[str]) -> bool:
    return bool(tokens & _SIZE_SYNONYMS.get(bird_size, {bird_size}))


def _matching_habitats(bird_habitats: set[str], tokens: set[str]) -> int:
    return sum(1 for h in bird_habitats if tokens & _HABITAT_SYNONYMS.get(h, {h}))


def _find_named_species(text: str) -> dict | None:
    """A species whose common name appears in the text, longest name first
    so "steller's jay" wins over the more generic "jay"."""
    lowered = text.lower()
    matches = [b for b in all_birds() if b["common_name"].lower() in lowered]
    if not matches:
        return None
    return max(matches, key=lambda b: len(b["common_name"]))


def _fill_to_six(codes: list[str], exclude: set[str]) -> list[str]:
    """Top up a candidate list to 6 with the next-best species by group size,
    used when a species' own confusion group has fewer than 5 members."""
    for bird in all_birds():
        if len(codes) >= 6:
            break
        if bird["code"] not in exclude and bird["code"] not in codes:
            codes.append(bird["code"])
    return codes[:6]


def _candidates_for_named(matched: dict) -> list[dict]:
    codes = [matched["code"], *matched["similar"][:5]]
    codes = _fill_to_six(codes, exclude=set())

    out = []
    for i, code in enumerate(codes):
        bird = get_bird(code)
        # Deterministic descending confidence; the named match leads clearly.
        confidence = 0.86 if code == matched["code"] else round(0.6 - i * 0.09, 2)
        out.append({**bird, "confidence": max(confidence, 0.05)})
    return out


def _score_generic(bird: dict, tokens: set[str], hints: dict | None) -> float:
    score = 0.0
    name_words = _words(bird["common_name"]) | bird.get("keywords", set())
    score += 2.0 * len(tokens & name_words)
    score += 1.5 * len(tokens & bird["colors"])
    score += 1.0 * _matching_habitats(bird["habitat"], tokens)
    if _matches_size(bird["size"], tokens):
        score += 1.0

    if hints:
        if hints.get("color") and _COLOR_ALIASES.get(hints["color"].lower(), hints["color"].lower()) in bird["colors"]:
            score += 1.5
        if hints.get("size") and _matches_size(bird["size"], _words(hints["size"])):
            score += 1.0
        if hints.get("habitat") and _matching_habitats(bird["habitat"], _words(hints["habitat"])):
            score += 1.0
    return score


def _candidates_for_generic(text: str, hints: dict | None) -> list[dict]:
    tokens = _words(text)
    scored = [(b, _score_generic(b, tokens, hints)) for b in all_birds()]
    scored.sort(key=lambda pair: (-pair[1], pair[0]["code"]))

    top = scored[:6]
    max_score = max((s for _, s in top), default=0.0) or 1.0
    out = []
    for bird, score in top:
        # Spread confidences across a plausible band; no ground truth exists
        # for a generic description, so nothing here claims certainty.
        confidence = round(0.15 + 0.45 * (score / max_score), 2)
        out.append({**bird, "confidence": confidence})
    return out


async def _with_media(candidates: list[dict], sense: str) -> list[dict]:
    """Swaps each candidate's placeholder `photo_url` for a real one from
    Wikimedia Commons, if available (see `app/dao/bird_photos.py`), and
    attaches its attribution. When `sense == "sound"` (the user picked "I
    heard it"), also attaches a call/song recording where one exists
    (`app/dao/bird_audio.py`) — there's no placeholder for audio, so
    `audio_url` stays `None` for a species with no recording. Looked up
    concurrently since a describe call needs up to six of each."""
    photos = await asyncio.gather(*(bird_photos.get_photo(c) for c in candidates))
    out = [
        {**c, "photo_url": photo["photo_url"], "photo_attribution": photo["attribution"]}
        for c, photo in zip(candidates, photos)
    ]

    if sense != "sound":
        for row in out:
            row["audio_url"] = None
            row["audio_attribution"] = None
        return out

    audios = await asyncio.gather(*(bird_audio.get_audio(c) for c in candidates))
    for row, audio in zip(out, audios):
        row["audio_url"] = audio["audio_url"] if audio else None
        row["audio_attribution"] = audio["attribution"] if audio else None
    return out


async def describe(
    text: str, hints: dict | None = None, sense: str = "sight"
) -> tuple[list[dict], str | None]:
    """Returns (candidates, target_species_code). `target_species_code` is set
    only when the text named a species outright, so the confirm step can grade
    the user's pick against it. `sense` ("sight" | "sound") only changes which
    media the candidates carry — the matching/scoring logic is the same
    either way; see `docs/features/add-observation.md`."""
    matched = _find_named_species(text)
    if matched:
        candidates, target_code = _candidates_for_named(matched), matched["code"]
    else:
        candidates, target_code = _candidates_for_generic(text, hints), None
    return await _with_media(candidates, sense), target_code
