"""Business logic for user-owned observations."""

from __future__ import annotations

from app.dao import ebird
from app.dao.observation_repo import observation_repo
from app.models.observation import Observation, ObservationCreate, ObservationUpdate


async def log_observation(payload: ObservationCreate) -> Observation:
    # Deferred imports avoid cycles through life_list and pins services.
    from app.services.life_list import get_life_list
    from app.services.pins import evaluate_pins
    from app.services.stickers import evaluate_stickers

    before_count = len(await get_life_list(payload.user_id))

    # Region is server-computed, never trusted from the caller.
    if payload.lat is not None and payload.lng is not None:
        region = await ebird.region_for_point(payload.lat, payload.lng)
        payload = payload.model_copy(update={"region": region})

    observation = await observation_repo.add(payload)
    entries = await get_life_list(payload.user_id)
    if len(entries) > before_count:
        await evaluate_stickers(payload.user_id, observation.id, entries)

    # Pin matches are checked for every logged sighting, not just new species.
    if observation.status == "logged":
        await evaluate_pins(observation)

    return observation


async def get_observation(observation_id: str) -> Observation | None:
    return await observation_repo.get(observation_id)


async def list_observations(user_id: str, scientific_name: str | None = None) -> list[Observation]:
    """Newest first. `scientific_name` scopes this to one species — see
    `observation_repo.py#list_for_user`'s own note."""
    rows = await observation_repo.list_for_user(user_id, scientific_name)
    return sorted(rows, key=lambda o: o.observed_at, reverse=True)


async def update_observation(observation_id: str, payload: ObservationUpdate) -> Observation | None:
    return await observation_repo.update(observation_id, payload)
