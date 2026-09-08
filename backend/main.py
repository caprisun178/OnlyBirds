"""Shim so `uvicorn main:app --reload` works from the backend/ directory,
matching the README. The real app lives in app/main.py.
"""

from app.main import app

__all__ = ["app"]
