"""Auth dependencies shared by the routers. See docs/features/user-profiles.md#auth.

Every request may carry `Authorization: Bearer <session token>` (issued by
POST /auth/google). These turn that into "who is calling" and enforce that
user-scoped endpoints only act on the caller's own data:

    current_user_id      the signed-in user's id, or None — never raises
    require_user         the signed-in user's id, else 401
    require_self         for `/users/{user_id}/...` routes: 401 if signed
                         out, 403 if `user_id` isn't the caller
    optional_self        for an optional `?user_id=` query param (e.g. "mark
                         the species I've seen"): fine when absent, else the
                         same check as require_self
"""

from fastapi import Depends, Header, HTTPException, Query, status

from app.services import auth as auth_service


async def current_user_id(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return auth_service.verify_session_token(token)
    except auth_service.InvalidSession:
        # Expired/garbage token: treat as signed out. Endpoints that need a
        # user then 401, which is the frontend's cue to drop the session.
        return None


async def require_user(user_id: str | None = Depends(current_user_id)) -> str:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def ensure_self(current: str, user_id: str) -> None:
    if current != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your account")


async def require_self(user_id: str, current: str = Depends(require_user)) -> str:
    ensure_self(current, user_id)
    return user_id


async def optional_self(
    user_id: str | None = Query(default=None),
    current: str | None = Depends(current_user_id),
) -> str | None:
    if user_id is None:
        return None
    if current is None:
        await require_user(None)  # raises the same 401 as everywhere else
    ensure_self(current, user_id)
    return user_id
