"""Business logic for user-owned observations."""

from __future__ import annotations

from app.dao.observation_repo import observation_repo
from app.models.observation import Observation, ObservationCreate


async def log_observation(payload: ObservationCreate) -> Observation:
    from app.services.life_list import get_life_list
    from app.services.stickers import evaluate_stickers

    before_count = len(await get_life_list(payload.user_id))
    observation = await observation_repo.add(payload)
    entries = await get_life_list(payload.user_id)
    if len(entries) > before_count:
        await evaluate_stickers(payload.user_id, observation.id, entries)
    return observation


async def get_observation(observation_id: str) -> Observation | None:
    return await observation_repo.get(observation_id)


async def list_observations(user_id: str) -> list[Observation]:
    """Newest first."""
    rows = await observation_repo.list_for_user(user_id)
    return sorted(rows, key=lambda o: o.observed_at, reverse=True)
