"""The internal `Observation` model.

Both iNaturalist and eBird payloads get translated into this one shape by the
adapter layer (`app/services/adapters.py`). A sighting is: someone saw some
species at a place and time, optionally with a photo and notes.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.species import SpeciesRef


class Source(str, Enum):
    inat = "inat"
    ebird = "ebird"
    manual = "manual"


class ObservationBase(BaseModel):
    lat: float
    lng: float
    observed_at: datetime
    source: Source
    photo_url: str | None = None
    notes: str | None = None


class ObservationCreate(ObservationBase):
    """Payload for logging a new observation via the API."""

    user_id: str
    species_id: str | None = None
    species: SpeciesRef | None = None
    source: Source = Source.manual
    source_observation_id: str | None = None


class Observation(ObservationBase):
    """A persisted or normalized observation returned by the API."""

    id: str | None = None
    user_id: str | None = None
    species_id: str | None = None
    species: SpeciesRef = Field(default_factory=SpeciesRef)
    source_observation_id: str | None = None
