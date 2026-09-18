"""
Shared test fixtures for FloodPulse backend tests.

- Unit tests (test_health.py): run without database, DATABASE_URL is mocked away.
- Integration tests (test_health_integration.py): run against the real database,
  require DATABASE_URL and a running PostgreSQL instance.
- Scheduler isolation: background scheduler is disabled by default during testing
  (SCHEDULER_ENABLED=false) so tests never launch background ingestion loops or make
  unmocked external network calls.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_scheduler_by_default(monkeypatch):
    """Ensure background scheduler does not start automatically during tests."""
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
