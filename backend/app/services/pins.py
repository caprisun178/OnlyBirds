"""Business logic for Pinned Birds — see docs/features/pinned-birds.md.

`pin()`/`unpin()`/`list_pins()` back the want-to-see list; `evaluate_pins()`
is the match-and-notify engine, called from
`app/services/observation.py#log_observation()` after every logged
observation (see that call site for why the import is deferred there).
"""

from __future__ import annotations

from app.dao.notification_repo import notification_repo
from app.dao.pin_repo import pin_repo
from app.models.observation import Observation
from app.models.pin import PinCreate, PinnedBird
from app.services import user as user_service
from app.services.life_list import get_life_list


class AlreadyOnLifeList(Exception):
    """Raised when pinning a species the caller has already logged —
    nothing to chase. See docs/features/pinned-birds.md#pinning.
    """


async def list_pins(user_id: str) -> list[PinnedBird]:
    return await pin_repo.list_for_user(user_id)


async def pin(user_id: str, payload: PinCreate) -> PinnedBird:
    life_list = await get_life_list(user_id)
    already_seen = {e.species.scientific_name.lower() for e in life_list if e.species.scientific_name}
    if payload.scientific_name.lower() in already_seen:
        raise AlreadyOnLifeList(payload.scientific_name)

    region = payload.region
    if not region:
        profile = await user_service.get_profile_by_id(user_id)
        region = profile.default_region if profile else "world"

    return await pin_repo.upsert(user_id, payload.scientific_name, payload.common_name, region)


async def update_pin_region(user_id: str, scientific_name: str, region: str) -> PinnedBird | None:
    return await pin_repo.update_region(user_id, scientific_name, region)


async def unpin(user_id: str, scientific_name: str) -> bool:
    return await pin_repo.delete(user_id, scientific_name)


async def evaluate_pins(observation: Observation) -> list[str]:
    """Finds other users' pins matching this observation's species + region,
    and raises a deduped `pin_hit` notification for each. Returns the
    `user_id`s actually notified (a repeat sighting the same day inserts
    nothing more — see `notification_repo.insert()` — so this list can be
    shorter than the number of matching pins).

    A no-op (empty list, no error) when the observation has no scientific
    name, no region (lat/lng weren't given — see
    `ObservationBase.region`'s docstring), or no user_id — there's nothing
    to match against.
    """
    scientific_name = observation.species.scientific_name
    if not scientific_name or not observation.region or not observation.user_id:
        return []

    matches = await pin_repo.find_matches(scientific_name, observation.region, observation.user_id)
    notified: list[str] = []
    day = observation.observed_at.date().isoformat()

    for pinned in matches:
        dedupe_key = f"pin_hit:{pinned.user_id}:{scientific_name.lower()}:{pinned.region}:{day}"
        payload = {
            "species": scientific_name,
            "common_name": pinned.common_name or observation.species.common_name,
            "region": observation.region,
            "observation_id": observation.id,
        }
        result = await notification_repo.insert(pinned.user_id, "pin_hit", payload, dedupe_key)
        if result:
            notified.append(pinned.user_id)

    return notified
