"""The internal `Observation` model.

Both iNaturalist and eBird payloads get translated into this one shape by the
adapter layer (`app/services/adapters.py`). A sighting is: someone saw some
species at a place and time, optionally with a photo and notes.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.species import SpeciesRef

Sex = Literal["male", "female", "unknown"]
LifeStage = Literal["adult", "juvenile", "fledgling", "unknown"]
ObservationStatus = Literal["draft", "identifying", "confirmed", "logged"]
DetectionType = Literal["sight", "sound"]


class Source(str, Enum):
    inat = "inat"
    ebird = "ebird"
    manual = "manual"


class ObservationBase(BaseModel):
    # A map picker isn't built yet (see add-observation.md), so a sighting can
    # be logged with just a free-text place name; lat/lng stay optional until
    # then.
    lat: float | None = None
    lng: float | None = None
    location_name: str | None = None
    observed_at: datetime
    source: Source
    photo_url: str | None = None
    notes: str | None = None
    sex: Sex | None = None
    life_stage: LifeStage | None = None
    detection_type: DetectionType | None = None  # "sight" or "sound" — how the bird was identified, per the wizard's saw-it/heard-it choice


class ObservationCreate(ObservationBase):
    """Payload for logging a new observation via the API."""

    user_id: str
    species_id: str | None = None
    species: SpeciesRef | None = None
    source: Source = Source.manual
    source_observation_id: str | None = None
    status: ObservationStatus = "logged"


class Observation(ObservationBase):
    """A persisted or normalized observation returned by the API."""

    id: str | None = None
    user_id: str | None = None
    species_id: str | None = None
    species: SpeciesRef = Field(default_factory=SpeciesRef)
    source_observation_id: str | None = None
    status: ObservationStatus = "logged"
