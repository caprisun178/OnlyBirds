"""Sign-in endpoints. See docs/features/user-profiles.md#auth.

    GET  /auth/config    {google_client_id} — public; null while unconfigured
    POST /auth/google    {credential} -> {token, expires_at, name, profile}
    GET  /auth/me        the signed-in user's profile (401 if signed out)

Sign-out has no endpoint: session tokens are stateless, so the frontend just
discards its copy.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_settings
from app.models.auth import AuthConfig, AuthSession, GoogleSignIn
from app.models.user import UserProfile
from app.routers.deps import require_user
from app.services import auth as auth_service
from app.services import user as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfig)
async def auth_config():
    settings = get_settings()
    enabled = bool(settings.google_client_id and settings.session_secret)
    return AuthConfig(google_client_id=settings.google_client_id if enabled else None)


@router.post("/google", response_model=AuthSession)
async def sign_in_with_google(payload: GoogleSignIn):
    try:
        return await auth_service.sign_in_with_google(payload.credential)
    except auth_service.AuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except auth_service.InvalidGoogleToken as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Google error: {exc}") from exc


@router.get("/me", response_model=UserProfile)
async def me(user_id: str = Depends(require_user)):
    profile = await user_service.get_profile_by_id(user_id)
    if profile is None:
        # Valid token for a user whose row is gone (e.g. DB reset).
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return profile
