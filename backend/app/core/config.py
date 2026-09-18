"""
FloodPulse application configuration.

All configuration is loaded from environment variables. No credentials
are hardcoded. DATABASE_URL is optional at import time so that basic
API health tests can run without a live database.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application environment: development, staging, production.
    app_env: str = "development"

    # Database connection string.
    # Optional at import time — required only when database operations are
    # actually performed (health checks, queries, migrations).
    # NEVER supply a default that contains a password.
    database_url: str | None = None

    # Background Scheduler (Phase 2.5)
    scheduler_enabled: bool = True
    openmeteo_ingestion_interval_minutes: int = 60

    # Source Health Internal Operational Policy (Phase 2.5)
    # NOTE: These are FloodPulse internal project policies, NOT upstream provider SLAs.
    openmeteo_freshness_threshold_hours: int = 4
    source_health_consecutive_failure_threshold: int = 3


def get_settings() -> Settings:
    """Return application settings. Cached per-process by FastAPI Depends."""
    return Settings()
