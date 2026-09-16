"""Describe & guess identification models.

Computer vision is descoped for MVP (see `docs/features/add-observation.md`),
so `app/dao/identify.py` matches free text against a small canned reference
set instead of calling a real CV/LLM service. These models are shaped so that
DAO can be swapped out later without touching the service or router layer.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["correct", "incorrect", "unconfirmed"]


class IdentifyHints(BaseModel):
    size: str | None = None
    color: str | None = None
    habitat: str | None = None
    region: str | None = None


class IdentifyRequest(BaseModel):
    text: str = Field(min_length=1)
    hints: IdentifyHints | None = None


class Candidate(BaseModel):
    species_code: str
    common_name: str
    scientific_name: str
    confidence: float
    photo_url: str


class IdentifyResponse(BaseModel):
    identification_id: str
    method: Literal["describe"] = "describe"
    candidates: list[Candidate]


class SelectCandidateRequest(BaseModel):
    """`species_code=None` means "none of these match what I saw"."""

    species_code: str | None = None


class SelectCandidateResponse(BaseModel):
    identification_id: str
    chosen_species: Candidate | None
    outcome: Outcome
    is_match: bool | None  # None when there was no known target to check against


class Identification(BaseModel):
    """Persisted record — mirrors the `identifications` table in database.md."""

    id: str
    method: Literal["describe"] = "describe"
    input: dict = Field(default_factory=dict)
    candidates: list[Candidate] = Field(default_factory=list)
    target_species_code: str | None = None  # only known when the text named a species outright
    chosen_species_code: str | None = None
    outcome: Outcome = "unconfirmed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
