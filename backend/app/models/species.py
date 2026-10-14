"""Species reference shared across observations and the life list.

Mirrors the `species` table in the README schema. `source_ids` keeps the mapping
back to each external API (iNaturalist `taxon_id`, eBird `species_code`) so the
same real-world species coming from either source resolves to one entry.
"""

from datetime import datetime

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


class SpeciesContent(BaseModel):
    """Cached Wikipedia-sourced text — mirrors the `species_content` table
    (migrations/0006_species_content.sql). See docs/features/bird-info.md.
    """

    scientific_name: str
    about: str | None = None
    about_source_url: str | None = None
    sex_differences: str | None = None
    migration: str | None = None
    habitat: str | None = None
    fetched_at: datetime | None = None


class SpeciesProfile(BaseModel):
    """The Bird Info page's full response (`GET /species/profile`) — see
    docs/features/bird-info.md. `common_name`/`family` are `None` when the
    species isn't in our own `species` table yet (e.g. an iNaturalist-only
    species never logged via eBird) — that's a normal outcome, not an error;
    the page just shows less of a header.
    """

    scientific_name: str
    common_name: str | None = None
    family: str | None = None
    photo_url: str
    photo_attribution: str | None = None
    audio_url: str | None = None
    audio_attribution: str | None = None
    about: str | None = None
    about_source_url: str | None = None
    sex_differences: str | None = None
    migration: str | None = None
    habitat: str | None = None
