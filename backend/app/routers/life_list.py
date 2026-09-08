"""Life-list endpoint — derived from the user's stored observations."""

from fastapi import APIRouter

from app.models.life_list import LifeListEntry
from app.services import life_list as life_list_service

router = APIRouter(tags=["life-list"])


@router.get("/users/{user_id}/life-list", response_model=list[LifeListEntry])
async def get_life_list(user_id: str):
    return await life_list_service.get_life_list(user_id)
