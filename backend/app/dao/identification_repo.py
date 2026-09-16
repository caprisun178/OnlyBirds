"""Persistence for describe & guess identification records.

Same in-memory-now, SQL-later shape as `app/dao/observation_repo.py` — see
that file's docstring. Swaps for a `identifications` table (see
`docs/features/database.md`) once PostgreSQL is wired up.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.models.identification import Candidate, Identification, Outcome


class IdentificationRepo(Protocol):
    async def add(
        self,
        method: str,
        input_data: dict,
        candidates: list[Candidate],
        target_species_code: str | None,
    ) -> Identification: ...

    async def get(self, identification_id: str) -> Identification | None: ...

    async def set_outcome(
        self,
        identification_id: str,
        chosen_species_code: str | None,
        outcome: Outcome,
    ) -> Identification | None: ...


class InMemoryIdentificationRepo:
    def __init__(self) -> None:
        self._by_id: dict[str, Identification] = {}

    async def add(
        self,
        method: str,
        input_data: dict,
        candidates: list[Candidate],
        target_species_code: str | None,
    ) -> Identification:
        record = Identification(
            id=uuid.uuid4().hex,
            method=method,
            input=input_data,
            candidates=candidates,
            target_species_code=target_species_code,
        )
        self._by_id[record.id] = record
        return record

    async def get(self, identification_id: str) -> Identification | None:
        return self._by_id.get(identification_id)

    async def set_outcome(
        self,
        identification_id: str,
        chosen_species_code: str | None,
        outcome: Outcome,
    ) -> Identification | None:
        record = self._by_id.get(identification_id)
        if record is None:
            return None
        updated = record.model_copy(
            update={"chosen_species_code": chosen_species_code, "outcome": outcome}
        )
        self._by_id[identification_id] = updated
        return updated


# Single shared instance for the process lifetime.
identification_repo: IdentificationRepo = InMemoryIdentificationRepo()
