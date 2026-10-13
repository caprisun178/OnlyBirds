"""User-owned observation endpoints.

Route shapes match what the frontend DAO expects
(`frontend/src/Dao/observations.js`):
    GET   /users/{user_id}/observations
    POST  /observations
    GET   /observations/{observation_id}
    PATCH /observations/{observation_id}
    DELETE /users/{user_id}/imports/{import_batch_id}   undo a bulk import
"""

from fastapi import APIRouter, HTTPException, status

from app.models.observation import Observation, ObservationCreate, ObservationUpdate
from app.services import observation as observation_service

router = APIRouter(tags=["observations"])


@router.get("/users/{user_id}/observations", response_model=list[Observation])
async def list_user_observations(user_id: str):
    return await observation_service.list_observations(user_id)


@router.post(
    "/observations",
    response_model=Observation,
    status_code=status.HTTP_201_CREATED,
)
async def create_observation(payload: ObservationCreate):
    return await observation_service.log_observation(payload)


@router.get("/observations/{observation_id}", response_model=Observation)
async def get_observation(observation_id: str):
    obs = await observation_service.get_observation(observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return obs


@router.patch("/observations/{observation_id}", response_model=Observation)
async def update_observation(observation_id: str, payload: ObservationUpdate):
    obs = await observation_service.update_observation(observation_id, payload)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return obs


@router.delete("/users/{user_id}/imports/{import_batch_id}")
async def undo_import(user_id: str, import_batch_id: str) -> dict[str, int]:
    """Deletes every observation from one bulk import. See
    docs/features/bulk-import.md §4."""
    deleted = await observation_service.undo_import(user_id, import_batch_id)
    return {"deleted": deleted}
