"""Response shapes for `GET /trip/plan` — see docs/features/plan-a-trip.md.
"""

from pydantic import BaseModel

from app.models.species import SpeciesRef


class Hotspot(BaseModel):
    """A real, eBird-curated birding location — from `GET /ref/hotspot/geo`,
    not guessed from sighting location names (see
    `app/dao/ebird.py#get_hotspots_near`'s docstring for why that
    distinction matters).
    """

    loc_id: str
    name: str
    lat: float
    lng: float
    species_all_time: int  # eBird's numSpeciesAllTime — a popularity/richness signal, not season-specific


class LikelySpecies(BaseModel):
    """One species likely to be around during the trip, based on how many
    times it was reported in roughly the same window *last year*
    (`app/dao/inaturalist.py#get_species_counts`) — one year of comparison,
    not a genuine multi-year frequency model; see
    docs/features/plan-a-trip.md for why.
    """

    species: SpeciesRef
    observation_count: int
    photo_url: str | None = None
    new_for_you: bool | None = None  # None when no user_id was given to cross-reference against


class TripPlan(BaseModel):
    hotspots: list[Hotspot]
    likely_species: list[LikelySpecies]
