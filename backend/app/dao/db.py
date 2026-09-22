"""Shared Postgres connection pool (Neon). Lazy — nothing connects until the
first query, so the server still starts fine with `DATABASE_URL` unset (see
`observation_repo.py`, which falls back to the in-memory store in that case).

Sync psycopg, not async, on purpose: psycopg's async mode needs a
selector-based asyncio event loop, but Windows' asyncio default (since 3.8)
is Proactor, and by the time our code imports under `uvicorn main:app`,
uvicorn has already created its event loop from the ambient policy — too
late to swap it out. Sync psycopg run through `asyncio.to_thread` (see each
repo method in `observation_repo.py`) sidesteps that entirely and behaves
the same on every platform.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        # Small pool — Neon's free tier caps concurrent connections, and this
        # is one API process, not a fleet.
        _pool = ConnectionPool(conninfo=settings.database_url, min_size=1, max_size=5, open=True)
    return _pool
