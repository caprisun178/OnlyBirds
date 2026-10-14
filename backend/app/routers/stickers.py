"""Sticker catalog and user collection endpoints."""

from fastapi import APIRouter

from app.models.sticker import Sticker, StickerShelf
from app.services import stickers as sticker_service

router = APIRouter(tags=["stickers"])


@router.get("/stickers", response_model=list[Sticker])
async def get_stickers():
    """Return the complete sticker catalog."""
    return await sticker_service.list_stickers()


@router.get("/users/{user_id}/stickers", response_model=StickerShelf)
async def get_user_stickers(user_id: str):
    """Return earned and locked stickers for a user."""
    return await sticker_service.get_sticker_shelf(user_id)