"""User-owned observation endpoints.

Route shapes match what the frontend DAO expects
(`frontend/src/Dao/observations.js`):
    GET  /users/{user_id}/observations
    POST /observations
    GET  /observations/{observation_id}
"""

from fastapi import APIRouter, HTTPException, status

from app.models.observation import Observation, ObservationCreate
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
