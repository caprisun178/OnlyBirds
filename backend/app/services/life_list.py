"""Life-list service.

Reason #3 in the README for having a backend: the life list is *derived* from a
user's own observation history and must persist independently of either external
API. Here it is computed from stored observations — one entry per species, dated
to the earliest sighting.

A species key falls back through: our `species_id` -> an external source id ->
the scientific name, so sightings of the same bird from different sources still
collapse to one life-list entry once ids line up.
"""

from __future__ import annotations

import uuid

from app.models.life_list import LifeListEntry
from app.models.observation import Observation
from app.services.observation import list_observations


def _species_key(obs: Observation) -> str:
    if obs.species_id:
        return f"id:{obs.species_id}"
    for source, value in sorted(obs.species.source_ids.items()):
        return f"{source}:{value}"
    if obs.species.scientific_name:
        return f"name:{obs.species.scientific_name.lower()}"
    return f"obs:{obs.id}"


async def get_life_list(user_id: str) -> list[LifeListEntry]:
    observations = await list_observations(user_id)

    first_by_species: dict[str, Observation] = {}
    for obs in observations:
        key = _species_key(obs)
        current = first_by_species.get(key)
        if current is None or obs.observed_at < current.observed_at:
            first_by_species[key] = obs

    entries = [
        LifeListEntry(
            id=uuid.uuid4().hex,
            user_id=user_id,
            species_id=obs.species_id,
            species=obs.species,
            first_observed_at=obs.observed_at,
            observation_id=obs.id,
        )
        for obs in first_by_species.values()
    ]
    entries.sort(key=lambda e: e.first_observed_at, reverse=True)
    return entries
