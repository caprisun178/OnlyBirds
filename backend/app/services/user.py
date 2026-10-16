"""Business logic for user profiles. See docs/features/user-profiles.md.

The profile's life list total reuses get_life_list, so it always matches what
the Life List page shows. (The doc's `life_list_entries` table doesn't exist:
the life list is derived from observations.)
"""

from __future__ import annotations

from app.dao.user_repo import user_repo
from app.models.user import User, UserCreate, UserProfile, UserUpdate
from app.services.life_list import get_life_list


class UsernameTaken(Exception):
    """Raised when a username already belongs to a different user."""


async def _to_profile(user: User) -> UserProfile:
    life_list = await get_life_list(user.auth_provider_id)
    return UserProfile(
        id=user.auth_provider_id,
        username=user.username,
        avatar_url=user.avatar_url,
        default_region=user.default_region,
        life_list_total=len(life_list),
        # TODO: count the user's stickers once the Stickers feature merges.
        sticker_count=0,
    )


async def create_user(payload: UserCreate) -> UserProfile:
    if payload.username:
        holder = await user_repo.get_by_username(payload.username)
        if holder and holder.auth_provider_id != payload.auth_provider_id:
            raise UsernameTaken(payload.username)
    user = await user_repo.create(payload)
    return await _to_profile(user)


async def get_profile_by_username(username: str) -> UserProfile | None:
    user = await user_repo.get_by_username(username)
    return await _to_profile(user) if user else None


async def get_profile_by_id(auth_id: str) -> UserProfile | None:
    user = await user_repo.get_by_auth_id(auth_id)
    return await _to_profile(user) if user else None


async def update_user(auth_id: str, changes: UserUpdate) -> UserProfile | None:
    user = await user_repo.update(auth_id, changes)
    return await _to_profile(user) if user else None

async def sign_in_user(auth_id: str, email: str | None = None, picture: str | None = None) -> UserProfile:
    """Get-or-create the user behind a sign-in (app/services/auth.py). The
    first sign-in creates the row; `picture` only fills an empty avatar, so a
    photo the user uploaded themselves is never overwritten."""
    user = await user_repo.create(UserCreate(auth_provider_id=auth_id, email=email))
    if user.avatar_url is None and picture:
        user = await user_repo.update(auth_id, UserUpdate(avatar_url=picture))
    return await _to_profile(user)
