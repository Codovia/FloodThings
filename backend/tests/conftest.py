"""
Shared test fixtures for FloodPulse backend tests.

- Unit tests (test_health.py): run without database, DATABASE_URL is mocked away.
- Integration tests (test_health_integration.py): run against the real database,
  require DATABASE_URL and a running PostgreSQL instance.
"""
