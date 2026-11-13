"""Typed application settings, loaded from environment variables (and `.env` in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
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
    # Super-Admin connection (schooltrack_platform, BYPASSRLS). Platform endpoints answer
    # 503 when it is not configured.
    platform_database_url: PostgresDsn | None = None
    # Background worker connection (schooltrack_worker): outbox and notifications only.
    worker_database_url: PostgresDsn | None = None
    # Redis: Celery broker and login rate limiting. Both are disabled when unset.
    redis_url: str | None = None
    push_provider: Literal["log", "expo"] = "log"
    notification_max_attempts: int = Field(default=5, ge=1, le=20)
    login_max_attempts: int = Field(default=10, ge=1)
    login_window_s: int = Field(default=900, ge=60)
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_echo: bool = False

    # Authentication
    jwt_secret: SecretStr
    jwt_issuer: str = "schooltrack"
    jwt_audience: str = "schooltrack-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)

    # Geolocation validation defaults (experimental values from the project brief;
    # institutions will be able to override them).
    geofence_default_radius_m: float = Field(default=100.0, gt=0, le=5_000)
    gps_max_accuracy_m: float = Field(default=30.0, gt=0, le=1_000)
    location_max_age_s: int = Field(default=30, gt=0, le=600)
    request_max_age_s: int = Field(default=15, gt=0, le=600)
    clock_skew_tolerance_s: int = Field(default=5, ge=0, le=120)
    # Faster than this between two consecutive located events is physically implausible
    # for a school commute (40 m/s = 144 km/h) and is flagged for review.
    max_plausible_speed_m_s: float = Field(default=40.0, gt=0)
    movement_window_h: float = Field(default=12.0, gt=0, le=72)
    # Events recorded without connectivity may be synchronized up to this long afterwards.
    offline_max_age_h: float = Field(default=72.0, gt=0, le=24 * 14)
    geofence_min_area_m2: float = Field(default=100.0, gt=0)
    geofence_max_area_m2: float = Field(default=5_000_000.0, gt=0)  # 5 km²

    @model_validator(mode="after")
    def _check_deployed_environment(self) -> "Settings":
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("jwt_secret must be at least 32 characters")
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
