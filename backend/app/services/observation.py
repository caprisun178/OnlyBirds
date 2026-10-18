"""Business logic for user-owned observations."""

from __future__ import annotations

import logging

from app.dao import ebird
from app.dao.observation_repo import observation_repo
from app.models.observation import LoggedObservation, Observation, ObservationCreate, ObservationUpdate

logger = logging.getLogger(__name__)


async def log_observation(payload: ObservationCreate) -> LoggedObservation:
    # Deferred imports avoid cycles through life_list and pins services.
    from app.services.life_list import get_life_list
    from app.services.pins import evaluate_pins
    from app.services.stickers import evaluate_stickers, stickers_for

    before_count = len(await get_life_list(payload.user_id))

    # Region is server-computed, never trusted from the caller.
    if payload.lat is not None and payload.lng is not None:
        region = await ebird.region_for_point(payload.lat, payload.lng)
        payload = payload.model_copy(update={"region": region})

    observation = await observation_repo.add(payload)
    entries = await get_life_list(payload.user_id)
    awards = []
    if len(entries) > before_count:
        try:
            awards = await evaluate_stickers(payload.user_id, observation.id, entries)
        except Exception:  # noqa: BLE001 — the sighting is already saved; a sticker
            # problem (e.g. the user_stickers migration not applied yet) must
            # not turn that into an error for the user.
            logger.exception("Sticker evaluation failed for observation %s", observation.id)

    # Pin matches are checked for every logged sighting, not just new species.
    if observation.status == "logged":
        await evaluate_pins(observation)

    return LoggedObservation(**observation.model_dump(), stickers_earned=stickers_for(awards))


async def get_observation(observation_id: str) -> Observation | None:
    return await observation_repo.get(observation_id)


async def list_observations(user_id: str, scientific_name: str | None = None) -> list[Observation]:
    """Newest first. `scientific_name` scopes this to one species — see
    `observation_repo.py#list_for_user`'s own note."""
    rows = await observation_repo.list_for_user(user_id, scientific_name)
    return sorted(rows, key=lambda o: o.observed_at, reverse=True)


async def update_observation(observation_id: str, payload: ObservationUpdate) -> Observation | None:
    return await observation_repo.update(observation_id, payload)
