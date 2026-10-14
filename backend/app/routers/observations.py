"""User-owned observation endpoints.

Route shapes match what the frontend DAO expects
(`frontend/src/Dao/observations.js`):
    GET   /users/{user_id}/observations
    POST  /observations
    GET   /observations/{observation_id}
    PATCH /observations/{observation_id}
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.models.observation import Observation, ObservationCreate, ObservationUpdate
from app.services import observation as observation_service

router = APIRouter(tags=["observations"])


@router.get("/users/{user_id}/observations", response_model=list[Observation])
async def list_user_observations(user_id: str, scientific_name: str | None = Query(default=None)):
    """`scientific_name` scopes this to one species — e.g. Life List's "view
    this species' own log" entry point — instead of always shipping a user's
    entire observation history just to show a handful of rows for one bird.
    """
    return await observation_service.list_observations(user_id, scientific_name)


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
