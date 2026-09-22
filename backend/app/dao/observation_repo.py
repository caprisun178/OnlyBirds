"""Persistence for user-owned observations. The life list has no persistence
of its own — it's derived live from these rows (`app/services/life_list.py`).

Two implementations behind one `ObservationRepo` Protocol:
- `InMemoryObservationRepo` — default when `DATABASE_URL` isn't set (tests,
  and any environment without a database configured).
- `PostgresObservationRepo` — real persistence (Neon), used automatically
  once `DATABASE_URL` is set. `user_id` everywhere in this API is the
  external id the frontend already uses (`'u1'`, the
  `docs/features/add-observation.md` test profile's id, standing in for
  `users.auth_provider_id` until real auth exists) — never the internal
  Postgres uuid. `users` and `species` rows are get-or-created on the fly
  from that id / from `payload.species.scientific_name`, since nothing
  upstream creates them ahead of time yet.

  Each method runs its (sync — see `app/dao/db.py`) query inside
  `asyncio.to_thread` to stay non-blocking without needing psycopg's async
  mode.

"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.observation import Observation, ObservationCreate
from app.models.species import SpeciesRef


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
            detection_type=payload.detection_type,
            status=payload.status,
        )
        self._by_id[obs.id] = obs
        return obs

    async def get(self, observation_id: str) -> Observation | None:
        return self._by_id.get(observation_id)

    async def list_for_user(self, user_id: str) -> list[Observation]:
        return [o for o in self._by_id.values() if o.user_id == user_id]


class PostgresObservationRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def add(self, payload: ObservationCreate) -> Observation:
        return await asyncio.to_thread(self._add_sync, payload)

    async def get(self, observation_id: str) -> Observation | None:
        return await asyncio.to_thread(self._get_sync, observation_id)

    async def list_for_user(self, user_id: str) -> list[Observation]:
        return await asyncio.to_thread(self._list_for_user_sync, user_id)

    # ---- sync internals, each run off the event loop via to_thread above --

    @staticmethod
    def _get_or_create_user_id(cur, auth_provider_id: str) -> uuid.UUID:
        cur.execute(
            """
            insert into users (auth_provider_id) values (%s)
            on conflict (auth_provider_id)
                do update set auth_provider_id = excluded.auth_provider_id
            returning id
            """,
            (auth_provider_id,),
        )
        return cur.fetchone()["id"]

    @staticmethod
    def _get_or_create_species_id(cur, species: SpeciesRef | None) -> uuid.UUID | None:
        if species is None or not species.scientific_name:
            return None
        cur.execute(
            "select id from species where scientific_name = %s",
            (species.scientific_name,),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            "insert into species (scientific_name, common_name) values (%s, %s) returning id",
            (species.scientific_name, species.common_name),
        )
        return cur.fetchone()["id"]

    def _add_sync(self, payload: ObservationCreate) -> Observation:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                user_id = self._get_or_create_user_id(cur, payload.user_id)
                species_id = self._get_or_create_species_id(cur, payload.species)

                cur.execute(
                    """
                    insert into observations (
                        user_id, species_id, lat, lng, location_name, observed_at,
                        source, source_observation_id, photo_url, notes,
                        sex, life_stage, detection_type, status
                    ) values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    returning id
                    """,
                    (
                        user_id,
                        species_id,
                        payload.lat,
                        payload.lng,
                        payload.location_name,
                        payload.observed_at,
                        payload.source.value,
                        payload.source_observation_id,
                        payload.photo_url,
                        payload.notes,
                        payload.sex,
                        payload.life_stage,
                        payload.detection_type,
                        payload.status,
                    ),
                )
                new_id = cur.fetchone()["id"]

        return Observation(
            id=str(new_id),
            user_id=payload.user_id,
            species_id=str(species_id) if species_id else None,
            species=payload.species or SpeciesRef(),
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
            detection_type=payload.detection_type,
            status=payload.status,
        )

    def _get_sync(self, observation_id: str) -> Observation | None:
        try:
            obs_uuid = uuid.UUID(observation_id)
        except ValueError:
            return None

        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select o.*, u.auth_provider_id as user_auth_id,
                           s.scientific_name as species_scientific_name,
                           s.common_name as species_common_name
                    from observations o
                    join users u on u.id = o.user_id
                    left join species s on s.id = o.species_id
                    where o.id = %s
                    """,
                    (obs_uuid,),
                )
                row = cur.fetchone()

        return self._row_to_observation(row) if row else None

    def _list_for_user_sync(self, user_id: str) -> list[Observation]:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select id from users where auth_provider_id = %s", (user_id,))
                user_row = cur.fetchone()
                if user_row is None:
                    return []  # never logged anything — no point querying observations

                cur.execute(
                    """
                    select o.*, %s as user_auth_id,
                           s.scientific_name as species_scientific_name,
                           s.common_name as species_common_name
                    from observations o
                    left join species s on s.id = o.species_id
                    where o.user_id = %s
                    """,
                    (user_id, user_row["id"]),
                )
                rows = cur.fetchall()

        return [self._row_to_observation(row) for row in rows]

    @staticmethod
    def _row_to_observation(row: dict[str, Any]) -> Observation:
        return Observation(
            id=str(row["id"]),
            user_id=row["user_auth_id"],
            species_id=str(row["species_id"]) if row["species_id"] else None,
            species=SpeciesRef(
                id=str(row["species_id"]) if row["species_id"] else None,
                scientific_name=row["species_scientific_name"],
                common_name=row["species_common_name"],
            ),
            lat=row["lat"],
            lng=row["lng"],
            location_name=row["location_name"],
            observed_at=row["observed_at"],
            source=row["source"],
            source_observation_id=row["source_observation_id"],
            photo_url=row["photo_url"],
            notes=row["notes"],
            sex=row["sex"],
            life_stage=row["life_stage"],
            detection_type=row["detection_type"],
            status=row["status"],
        )


def _build_default_repo() -> ObservationRepo:
    if get_settings().database_url:
        return PostgresObservationRepo()
    return InMemoryObservationRepo()


# Single shared instance for the process lifetime.
observation_repo: ObservationRepo = _build_default_repo()
