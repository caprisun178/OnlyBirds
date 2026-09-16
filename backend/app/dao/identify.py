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

import re

from app.data.birds import all_birds, get_bird

_WORD_RE = re.compile(r"[a-z]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


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
    name_words = _words(bird["common_name"])
    score += 2.0 * len(tokens & name_words)
    score += 1.5 * len(tokens & bird["colors"])
    score += 1.0 * len(tokens & bird["habitat"])
    if bird["size"] in tokens:
        score += 1.0

    if hints:
        if hints.get("color") and hints["color"].lower() in bird["colors"]:
            score += 1.5
        if hints.get("size") and hints["size"].lower() == bird["size"]:
            score += 1.0
        if hints.get("habitat") and hints["habitat"].lower() in bird["habitat"]:
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


def describe(text: str, hints: dict | None = None) -> tuple[list[dict], str | None]:
    """Returns (candidates, target_species_code). `target_species_code` is set
    only when the text named a species outright, so the confirm step can grade
    the user's pick against it."""
    matched = _find_named_species(text)
    if matched:
        return _candidates_for_named(matched), matched["code"]
    return _candidates_for_generic(text, hints), None
