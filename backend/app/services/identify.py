"""Business logic for the describe & guess / photo identification flows."""

from __future__ import annotations

import asyncio
from datetime import date

from app.dao import bioclip_classifier, bird_photos, ebird
from app.dao import identify as identify_dao
from app.dao.identification_repo import identification_repo
from app.models.identification import (
    Candidate,
    IdentifyRequest,
    IdentifyResponse,
    SelectCandidateResponse,
)

# A wider raw pool is only worth fetching once a region filter can actually
# use the extra candidates to rescue one buried behind implausible ones —
# otherwise it's wasted scoring/classification work for a reorder that's a
# no-op. See `_regional_species_codes()`'s docstring for why this never
# *drops* a candidate, only reprioritizes.
_REGIONAL_POOL_SIZE = 15
_FINAL_CANDIDATE_COUNT = 6


async def _regional_checklist(
    lat: float | None, lng: float | None, observed_at: date | None
) -> list[dict] | None:
    """Raw eBird checklist rows for this region/day — shared fetch behind
    both `_regional_species_codes()` (describe-flow's reorder) and
    `_regional_candidates()` (photo-flow's BioCLIP candidate pool), so a
    request only ever makes this call once. Returns `None` whenever there
    isn't enough to ask or eBird can't answer — see
    `app/services/observation.py`'s identical reasoning for
    `region_for_point()` degrading rather than raising; a failed regional
    lookup should never block identification, only skip the enhancement.
    """
    if lat is None or lng is None or observed_at is None:
        return None
    region = await ebird.region_for_point(lat, lng)
    if region == "world":  # region_for_point()'s own failure fallback — not a real region to query
        return None
    try:
        return await ebird.get_historic_checklist(region, observed_at)
    except Exception:
        return None


async def _regional_species_codes(
    lat: float | None, lng: float | None, observed_at: date | None
) -> set[str] | None:
    """Species eBird recorded in this region on this calendar day — a signal
    to *reorder* describe-flow's generic-path candidates toward what's
    regionally plausible, never to drop one. One day's regional checklist is
    real but incomplete (a common resident can go unreported on any given
    day), so treating absence as "ruled out" would sometimes demote the
    correct species for a data gap, not a real implausibility."""
    checklist = await _regional_checklist(lat, lng, observed_at)
    if not checklist:
        return None
    return {row["speciesCode"] for row in checklist if "speciesCode" in row}


async def _regional_candidates(
    lat: float | None, lng: float | None, observed_at: date | None
) -> list[dict] | None:
    """The same checklist, shaped as `{scientific_name, common_name,
    species_code}` dicts for `bioclip_classifier.classify()`'s `candidates`
    param — which **adds** these to its own default pool rather than
    replacing it (see that function's docstring for why: a single day's
    regional checklist is real but incomplete, and using it exclusively was
    confirmed live to sometimes lose a real local species the checklist
    just didn't happen to include that day). Returns `None` (classifier
    uses its default pool alone) under the same conditions
    `_regional_checklist()` does, or if the checklist came back with no
    usable rows."""
    checklist = await _regional_checklist(lat, lng, observed_at)
    if not checklist:
        return None
    candidates = [
        {
            "scientific_name": row["sciName"],
            "common_name": row["comName"],
            "species_code": row["speciesCode"],
        }
        for row in checklist
        if row.get("sciName") and row.get("comName") and row.get("speciesCode")
    ]
    return candidates or None


def _reorder_by_region(candidates: list[dict], regional_codes: set[str] | None, code_key: str) -> list[dict]:
    """Stable partition: candidates eBird actually recorded in this
    region/day move to the front, in their original relative order;
    everything else follows, also in its original order. Never drops a
    candidate — see `_regional_species_codes()` for why absence isn't
    treated as disqualifying."""
    if not regional_codes:
        return candidates
    in_region = [c for c in candidates if c[code_key] in regional_codes]
    out_of_region = [c for c in candidates if c[code_key] not in regional_codes]
    return in_region + out_of_region


