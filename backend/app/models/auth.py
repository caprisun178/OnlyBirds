"""Sign-in models. See docs/features/user-profiles.md#auth."""

from datetime import datetime

from pydantic import BaseModel

from app.models.user import UserProfile


class GoogleSignIn(BaseModel):
    # The `credential` string Google's sign-in button hands the frontend.
    credential: str


class AuthSession(BaseModel):
    """What sign-in returns. `token` goes in `Authorization: Bearer ...` on
    every later request; `name` is Google's display name, for greeting the
    user before they've picked a username."""

    token: str
    expires_at: datetime
    name: str | None = None
    profile: UserProfile


class AuthConfig(BaseModel):
    """Public sign-in config for the frontend. `google_client_id` is null
    while sign-in isn't configured on this server."""

    google_client_id: str | None = None
