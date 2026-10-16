"""Pinned Birds endpoints. See docs/features/pinned-birds.md.

    GET    /users/{user_id}/pins
    POST   /users/{user_id}/pins
    PATCH  /users/{user_id}/pins/{scientific_name}
    DELETE /users/{user_id}/pins/{scientific_name}

`{scientific_name}` in the path is URL-encoded by the caller as needed
(e.g. "Branta canadensis" -> "Branta%20canadensis") — FastAPI decodes it
automatically.
"""

from fastapi import APIRouter, HTTPException, status

from app.models.pin import PinCreate, PinnedBird, PinRegionUpdate
from app.services import pins as pins_service

router = APIRouter(tags=["pins"])


@router.get("/users/{user_id}/pins", response_model=list[PinnedBird])
async def list_pins(user_id: str):
    return await pins_service.list_pins(user_id)


@router.post("/users/{user_id}/pins", response_model=PinnedBird, status_code=status.HTTP_201_CREATED)
async def create_pin(user_id: str, payload: PinCreate):
    try:
        return await pins_service.pin(user_id, payload)
    except pins_service.AlreadyOnLifeList:
        raise HTTPException(status_code=409, detail="Already on your life list — nothing to chase")


@router.patch("/users/{user_id}/pins/{scientific_name}", response_model=PinnedBird)
async def update_pin(user_id: str, scientific_name: str, payload: PinRegionUpdate):
    pin = await pins_service.update_pin_region(user_id, scientific_name, payload.region)
    if pin is None:
        raise HTTPException(status_code=404, detail="Pin not found")
    return pin


@router.delete("/users/{user_id}/pins/{scientific_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pin(user_id: str, scientific_name: str):
    deleted = await pins_service.unpin(user_id, scientific_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pin not found")