async def describe_bird(payload: IdentifyRequest) -> IdentifyResponse:
    hints = payload.hints.model_dump(exclude_none=True) if payload.hints else None
    regional_codes = await _regional_species_codes(payload.lat, payload.lng, payload.observed_at)
    pool_size = _REGIONAL_POOL_SIZE if regional_codes else _FINAL_CANDIDATE_COUNT

    raw_candidates, target_code = await identify_dao.get_candidates(payload.text, hints, pool_size=pool_size)

    if target_code is None:
        # Generic path only — no ground truth to second-guess. The named
        # path (target_code set) already knows the answer at real
        # confidence; reordering it by an incomplete regional checklist
        # could demote a correct named match for a data gap, which would
        # make this strictly worse, not better.
        raw_candidates = _reorder_by_region(raw_candidates, regional_codes, "code")
    raw_candidates = raw_candidates[:_FINAL_CANDIDATE_COUNT]

    hydrated = await identify_dao.attach_media(raw_candidates, payload.sense)

    candidates = [
        Candidate(
            species_code=c["code"],
            common_name=c["common_name"],
            scientific_name=c["scientific_name"],
            confidence=c["confidence"],
            photo_url=c["photo_url"],
            photo_attribution=c["photo_attribution"],
            audio_url=c["audio_url"],
            audio_attribution=c["audio_attribution"],
        )
        for c in hydrated
    ]

    record = await identification_repo.add(
        method="describe",
        sense=payload.sense,
        input_data={"text": payload.text, "hints": hints or {}},
        candidates=candidates,
        target_species_code=target_code,
    )
    return IdentifyResponse(identification_id=record.id, sense=payload.sense, candidates=candidates)


async def identify_photo(
    image_bytes: bytes,
    lat: float | None = None,
    lng: float | None = None,
    observed_at: date | None = None,
) -> IdentifyResponse:
    """Photo-based identification (`docs/features/bird-id.md` §7/§9) —
    classifies via `app/dao/bioclip_classifier.py` (zero-shot, no fixed
    label set), then hydrates each prediction with a real photo exactly
    like describe-flow candidates get (`bird_photos.get_stock_photo()` —
    same call `species.py`'s search uses for non-canned-reference-set
    species). No audio: a photo upload is inherently "sight," never
    "sound," so `sense` is always "sight" and there's nothing to attach the
    way describe's "I heard it" path does.

    `lat`/`lng`/`observed_at` are optional and, when given, add species
    eBird actually recorded in that region on that day
    (`_regional_candidates()`) to the classifier's default candidate pool —
    this is what fixes the failure mode `docs/features/bird-id.md`'s
    §1/§7/§9 describe: a regionally-common species that was missing from
    the default pool entirely now gets to compete, without needing the
    region's checklist to be complete enough to stand on its own (it isn't,
    always — see `bioclip_classifier.classify()`'s docstring for the
    confirmed-live regression that shaped this).
    """
    regional_candidates = await _regional_candidates(lat, lng, observed_at)

    predictions = bioclip_classifier.classify(
        image_bytes, top_k=_FINAL_CANDIDATE_COUNT, candidates=regional_candidates
    )

    photos = await asyncio.gather(
        *(bird_photos.get_stock_photo(p["scientific_name"], p["common_name"]) for p in predictions)
    )

    candidates = [
        Candidate(
            species_code=p["species_code"],
            common_name=p["common_name"],
            scientific_name=p["scientific_name"],
            confidence=p["confidence"],
            photo_url=photo["photo_url"],
            photo_attribution=photo["attribution"],
            audio_url=None,
            audio_attribution=None,
        )
        for p, photo in zip(predictions, photos)
    ]

    record = await identification_repo.add(
        method="photo",
        sense="sight",
        input_data={},
        candidates=candidates,
        target_species_code=None,
    )
    return IdentifyResponse(identification_id=record.id, method="photo", sense="sight", candidates=candidates)


async def select_candidate(
    identification_id: str, species_code: str | None
) -> SelectCandidateResponse | None:
    record = await identification_repo.get(identification_id)
    if record is None:
        return None

    chosen = next(
        (c for c in record.candidates if c.species_code == species_code), None
    )

    if record.target_species_code is not None:
        is_match = species_code == record.target_species_code
        outcome = "correct" if is_match else "incorrect"
    else:
        # No named target to grade against — a generic description just
        # trusts whichever candidate the user recognized.
        is_match = None
        outcome = "unconfirmed"

    await identification_repo.set_outcome(identification_id, species_code, outcome)
    return SelectCandidateResponse(
        identification_id=identification_id,
        chosen_species=chosen,
        outcome=outcome,
        is_match=is_match,
    )
