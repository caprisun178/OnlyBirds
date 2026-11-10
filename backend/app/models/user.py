"""User model.

Auth is delegated to a hosted provider (Auth0 / Supabase Auth); we only store
the provider's subject id plus email. The base server does not verify tokens yet
— `auth_provider_id` is taken at face value.
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Free text shown on the profile; separate from the unique `username` handle.
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class User(BaseModel):
    id: str | None = None
    email: str | None = None
    auth_provider_id: str
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    default_region: str = "world"
    favorite_species: str | None = None
    favorite_common_name: str | None = None


class UserCreate(BaseModel):
    auth_provider_id: str
    username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,30}$")
    email: str | None = None


class UserUpdate(BaseModel):
    """Only the fields the user may change. None means 'leave as is'."""

    display_name: DisplayName | None = None
    avatar_url: str | None = None
    default_region: str | None = None
    favorite_species: str | None = None
    favorite_common_name: str | None = None


class UserProfile(BaseModel):
    """What the API returns: no email, plus the derived totals.

    `id` is the external id (`auth_provider_id`, e.g. 'u1'), never the
    internal Postgres uuid, to match observations and testProfile.js.
    """

    id: str
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    default_region: str = "world"
    favorite_species: str | None = None
    favorite_common_name: str | None = None
    life_list_total: int = 0
    sticker_count: int = 0