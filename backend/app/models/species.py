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
