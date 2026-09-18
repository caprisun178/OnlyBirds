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

from app.dao import ebird, region_repo
from app.models.life_list import ChecklistSpecies, LifeListEntry, RegionChecklistResponse, RegionOption
from app.models.observation import Observation
from app.services.observation import get_observation, list_observations


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


async def get_region_children(parent_code: str, region_type: str) -> list[RegionOption]:
    raw = await ebird.get_region_children(parent_code, region_type)
    return [RegionOption(code=r["code"], name=r["name"]) for r in raw]


async def get_region_checklist(region_code: str, user_id: str | None) -> RegionChecklistResponse:
    """The region's full species checklist, each row marked seen or not for
    `user_id` (by scientific name — the same fallback `_species_key` above
    uses when nothing better is available). Without a `user_id`, every row
    comes back unseen — still useful as a plain species catalog.
    """
    checklist = await region_repo.get_checklist(region_code)

    seen_by_name: dict[str, LifeListEntry] = {}
    if user_id:
        entries = await get_life_list(user_id)
        seen_by_name = {
            e.species.scientific_name.lower(): e
            for e in entries
            if e.species.scientific_name
        }

    rows: list[ChecklistSpecies] = []
    seen_count = 0
    for sp in checklist:
        entry = seen_by_name.get(sp["scientific_name"].lower())
        photo_url = None
        if entry and entry.observation_id:
            obs = await get_observation(entry.observation_id)
            photo_url = obs.photo_url if obs else None
        if entry:
            seen_count += 1
        rows.append(
            ChecklistSpecies(
                code=sp["code"],
                common_name=sp["common_name"],
                scientific_name=sp["scientific_name"],
                seen=entry is not None,
                first_observed_at=entry.first_observed_at if entry else None,
                photo_url=photo_url,
            )
        )

    return RegionChecklistResponse(
        region_code=region_code, total=len(rows), seen=seen_count, species=rows
    )
