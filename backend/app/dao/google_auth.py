"""
==============================
Google Sign-In token verification
Description:
Raw access to Google's `tokeninfo` endpoint — no business logic. The
frontend's Google sign-in button hands back an ID token (a JWT signed by
Google); this asks Google whether it's genuine and returns its claims.

`tokeninfo` instead of verifying the JWT signature locally (google-auth +
Google's rotating public keys) keeps this to the httpx we already depend on.
It's one extra round trip per *sign-in*, not per request — after sign-in the
app uses its own session token (app/services/auth.py) — so the cost is
negligible at this scale.

Docs: https://developers.google.com/identity/sign-in/web/backend-auth#calling-the-tokeninfo-endpoint
=============================
"""

import httpx

from app.config import get_settings

_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class InvalidGoogleToken(Exception):
    """The ID token is expired, forged, or was issued for another app."""


async def verify_id_token(id_token: str, client_id: str) -> dict:
    """Return the token's claims (`sub`, `email`, `name`, `picture`, ...) or
    raise InvalidGoogleToken. Google itself checks the signature and expiry;
    the audience and issuer checks are ours to do."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        resp = await client.get(_TOKENINFO_URL, params={"id_token": id_token})
    if resp.status_code != 200:
        raise InvalidGoogleToken("Google rejected the token")
    claims = resp.json()
    if claims.get("aud") != client_id:
        raise InvalidGoogleToken("Token was issued for a different app")
    if claims.get("iss") not in _VALID_ISSUERS:
        raise InvalidGoogleToken("Token was not issued by Google")
    if not claims.get("sub"):
        raise InvalidGoogleToken("Token has no subject")
    return claims
