"""Life list entry — one row per species a user has ever observed.

Derived from the user's own observation history (see
`app/services/life_list.py`), persisted independently of the external APIs.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.species import SpeciesRef


class LifeListEntry(BaseModel):
    id: str | None = None
    user_id: str
    species_id: str | None = None
    species: SpeciesRef = Field(default_factory=SpeciesRef)
    first_observed_at: datetime
    observation_id: str | None = None


class RegionOption(BaseModel):
    """One entry in the region picker — a child of some parent region."""

    code: str
    name: str


class ChecklistSpecies(BaseModel):
    """One row in a region's completion view — a species, marked seen or not
    for whichever user asked (or not-personalized if no user_id was given)."""

    code: str
    common_name: str
    scientific_name: str
    seen: bool
    first_observed_at: datetime | None = None
    photo_url: str | None = None


class RegionChecklistResponse(BaseModel):
    region_code: str
    total: int
    seen: int
    species: list[ChecklistSpecies]
