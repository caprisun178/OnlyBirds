"""Business logic for the describe & guess identification flow."""

from __future__ import annotations

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
