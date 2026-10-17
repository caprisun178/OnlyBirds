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
    # Whether to show admin screens. Display only — the backend checks
    # ADMIN_EMAILS on every admin request regardless.
    is_admin: bool = False


class Me(UserProfile):
    """GET /auth/me: the signed-in user's own profile plus `is_admin`
    (kept off UserProfile itself, which is also the public profile)."""

    is_admin: bool = False


class AuthConfig(BaseModel):
    """Public sign-in config for the frontend. `google_client_id` is null
    while sign-in isn't configured on this server."""

    google_client_id: str | None = None
