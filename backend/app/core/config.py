"""Typed application settings, loaded from environment variables (and `.env` in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = "local"
    app_name: str = "SchoolTrack API"
    api_v1_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    # Runtime connection: must use the least-privileged role (schooltrack_app), so RLS applies.
    database_url: PostgresDsn
    # Owner connection used only by Alembic. Falls back to database_url when unset.
    migrations_database_url: PostgresDsn | None = None
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_echo: bool = False

    # Geolocation validation defaults (experimental values from the project brief;
    # institutions will be able to override them).
    geofence_default_radius_m: float = Field(default=100.0, gt=0, le=5_000)
    gps_max_accuracy_m: float = Field(default=30.0, gt=0, le=1_000)
    location_max_age_s: int = Field(default=30, gt=0, le=600)
    request_max_age_s: int = Field(default=15, gt=0, le=600)

    @model_validator(mode="after")
    def _check_deployed_environment(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if "*" in self.cors_origins:
                raise ValueError("CORS wildcard is not allowed outside local/test environments")
            if self.db_echo:
                raise ValueError("db_echo would log personal data; disable it outside local/test")
        return self

    @property
    def is_deployed(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
