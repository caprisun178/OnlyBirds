"""User model.

Auth is delegated to a hosted provider (Auth0 / Supabase Auth); we only store
the provider's subject id plus email. The base server does not verify tokens yet
— `auth_provider_id` is taken at face value.
"""

from pydantic import BaseModel


class User(BaseModel):
    id: str | None = None
    email: str | None = None
    auth_provider_id: str
