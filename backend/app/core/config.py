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
        env_file=".env",
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


def get_settings() -> Settings:
    """Return application settings. Cached per-process by FastAPI Depends."""
    return Settings()
