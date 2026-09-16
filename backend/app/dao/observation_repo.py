"""Persistence for user-owned observations and life-list entries.

Roadmap step 3 swaps this for PostgreSQL + PostGIS. Until then an in-process
dict store keeps the `/observations` and `/life-list` endpoints working end to
end. The `ObservationRepo` protocol is the seam a SQL implementation slots into.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.models.observation import Observation, ObservationCreate


class ObservationRepo(Protocol):
    async def add(self, payload: ObservationCreate) -> Observation: ...
    async def get(self, observation_id: str) -> Observation | None: ...
    async def list_for_user(self, user_id: str) -> list[Observation]: ...


class InMemoryObservationRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, Observation] = {}

    async def add(self, payload: ObservationCreate) -> Observation:
        obs = Observation(
            id=uuid.uuid4().hex,
            user_id=payload.user_id,
            species_id=payload.species_id,
            species=payload.species or None,  # type: ignore[arg-type]
            lat=payload.lat,
            lng=payload.lng,
            location_name=payload.location_name,
            observed_at=payload.observed_at,
            source=payload.source,
            source_observation_id=payload.source_observation_id,
            photo_url=payload.photo_url,
            notes=payload.notes,
            sex=payload.sex,
            life_stage=payload.life_stage,
            identification_id=payload.identification_id,
            status=payload.status,
        )
        self._by_id[obs.id] = obs
        return obs

    async def get(self, observation_id: str) -> Observation | None:
        return self._by_id.get(observation_id)

    async def list_for_user(self, user_id: str) -> list[Observation]:
        return [o for o in self._by_id.values() if o.user_id == user_id]


# Single shared instance for the process lifetime.
observation_repo: ObservationRepo = InMemoryObservationRepo()
