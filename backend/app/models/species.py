"""Species reference shared across observations and the life list.

Mirrors the `species` table in the README schema. `source_ids` keeps the mapping
back to each external API (iNaturalist `taxon_id`, eBird `species_code`) so the
same real-world species coming from either source resolves to one entry.
"""

from pydantic import BaseModel, Field


class SpeciesRef(BaseModel):
    id: str | None = None
    scientific_name: str | None = None
    common_name: str | None = None
    taxon_group: str | None = None
    source_ids: dict[str, str] = Field(default_factory=dict)


class SpeciesPhoto(BaseModel):
    """A guaranteed-non-blank photo for a species — a real Commons photo, or
    a generated placeholder if Commons has nothing (`bird_photos.get_stock_photo()`
    always returns one or the other). Keyed by scientific name since that's
    the one field every caller actually has. Backs any UI that needs a photo
    for a species that may not have come with its own observation photo —
    e.g. Explore Map's species-filter suggestions, most of which are eBird
    sightings and never carry a `photo_url` at all.
    """

    scientific_name: str
    photo_url: str
    photo_attribution: str | None = None
