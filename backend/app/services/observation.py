"""Business logic for user-owned observations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.dao import ebird
from app.dao.observation_repo import observation_repo
from app.models.observation import Observation, ObservationCreate, ObservationUpdate

# A pin alert only helps if the bird might still be there — older sightings
# (back-dated entries, bulk-imported trips) are logged without alerting
# anyone. Decided 2026-10-13, see docs/features/bulk-import.md §4.
PIN_ALERT_MAX_AGE = timedelta(days=7)


def _recent_enough_to_alert(observed_at: datetime) -> bool:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)  # naive = UTC, as stored
    return datetime.now(timezone.utc) - observed_at <= PIN_ALERT_MAX_AGE


async def log_observation(payload: ObservationCreate) -> Observation:
    # Deferred import: app.services.pins imports app.services.life_list,
    # which imports this module (get_observation/list_observations) — a
    # module-level import here would be a circular import. Only this one
    # call site needs it, so a local import is enough to break the cycle.
    from app.services.pins import evaluate_pins

    # Region is server-computed, never trusted from the caller — see
    # ObservationBase.region's docstring. Only possible when lat/lng are
    # given (still optional — see ObservationBase); skipped otherwise rather
    # than guessing. A region lookup is a courtesy, not a requirement: the
    # observation is still logged if it fails or eBird isn't configured
    # (region_for_point() itself degrades to "world" rather than raising).
    if payload.lat is not None and payload.lng is not None:
        region = await ebird.region_for_point(payload.lat, payload.lng)
        payload = payload.model_copy(update={"region": region})

    observation = await observation_repo.add(payload)

    # Runs after every logged observation (not just lifers) — someone else
    # seeing a common bird is still a sighting a pinning user might chase.
    # See docs/features/pinned-birds.md#match--notify.
    if observation.status == "logged" and _recent_enough_to_alert(observation.observed_at):
        await evaluate_pins(observation)

    return observation


async def get_observation(observation_id: str) -> Observation | None:
    return await observation_repo.get(observation_id)


async def list_observations(user_id: str) -> list[Observation]:
    """Newest first."""
    rows = await observation_repo.list_for_user(user_id)
    return sorted(rows, key=lambda o: o.observed_at, reverse=True)


async def update_observation(observation_id: str, payload: ObservationUpdate) -> Observation | None:
    return await observation_repo.update(observation_id, payload)


async def undo_import(user_id: str, import_batch_id: str) -> int:
    """Deletes every observation one bulk import logged for this user;
    returns how many. Stored photos are left in the bucket — see
    docs/features/bulk-import.md §4's note on orphaned photos."""
    return await observation_repo.delete_by_import_batch(user_id, import_batch_id)
