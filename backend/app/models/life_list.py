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
