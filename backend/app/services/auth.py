"""Sign-in and session tokens. See docs/features/user-profiles.md#auth.

Google proves who the user is once, at sign-in (app/dao/google_auth.py).
After that the app uses its own session token so it doesn't depend on
Google's 1-hour ID-token lifetime: `<payload>.<signature>`, where payload is
base64url JSON `{"sub": user_id, "exp": unix_seconds}` and signature is
HMAC-SHA256 of the payload under SESSION_SECRET. Stateless — nothing is
stored server-side, so signing out is just the frontend forgetting it.

User ids for Google accounts are `google:<sub>` (Google's stable account id),
stored as `users.auth_provider_id` — the same "external id" every
`/users/{user_id}/...` endpoint already takes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.dao import google_auth
from app.models.auth import AuthSession
from app.services import user as user_service


class AuthNotConfigured(Exception):
    """GOOGLE_CLIENT_ID / SESSION_SECRET aren't set on this server."""


class InvalidSession(Exception):
    """Session token is missing, malformed, tampered with, or expired."""


InvalidGoogleToken = google_auth.InvalidGoogleToken


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def _secret() -> str:
    secret = get_settings().session_secret
    if not secret:
        raise AuthNotConfigured("SESSION_SECRET is not set")
    return secret


def create_session_token(user_id: str, now: float | None = None) -> tuple[str, datetime]:
    now = time.time() if now is None else now
    exp = int(now + get_settings().session_ttl_days * 86400)
    payload_b64 = _b64encode(json.dumps({"sub": user_id, "exp": exp}).encode())
    token = f"{payload_b64}.{_sign(payload_b64, _secret())}"
    return token, datetime.fromtimestamp(exp, tz=timezone.utc)


def verify_session_token(token: str, now: float | None = None) -> str:
    """Return the user id the token was issued to, or raise InvalidSession."""
    secret = get_settings().session_secret
    if not secret:
        # Sign-in isn't configured, so no token can be valid — everyone is
        # signed out rather than this being a server error on every request.
        raise InvalidSession("Sign-in is not configured")
    try:
        payload_b64, signature = token.split(".")
    except ValueError as exc:
        raise InvalidSession("Malformed session token") from exc
    if not hmac.compare_digest(signature, _sign(payload_b64, secret)):
        raise InvalidSession("Bad session token signature")
    try:
        payload = json.loads(_b64decode(payload_b64))
        user_id, exp = payload["sub"], payload["exp"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidSession("Malformed session token") from exc
    if (time.time() if now is None else now) >= exp:
        raise InvalidSession("Session expired")
    return user_id


async def sign_in_with_google(credential: str) -> AuthSession:
    client_id = get_settings().google_client_id
    if not client_id:
        raise AuthNotConfigured("GOOGLE_CLIENT_ID is not set")
    _secret()  # fail before touching the DB if we couldn't issue a session anyway

    claims = await google_auth.verify_id_token(credential, client_id)
    user_id = f"google:{claims['sub']}"

    # Their Google photo becomes the avatar until they upload their own.
    profile = await user_service.sign_in_user(user_id, claims.get("email"), claims.get("picture"))
    token, expires_at = create_session_token(user_id)
    return AuthSession(token=token, expires_at=expires_at, name=claims.get("name"), profile=profile)
