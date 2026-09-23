"""Describe & guess identification endpoints.

    POST /identify/describe               free text -> ranked candidate photos
    POST /identify/{id}/select            record which candidate the user picked

See `docs/features/add-observation.md` for the flow this feeds into.
"""

from fastapi import APIRouter, HTTPException

from app.models.identification import (
    IdentifyRequest,
    IdentifyResponse,
    SelectCandidateRequest,
    SelectCandidateResponse,
)
from app.services import identify as identify_service

router = APIRouter(prefix="/identify", tags=["identify"])


@router.post("/describe", response_model=IdentifyResponse)
async def identify_describe(payload: IdentifyRequest):
    return await identify_service.describe_bird(payload)


@router.post("/{identification_id}/select", response_model=SelectCandidateResponse)
async def identify_select(identification_id: str, payload: SelectCandidateRequest):
    result = await identify_service.select_candidate(
        identification_id, payload.species_code
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Identification not found")
    return result
