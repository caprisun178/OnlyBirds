"""Business logic for the describe & guess / photo identification flows."""

from __future__ import annotations

import asyncio

from app.dao import bird_classifier, bird_photos
from app.dao import identify as identify_dao
from app.dao.identification_repo import identification_repo
from app.models.identification import (
    Candidate,
    IdentifyRequest,
    IdentifyResponse,
    SelectCandidateResponse,
)


async def describe_bird(payload: IdentifyRequest) -> IdentifyResponse:
    hints = payload.hints.model_dump(exclude_none=True) if payload.hints else None
    raw_candidates, target_code = await identify_dao.describe(payload.text, hints, payload.sense)

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
        for c in raw_candidates
    ]

    record = await identification_repo.add(
        method="describe",
        sense=payload.sense,
        input_data={"text": payload.text, "hints": hints or {}},
        candidates=candidates,
        target_species_code=target_code,
    )
    return IdentifyResponse(identification_id=record.id, sense=payload.sense, candidates=candidates)


async def identify_photo(image_bytes: bytes) -> IdentifyResponse:
    """Photo-based identification (`docs/features/bird-id.md`) — classifies
    locally (`app/dao/bird_classifier.py`, no network call), then hydrates
    each prediction with a real photo exactly like describe-flow candidates
    get (`bird_photos.get_stock_photo()` — same call `species.py`'s search
    uses for non-canned-reference-set species). No audio: a photo upload is
    inherently "sight," never "sound," so `sense` is always "sight" and
    there's nothing to attach the way describe's "I heard it" path does.
    """
    predictions = bird_classifier.classify(image_bytes)
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
