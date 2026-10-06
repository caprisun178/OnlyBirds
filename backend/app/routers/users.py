"""User profile endpoints. See docs/features/user-profiles.md.

    POST  /users              create (or fill in) a user after first sign-in
    GET   /users/by-id/{id}   profile by the external id (e.g. 'u1') — what every
                               other `/users/{user_id}/...` endpoint in this app
                               (pins, life-list, observations, ...) already means
                               by "user id"
    GET   /users/{username}   public profile, by the user-chosen username instead
    PATCH /users/{id}         update avatar_url and/or default_region

`id` in the PATCH path (and the new by-id GET) is the external id. Defined
*before* `GET /users/{username}` below so the literal `by-id` segment isn't
swallowed as someone's username — Starlette matches path routes in
registration order.
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


@router.get("/users/by-id/{user_id}", response_model=UserProfile)
async def get_user_by_id(user_id: str):
    profile = await user_service.get_profile_by_id(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


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