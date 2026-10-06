"""Test Your Skill — a no-persistence photo/sound quiz. See
docs/features/test-your-skill.md.

Pulls from the real eBird taxonomy via `app/dao/region_repo.py#get_checklist()`
— already built and cached for Life List's region completion view — rather
than a small hand-curated set, so the quiz can offer genuine region and
taxonomic-family filters ("New World Warblers," "Crows, Jays, and Magpies,"
"Owls," ...) instead of the original MVP's dozen color-based "looks like
this" groups. `region_code="world"` (confirmed live: eBird accepts it,
~10,800 species, ~4-5s cold / instant cached) is the unfiltered "any and all
birds" default. Media still comes entirely from the already-built
`bird_photos.py`/`bird_audio.py` Commons lookups — no new external
integration, same as the original version of this file.
"""

from __future__ import annotations

import random
from typing import Literal

from app.dao import bird_audio, bird_photos, region_repo

QuizMode = Literal["photo", "audio"]

DEFAULT_REGION = "world"
_CHOICE_COUNT = 4
# Calibrated live: a random sample of 30 species from the *world* pool
# (deliberately including obscure, non-North-American birds) had real
# Commons photos 21/30 of the time (~70%). At that rate, 12 attempts fails
# to find any usable species with probability ~0.3^12 — near zero — for any
# reasonably broad pool. A narrow filter (a family or region with only a
# handful of species) can still legitimately exhaust its own pool before
# this cap is reached; see NoQuestionAvailable.
_MAX_ATTEMPTS = 12


class NoQuestionAvailable(Exception):
    """Either the region/family combination has no species at all, or none
    of the species it does have turned up real media within `_MAX_ATTEMPTS`
    tries. The caller (the router) surfaces this as a clear "try a wider
    filter" message — it's an expected outcome for a narrow enough filter,
    not a bug.
    """


async def get_question(mode: QuizMode, region_code: str = DEFAULT_REGION, family: str | None = None) -> dict:
    """One fresh question: a random species from the filtered checklist's
    real photo or recording, plus 4 shuffled common-name choices (the
    correct one + up to 3 from the same `family_common_name`, within the
    same filtered pool). Nothing about this call is persisted.
    """
    pool = await _filtered_pool(region_code, family)
    if not pool:
        raise NoQuestionAvailable(
            f"no species found for region_code={region_code!r} family={family!r} — try a broader filter"
        )

    candidates = list(pool)
    random.shuffle(candidates)

    for species in candidates[:_MAX_ATTEMPTS]:
        media = await _real_media(species, mode)
        if media is None:
            continue  # no real photo/recording for this one — try another

        choices = _build_choices(species, pool)
        return {
            "mode": mode,
            "photo_url": media["url"] if mode == "photo" else None,
            "audio_url": media["url"] if mode == "audio" else None,
            "attribution": media["attribution"],
            "choices": choices,
            "correct_scientific_name": species["scientific_name"],
        }

    raise NoQuestionAvailable(
        f"no species with real {mode} media found among {min(len(pool), _MAX_ATTEMPTS)} tried "
        f"(region_code={region_code!r} family={family!r}) — try a broader filter"
    )


async def get_filter_options(region_code: str = DEFAULT_REGION) -> list[dict]:
    """Every taxonomic family actually present in this region's checklist,
    each with how many species it has there — so the frontend only ever
    offers a filter that has something behind it for the chosen region
    (no "Woodpeckers" option for a region with zero woodpeckers).
    """
    species = await region_repo.get_checklist(region_code)
    counts: dict[str, int] = {}
    for s in species:
        name = s.get("family_common_name")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return sorted(({"name": name, "count": count} for name, count in counts.items()), key=lambda f: f["name"])


async def _filtered_pool(region_code: str, family: str | None) -> list[dict]:
    species = await region_repo.get_checklist(region_code)
    if family:
        species = [s for s in species if s.get("family_common_name") == family]
    return species


async def _real_media(species: dict, mode: QuizMode) -> dict | None:
    """`None` means "don't use this species for this mode" — either Commons
    has nothing (both modes) or the photo lookup fell back to the generated
    placeholder (photo only; audio has no placeholder to begin with, so a
    `None` result from get_audio() already means exactly this — see that
    module's own docstring).
    """
    if mode == "photo":
        result = await bird_photos.get_stock_photo(species["scientific_name"], species["common_name"])
        if result["attribution"] is None:
            return None
        return {"url": result["photo_url"], "attribution": result["attribution"]}

    result = await bird_audio.get_audio({"scientific_name": species["scientific_name"]})
    if result is None:
        return None
    return {"url": result["audio_url"], "attribution": result["attribution"]}


def _build_choices(correct: dict, pool: list[dict]) -> list[dict]:
    """3 distractors from the correct species' own family within the active
    (possibly already-filtered) pool — genuinely confusable choices, same
    spirit as the original curated `similar` groups, just generalized to
    real eBird family data instead of a hand-picked visual-similarity list.
    Falls back to random species from the rest of the pool only if that
    family has fewer than 3 *other* members in it (a rare, thin family, or
    a region where it's only barely represented) — those distractors read
    as less obviously related, an accepted tradeoff for an edge case rather
    than failing the question outright.
    """
    same_family = [
        s for s in pool if s.get("family_common_name") == correct.get("family_common_name") and s["code"] != correct["code"]
    ]
    source = same_family if len(same_family) >= _CHOICE_COUNT - 1 else [s for s in pool if s["code"] != correct["code"]]
    distractors = random.sample(source, min(_CHOICE_COUNT - 1, len(source)))

    choices = [correct, *distractors]
    random.shuffle(choices)
    return [{"common_name": c["common_name"], "scientific_name": c["scientific_name"]} for c in choices]
