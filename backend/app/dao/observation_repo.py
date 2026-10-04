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
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Protocol

from psycopg.rows import dict_row

from app.config import get_settings
from app.dao.db import get_pool
from app.models.observation import Observation, ObservationCreate, ObservationUpdate
from app.models.species import SpeciesRef

_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in km — stands in for a
    real PostGIS radius query until `observations.geom` exists (see
    docs/features/explore-map.md's "full spec" vs. what's actually built).
    `lat`/`lng` columns already exist on `observations`; this just filters
    them in Python instead of in SQL.
    """
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))


class ObservationRepo(Protocol):
    async def add(self, payload: ObservationCreate) -> Observation: ...
    async def get(self, observation_id: str) -> Observation | None: ...
    async def list_for_user(self, user_id: str) -> list[Observation]: ...
    async def update(self, observation_id: str, payload: ObservationUpdate) -> Observation | None: ...
    async def list_near(self, lat: float, lng: float, radius_km: float, since: datetime) -> list[Observation]: ...


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

    async def update(self, observation_id: str, payload: ObservationUpdate) -> Observation | None:
        existing = self._by_id.get(observation_id)
        if existing is None:
            return None
        updated = existing.model_copy(update=payload.model_dump(exclude_unset=True))
        self._by_id[observation_id] = updated
        return updated

    async def list_near(self, lat: float, lng: float, radius_km: float, since: datetime) -> list[Observation]:
        return [
            o
            for o in self._by_id.values()
            if o.status == "logged"
            and o.lat is not None
            and o.lng is not None
            and o.observed_at >= since
            and _haversine_km(lat, lng, o.lat, o.lng) <= radius_km
        ]


class PostgresObservationRepo:
    """Real persistence against Postgres (Neon). See module docstring."""

    async def add(self, payload: ObservationCreate) -> Observation:
        return await asyncio.to_thread(self._add_sync, payload)

    async def get(self, observation_id: str) -> Observation | None:
        return await asyncio.to_thread(self._get_sync, observation_id)

    async def list_for_user(self, user_id: str) -> list[Observation]:
        return await asyncio.to_thread(self._list_for_user_sync, user_id)

    async def update(self, observation_id: str, payload: ObservationUpdate) -> Observation | None:
        return await asyncio.to_thread(self._update_sync, observation_id, payload)

    async def list_near(self, lat: float, lng: float, radius_km: float, since: datetime) -> list[Observation]:
        return await asyncio.to_thread(self._list_near_sync, lat, lng, radius_km, since)

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

    def _update_sync(self, observation_id: str, payload: ObservationUpdate) -> Observation | None:
        try:
            obs_uuid = uuid.UUID(observation_id)
        except ValueError:
            return None

        # Only the fields actually sent get touched — `exclude_unset` so an
        # omitted field isn't overwritten with a stray `null`.
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            return self._get_sync(observation_id)

        set_clause = ", ".join(f"{column} = %s" for column in fields)
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"update observations set {set_clause} where id = %s",
                    (*fields.values(), obs_uuid),
                )
                if cur.rowcount == 0:
                    return None

        return self._get_sync(observation_id)

    def _list_near_sync(self, lat: float, lng: float, radius_km: float, since: datetime) -> list[Observation]:
        # No PostGIS geom column yet, so this can't do a real radius query in
        # SQL — instead, a generous bounding box narrows the candidates (1°
        # latitude is ~111 km; longitude degrees shrink toward the poles, so
        # that side widens by 1/cos(lat)), then `_haversine_km` filters to
        # the exact circle in Python. Fine at this app's current scale;
        # revisit once `observations.geom` exists (docs/features/explore-map.md).
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * max(0.1, cos(radians(lat))))

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
                    where o.status = 'logged'
                      and o.lat between %s and %s
                      and o.lng between %s and %s
                      and o.observed_at >= %s
                    """,
                    (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta, since),
                )
                rows = cur.fetchall()

        candidates = [self._row_to_observation(row) for row in rows]
        return [o for o in candidates if _haversine_km(lat, lng, o.lat, o.lng) <= radius_km]

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
