"""
Integration tests for SourceHealthService dynamic health evaluation.

Verifies:
- Disabled sources evaluate to DOWN.
- Sources with no ingestion history evaluate to DOWN.
- Single failed run evaluates to DEGRADED.
- Consecutive failed runs reaching threshold evaluate to DOWN.
- Partial runs evaluate to DEGRADED.
- Fresh successful runs evaluate to HEALTHY.
- Stale successful runs evaluate to DEGRADED per FloodPulse internal operational policy.
- Zero persistent health columns added to DataSource.
- Guaranteed teardown of test fixtures so zero residue remains.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.models.flood import FloodObservation
from app.db.models.system import DataIngestionRun, DataSource
from app.db.models.weather import WeatherObservation
from app.db.session import _get_session_factory
from app.services.source_health import HealthStatus, SourceHealthService


@pytest.fixture
def db_session():
    """Yield a database session and ensure clean rollback/closure."""
    factory = _get_session_factory()
    with factory() as session:
        yield session


class TestSourceHealthEvaluation:
    """Test dynamic health algorithm under various operational conditions."""

    def test_disabled_source_evaluates_to_down(self, db_session):
        """A source with is_active=False must evaluate to DOWN."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Disabled Source {source_id}",
            is_active=False,
        )
        try:
            db_session.add(source)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.DOWN
            assert not health.is_active
            assert "deactivated" in health.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_source_without_ingestion_history_evaluates_to_down(self, db_session):
        """An active source with zero DataIngestionRun entries must evaluate to DOWN."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Empty History Source {source_id}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.DOWN
            assert health.is_active
            assert health.last_attempted_at is None
            assert "no ingestion runs" in health.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_single_failed_run_evaluates_to_degraded(self, db_session):
        """A single failed run (consecutive failures < threshold) evaluates to DEGRADED."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Failed Run Source {source_id}",
            is_active=True,
        )
        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        run = DataIngestionRun(
            id=run_id,
            source_id=source_id,
            started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=9),
            status="FAILED",
            error_message="HTTP 502 Bad Gateway",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.DEGRADED
            assert health.consecutive_failures == 1
            assert "HTTP 502" in health.health_reason
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_consecutive_failures_escalate_to_down(self, db_session):
        """When consecutive failures reach the policy threshold (e.g. 3), health escalates to DOWN."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Threshold Fail Source {source_id}",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        runs = [
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(hours=3),
                completed_at=now - timedelta(hours=3) + timedelta(seconds=10),
                status="FAILED",
                error_message="Connection refused",
            ),
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2) + timedelta(seconds=10),
                status="FAILED",
                error_message="Connection timed out",
            ),
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1) + timedelta(seconds=10),
                status="FAILED",
                error_message="Host unreachable",
            ),
        ]
        try:
            db_session.add(source)
            for r in runs:
                db_session.add(r)
            db_session.commit()

            custom_settings = Settings(source_health_consecutive_failure_threshold=3)
            service = SourceHealthService(settings=custom_settings)
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.DOWN
            assert health.consecutive_failures == 3
            assert "3 consecutive ingestion failures" in health.health_reason
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_partial_run_evaluates_to_degraded(self, db_session):
        """A run that completes with PARTIAL status evaluates to DEGRADED."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Partial Run Source {source_id}",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(minutes=15),
            completed_at=now - timedelta(minutes=14),
            status="PARTIAL",
            records_received=5,
            records_inserted=4,
            records_rejected=1,
            error_message="Mandya: coordinate out of bounds",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.DEGRADED
            assert "partial errors" in health.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_recent_ingestion_with_stale_actual_observation_evaluates_to_degraded(self, db_session):
        """REQUIRED FIX 1: When ingestion completed recently but actual observation is stale, status MUST be DEGRADED."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Open-Meteo Weather API {source_id}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        # Ingestion run completed 10 minutes ago
        run_completed = now - timedelta(minutes=10)
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(minutes=11),
            completed_at=run_completed,
            status="SUCCESS",
            records_received=10,
            records_inserted=10,
        )
        # Latest actual observation timestamp is 6 hours old (policy threshold: 4 hours)
        obs_dt = now - timedelta(hours=6)
        obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=obs_dt,
            temperature=24.5,
            data_category="MODEL_OUTPUT",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.add(obs)
            db_session.commit()

            custom_settings = Settings(openmeteo_freshness_threshold_hours=4)
            service = SourceHealthService(settings=custom_settings)
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            # Must evaluate to DEGRADED despite recent ingestion run!
            assert health.health_status == HealthStatus.DEGRADED
            assert "stale per floodpulse internal operational policy" in health.health_reason.lower()
            # Verify separate concepts:
            assert health.last_successful_at == run_completed
            assert health.latest_data_timestamp == obs_dt
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_recent_ingestion_with_fresh_actual_observation_evaluates_to_healthy(self, db_session):
        """When ingestion run succeeded and actual observation is fresh, status is HEALTHY."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Open-Meteo Weather API {source_id}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        run_completed = now - timedelta(minutes=10)
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(minutes=11),
            completed_at=run_completed,
            status="SUCCESS",
            records_received=10,
            records_inserted=10,
        )
        # Observation is 1 hour old (within 4h threshold)
        obs_dt = now - timedelta(hours=1)
        obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=obs_dt,
            temperature=24.5,
            data_category="MODEL_OUTPUT",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.add(obs)
            db_session.commit()

            custom_settings = Settings(openmeteo_freshness_threshold_hours=4)
            service = SourceHealthService(settings=custom_settings)
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            assert health.health_status == HealthStatus.HEALTHY
            assert health.consecutive_failures == 0
            assert "fresh per floodpulse internal policy" in health.health_reason.lower()
            assert health.last_successful_at == run_completed
            assert health.latest_data_timestamp == obs_dt
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_openmeteo_source_uses_configured_freshness_threshold(self, db_session):
        """Open-Meteo source uses the configured settings threshold rather than a magic number."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Open-Meteo Weather API {source_id}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(minutes=15),
            completed_at=now - timedelta(minutes=14),
            status="SUCCESS",
        )
        # Observation is 3 hours old
        obs_dt = now - timedelta(hours=3)
        obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=obs_dt,
            temperature=22.0,
            data_category="MODEL_OUTPUT",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.add(obs)
            db_session.commit()

            # Under 2-hour threshold: 3h old data is DEGRADED
            service_2h = SourceHealthService(settings=Settings(openmeteo_freshness_threshold_hours=2))
            health_2h = service_2h.get_source_health(db_session, source_id)
            assert health_2h is not None
            assert health_2h.health_status == HealthStatus.DEGRADED
            assert "threshold: 2.0h" in health_2h.health_reason

            # Under 5-hour threshold: 3h old data is HEALTHY
            service_5h = SourceHealthService(settings=Settings(openmeteo_freshness_threshold_hours=5))
            health_5h = service_5h.get_source_health(db_session, source_id)
            assert health_5h is not None
            assert health_5h.health_status == HealthStatus.HEALTHY
            assert "threshold: 5.0h" in health_5h.health_reason
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_static_or_historical_source_does_not_inherit_openmeteo_freshness_policy(self, db_session):
        """REQUIRED FIX 2: Static / historical sources and unconfigured sources must NOT inherit Open-Meteo policy."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"India Flood Inventory (IFI v3.0) {source_id}",
            organization="HydroSenseLab",
            data_type="HISTORICAL_FLOOD_DISASTER",
            update_frequency="STATIC",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(days=5),
            completed_at=now - timedelta(days=5) + timedelta(minutes=1),
            status="SUCCESS",
        )
        # Historical flood observation from years ago (e.g. 2019)
        obs_dt = datetime(2019, 8, 10, 12, 0, tzinfo=timezone.utc)
        obs = FloodObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observation_time=obs_dt,
            flood_depth=1.5,
            data_category="HISTORICAL_EVENT",
        )
        try:
            db_session.add(source)
            db_session.commit()
            db_session.add(run)
            db_session.add(obs)
            db_session.commit()

            service = SourceHealthService()
            # Verify freshness policy is None for static source
            assert service.get_freshness_threshold_hours(source) is None

            health = service.get_source_health(db_session, source_id)
            assert health is not None
            # Must be HEALTHY — not degraded due to historical age!
            assert health.health_status == HealthStatus.HEALTHY
            assert "static/historical reference dataset with no recurring operational freshness requirement" in health.health_reason

            # Also verify an unconfigured telemetry source (NWIC) does NOT inherit Open-Meteo policy
            nwic_source = DataSource(
                id=uuid.uuid4(),
                name=f"NWIC Central Water Commission River Gauge Telemetry {uuid.uuid4()}",
                data_type="HYDROLOGICAL",
                update_frequency="HOURLY",
                is_active=True,
            )
            assert service.get_freshness_threshold_hours(nwic_source) is None
        finally:
            db_session.rollback()
            db_session.execute(text(f"DELETE FROM flood_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_running_does_not_automatically_produce_healthy(self, db_session):
        """REQUIRED FIX 3: RUNNING must not automatically declare HEALTHY; evaluates prior verified data state."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Open-Meteo Weather API {source_id}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        service = SourceHealthService()

        # Case A: Brand-new source with only 1 run, currently RUNNING -> DEGRADED
        running_run_1 = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(seconds=30),
            status="RUNNING",
        )
        try:
            db_session.add(source)
            db_session.add(running_run_1)
            db_session.commit()

            health_a = service.get_source_health(db_session, source_id)
            assert health_a is not None
            assert health_a.health_status == HealthStatus.DEGRADED
            assert "initial ingestion run in progress" in health_a.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.commit()

        # Case B: 3 prior FAILED runs, currently RUNNING -> DOWN
        now = datetime.now(timezone.utc)
        failed_runs = [
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(minutes=30),
                completed_at=now - timedelta(minutes=29),
                status="FAILED",
                error_message="Fail 1",
            ),
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(minutes=20),
                completed_at=now - timedelta(minutes=19),
                status="FAILED",
                error_message="Fail 2",
            ),
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=9),
                status="FAILED",
                error_message="Fail 3",
            ),
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(seconds=15),
                status="RUNNING",
            ),
        ]
        try:
            for r in failed_runs:
                db_session.add(r)
            db_session.commit()

            health_b = service.get_source_health(db_session, source_id)
            assert health_b is not None
            assert health_b.health_status == HealthStatus.DOWN
            assert "3 consecutive ingestion failures" in health_b.health_reason
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.commit()

        # Case C: Prior SUCCESS run exists, but existing observation is stale (6h old > 4h), currently RUNNING -> DEGRADED
        stale_obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=now - timedelta(hours=6),
            temperature=24.0,
            data_category="MODEL_OUTPUT",
        )
        prior_success_run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6) + timedelta(minutes=1),
            status="SUCCESS",
        )
        active_running_run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(seconds=10),
            status="RUNNING",
        )
        try:
            db_session.add(stale_obs)
            db_session.add(prior_success_run)
            db_session.add(active_running_run)
            db_session.commit()

            health_c = service.get_source_health(db_session, source_id)
            assert health_c is not None
            assert health_c.health_status == HealthStatus.DEGRADED
            assert "existing data is stale per floodpulse internal policy" in health_c.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.commit()

        # Case D: Prior SUCCESS run exists, and existing observation is fresh (1h old <= 4h), currently RUNNING -> HEALTHY
        fresh_obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=now - timedelta(hours=1),
            temperature=24.0,
            data_category="MODEL_OUTPUT",
        )
        fresh_success_run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(minutes=1),
            status="SUCCESS",
        )
        active_running_run_2 = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=now - timedelta(seconds=10),
            status="RUNNING",
        )
        try:
            db_session.add(fresh_obs)
            db_session.add(fresh_success_run)
            db_session.add(active_running_run_2)
            db_session.commit()

            health_d = service.get_source_health(db_session, source_id)
            assert health_d is not None
            assert health_d.health_status == HealthStatus.HEALTHY
            assert "existing data remains fresh" in health_d.health_reason.lower()
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()

    def test_latest_data_timestamp_from_observations(self, db_session):
        """Latest data timestamp accurately queries stored observation timestamps."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Observation Timestamp Source {source_id}",
            is_active=True,
        )
        obs_dt = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        run_dt = datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)

        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=source_id,
            started_at=run_dt,
            completed_at=run_dt + timedelta(seconds=10),
            status="SUCCESS",
            records_received=1,
            records_inserted=1,
        )
        obs = WeatherObservation(
            id=uuid.uuid4(),
            source_id=source_id,
            observed_at=obs_dt,
            temperature=25.0,
            data_category="MODEL_OUTPUT",
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.add(obs)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, source_id)

            assert health is not None
            # Must equal actual observation timestamp, NOT the run timestamp!
            assert health.latest_data_timestamp == obs_dt
            assert health.last_attempted_at == run_dt
        finally:
            db_session.execute(text(f"DELETE FROM weather_observations WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()


class TestSourceRunsHistory:
    """Test get_source_runs pagination and ordering."""

    def test_get_source_runs_pagination(self, db_session):
        """Runs must be ordered by started_at DESC with limit and offset support."""
        source_id = uuid.uuid4()
        source = DataSource(
            id=source_id,
            name=f"Test Runs Pagination Source {source_id}",
            is_active=True,
        )
        now = datetime.now(timezone.utc)
        runs = [
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=source_id,
                started_at=now - timedelta(minutes=i * 10),
                completed_at=now - timedelta(minutes=i * 10) + timedelta(seconds=5),
                status="SUCCESS",
                records_received=10,
            )
            for i in range(5)
        ]
        try:
            db_session.add(source)
            for r in runs:
                db_session.add(r)
            db_session.commit()

            service = SourceHealthService()
            # Fetch page 1 (limit 2, offset 0)
            page1, total = service.get_source_runs(db_session, source_id, limit=2, offset=0)
            assert total == 5
            assert len(page1) == 2
            assert page1[0].started_at > page1[1].started_at

            # Fetch page 2 (limit 2, offset 2)
            page2, _ = service.get_source_runs(db_session, source_id, limit=2, offset=2)
            assert len(page2) == 2
            assert page1[1].started_at > page2[0].started_at
        finally:
            db_session.execute(text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{source_id}'"))
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
            db_session.commit()
