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

    # CORS — comma-separated in the environment, list in code.
    cors_origins: str = "http://localhost:3000,http://localhost:4174,http://localhost:5173,http://localhost:8081"

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
