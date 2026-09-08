"""Business logic for user-owned observations."""

from __future__ import annotations

from app.dao.observation_repo import observation_repo
from app.models.observation import Observation, ObservationCreate


async def log_observation(payload: ObservationCreate) -> Observation:
    return await observation_repo.add(payload)


async def get_observation(observation_id: str) -> Observation | None:
    return await observation_repo.get(observation_id)


async def list_observations(user_id: str) -> list[Observation]:
    """Newest first."""
    rows = await observation_repo.list_for_user(user_id)
    return sorted(rows, key=lambda o: o.observed_at, reverse=True)
