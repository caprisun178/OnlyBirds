"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Only Birds API"

    # External APIs
    ebird_api_key: str | None = None
    ebird_base_url: str = "https://api.ebird.org/v2"
    inat_base_url: str = "https://api.inaturalist.org/v1"
    http_timeout_seconds: float = 15.0

    # CORS — comma-separated in the environment, list in code. Both
    # `localhost` and `127.0.0.1` for each dev port: browsers treat them as
    # different origins even though they're the same machine, so a frontend
    # opened at one when only the other is whitelisted fails every API call
    # with a bare "Failed to fetch" (no CORS-specific message) — a real case
    # of this, see docs/index.md's environment-variables table.
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:4174,http://127.0.0.1:4174,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8081,http://127.0.0.1:8081"
    )

    # Roadmap step 3; unused by the base server.
    database_url: str | None = None

    # Object storage — Supabase Storage bucket for observation photos
    # (see docs/features/add-observation.md). Photo upload is disabled
    # (503) until both of these are set.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "observation-photos"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
