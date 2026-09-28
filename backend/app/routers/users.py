"""User profile endpoints. See docs/features/user-profiles.md.

    POST  /users              create (or fill in) a user after first sign-in
    GET   /users/{username}   public profile
    PATCH /users/{id}         update avatar_url and/or default_region

`id` in the PATCH path is the external id (e.g. 'u1').
"""

from fastapi import APIRouter, HTTPException, status

from app.models.user import UserCreate, UserProfile, UserUpdate
from app.services import user as user_service

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate):
    try:
        return await user_service.create_user(payload)
    except user_service.UsernameTaken:
        raise HTTPException(status_code=409, detail="Username already taken")


@router.get("/users/{username}", response_model=UserProfile)
async def get_user(username: str):
    profile = await user_service.get_profile_by_username(username)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.patch("/users/{user_id}", response_model=UserProfile)
async def update_user(user_id: str, changes: UserUpdate):
    profile = await user_service.update_user(user_id, changes)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile