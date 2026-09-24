"""
Focused integration tests for Mission 001 gap fields:
  - data_sources.authority_level
  - data_ingestion_runs.http_status_code

Verifies:
1. authority_level persistence with valid and NULL values.
2. http_status_code persistence on DataIngestionRun.
3. complete_ingestion_run() stores http_status_code when provided (HTTP 200).
4. complete_ingestion_run() stores http_status_code on failure (HTTP 4xx/5xx).
5. SourceHealthService exposes last_http_status_code from the latest run that recorded one.
6. SourceHealthService exposes authority_level from the DataSource.
7. Existing HEALTHY/DEGRADED/DOWN behavior is unaffected when http_status_code is absent.
8. Check constraint rejects invalid http_status_code values.
9. Check constraint rejects unknown authority_level values.

All tests guarantee teardown — zero residue in production tables.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models.system import DataIngestionRun, DataSource
from app.db.session import _get_session_factory
from app.ingestion.base import IngestionMetrics
from app.ingestion.registry import (
    complete_ingestion_run,
    get_or_create_data_source,
    start_ingestion_run,
)
from app.services.source_health import HealthStatus, SourceHealthService


@pytest.fixture
def db_session():
    """Yield a live database session with clean rollback/closure."""
    factory = _get_session_factory()
    with factory() as session:
        yield session


class TestAuthorityLevelPersistence:
    """Tests for data_sources.authority_level."""

    def test_authority_level_persists_valid_values(self, db_session):
        """Each valid authority_level value round-trips through PostgreSQL."""
        valid_levels = [
            "CORE",
            "SECONDARY",
            "REFERENCE",
            "PENDING",
            "CREDENTIAL_BLOCKED",
            "NOT_SUITABLE",
        ]
        created_ids: list[str] = []
        try:
            for level in valid_levels:
                sid = uuid.uuid4()
                created_ids.append(str(sid))
                source = DataSource(
                    id=sid,
                    name=f"Test AuthLevel {level} {sid}",
                    authority_level=level,
                    is_active=True,
                )
                db_session.add(source)
            db_session.commit()

            for sid_str in created_ids:
                s = db_session.get(DataSource, uuid.UUID(sid_str))
                assert s is not None
                assert s.authority_level in valid_levels
        finally:
            for sid_str in created_ids:
                db_session.execute(
                    text(f"DELETE FROM data_sources WHERE id = '{sid_str}'")
                )
            db_session.commit()

    def test_authority_level_nullable(self, db_session):
        """authority_level may be NULL — existing sources without a level are unaffected."""
        sid = uuid.uuid4()
        try:
            source = DataSource(
                id=sid,
                name=f"Test NULL AuthLevel {sid}",
                authority_level=None,
                is_active=True,
            )
            db_session.add(source)
            db_session.commit()

            reloaded = db_session.get(DataSource, sid)
            assert reloaded is not None
            assert reloaded.authority_level is None
        finally:
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_authority_level_check_constraint_rejects_invalid(self, db_session):
        """The CHECK constraint must reject an unrecognised authority_level value."""
        sid = uuid.uuid4()
        source = DataSource(
            id=sid,
            name=f"Test Bad AuthLevel {sid}",
            authority_level="MADE_UP_TIER",
            is_active=True,
        )
        db_session.add(source)
        with pytest.raises((IntegrityError, Exception)):
            db_session.commit()
        db_session.rollback()

    def test_authority_level_exposed_by_source_health_service(self, db_session):
        """SourceHealthService.get_source_health() must expose the authority_level field."""
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source = DataSource(
            id=sid,
            name=f"Open-Meteo CORE Source {sid}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            authority_level="CORE",
            is_active=True,
        )
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=sid,
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=4),
            status="SUCCESS",
            records_received=10,
            records_inserted=10,
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, sid)
            assert health is not None
            assert health.authority_level == "CORE"
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()


class TestHttpStatusCodePersistence:
    """Tests for data_ingestion_runs.http_status_code."""

    def test_http_status_code_persists_successful_200(self, db_session):
        """complete_ingestion_run() stores HTTP 200 on a successful run."""
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source = DataSource(
            id=sid,
            name=f"Test HTTP 200 Source {sid}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            run = start_ingestion_run(db_session, sid)
            metrics = IngestionMetrics(
                records_received=5,
                records_valid=5,
                records_inserted=5,
            )
            complete_ingestion_run(
                db_session, run, "SUCCESS", metrics, http_status_code=200
            )
            db_session.commit()

            reloaded = db_session.get(DataIngestionRun, run.id)
            assert reloaded is not None
            assert reloaded.status == "SUCCESS"
            assert reloaded.http_status_code == 200
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_http_status_code_persists_failure_4xx(self, db_session):
        """complete_ingestion_run() stores HTTP 403 on a failed run."""
        sid = uuid.uuid4()
        source = DataSource(
            id=sid,
            name=f"Test HTTP 403 Source {sid}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            run = start_ingestion_run(db_session, sid)
            metrics = IngestionMetrics(records_received=0)
            complete_ingestion_run(
                db_session,
                run,
                "FAILED",
                metrics,
                error_message="HTTP 403 Forbidden — credential required",
                http_status_code=403,
            )
            db_session.commit()

            reloaded = db_session.get(DataIngestionRun, run.id)
            assert reloaded is not None
            assert reloaded.status == "FAILED"
            assert reloaded.http_status_code == 403
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_http_status_code_persists_failure_5xx(self, db_session):
        """complete_ingestion_run() stores HTTP 503 on a server-error run."""
        sid = uuid.uuid4()
        source = DataSource(
            id=sid,
            name=f"Test HTTP 503 Source {sid}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            run = start_ingestion_run(db_session, sid)
            metrics = IngestionMetrics(records_received=0)
            complete_ingestion_run(
                db_session,
                run,
                "FAILED",
                metrics,
                error_message="HTTP 503 Service Unavailable",
                http_status_code=503,
            )
            db_session.commit()

            reloaded = db_session.get(DataIngestionRun, run.id)
            assert reloaded is not None
            assert reloaded.http_status_code == 503
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_http_status_code_nullable_for_non_http_ingestion(self, db_session):
        """complete_ingestion_run() leaves http_status_code NULL for file-based ingestion."""
        sid = uuid.uuid4()
        source = DataSource(
            id=sid,
            name=f"Test File Ingest Source {sid}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            run = start_ingestion_run(db_session, sid)
            metrics = IngestionMetrics(
                records_received=100, records_valid=100, records_inserted=100
            )
            # No http_status_code — file-based ingestion (e.g. CSV, shapefile)
            complete_ingestion_run(db_session, run, "SUCCESS", metrics)
            db_session.commit()

            reloaded = db_session.get(DataIngestionRun, run.id)
            assert reloaded is not None
            assert reloaded.http_status_code is None
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_http_status_code_check_constraint_rejects_out_of_range(self, db_session):
        """The CHECK constraint must reject http_status_code outside [100, 599]."""
        sid = uuid.uuid4()
        source = DataSource(
            id=sid,
            name=f"Test Bad HTTP Status Source {sid}",
            is_active=True,
        )
        try:
            db_session.add(source)
            db_session.commit()

            bad_run = DataIngestionRun(
                id=uuid.uuid4(),
                source_id=sid,
                started_at=datetime.now(timezone.utc),
                status="RUNNING",
                http_status_code=99,  # Invalid — below 100
            )
            db_session.add(bad_run)
            with pytest.raises((IntegrityError, Exception)):
                db_session.commit()
            db_session.rollback()
        finally:
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()


class TestSourceHealthExposesHttpStatus:
    """Tests that SourceHealthService correctly exposes last_http_status_code."""

    def test_last_http_status_code_exposed_from_latest_run(self, db_session):
        """SourceHealthService must return the http_status_code from the most recent run that recorded one."""
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source = DataSource(
            id=sid,
            name=f"Open-Meteo HTTP Status Test {sid}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        # Older run with HTTP 503
        old_run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=sid,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(seconds=5),
            status="FAILED",
            http_status_code=503,
            error_message="Service unavailable",
        )
        # Newer run with HTTP 200
        new_run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=sid,
            started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=9),
            status="SUCCESS",
            records_received=10,
            records_inserted=10,
            http_status_code=200,
        )
        try:
            db_session.add(source)
            db_session.add(old_run)
            db_session.add(new_run)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, sid)
            assert health is not None
            # Must return the HTTP status from the most recent run (200, not the old 503)
            assert health.last_http_status_code == 200
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_last_http_status_code_is_none_when_no_runs_recorded_one(self, db_session):
        """SourceHealthService returns None for last_http_status_code when no runs recorded an HTTP code."""
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source = DataSource(
            id=sid,
            name=f"File Ingest Source Health {sid}",
            is_active=True,
        )
        run = DataIngestionRun(
            id=uuid.uuid4(),
            source_id=sid,
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=4),
            status="SUCCESS",
            records_received=50,
            records_inserted=50,
            # http_status_code deliberately absent (NULL)
        )
        try:
            db_session.add(source)
            db_session.add(run)
            db_session.commit()

            service = SourceHealthService()
            health = service.get_source_health(db_session, sid)
            assert health is not None
            assert health.last_http_status_code is None
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()

    def test_existing_health_algorithm_unchanged_without_http_code(self, db_session):
        """Existing HEALTHY/DEGRADED/DOWN algorithm is unaffected when http_status_code is absent."""
        sid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source = DataSource(
            id=sid,
            name=f"Open-Meteo No HTTP Code {sid}",
            organization="Open-Meteo GmbH",
            data_type="METEOROLOGICAL",
            update_frequency="HOURLY",
            is_active=True,
        )
        # 3 consecutive FAILED runs with no http_status_code
        runs = [
            DataIngestionRun(
                id=uuid.uuid4(),
                source_id=sid,
                started_at=now - timedelta(hours=3 - i),
                completed_at=now - timedelta(hours=3 - i) + timedelta(seconds=5),
                status="FAILED",
                error_message=f"Failure {i}",
                # http_status_code deliberately absent
            )
            for i in range(3)
        ]
        try:
            db_session.add(source)
            for r in runs:
                db_session.add(r)
            db_session.commit()

            from app.core.config import Settings
            service = SourceHealthService(
                settings=Settings(source_health_consecutive_failure_threshold=3)
            )
            health = service.get_source_health(db_session, sid)
            assert health is not None
            # Algorithm still produces DOWN after 3 consecutive failures
            assert health.health_status == HealthStatus.DOWN
            assert health.consecutive_failures == 3
            # And http_status_code is simply None
            assert health.last_http_status_code is None
        finally:
            db_session.execute(
                text(f"DELETE FROM data_ingestion_runs WHERE source_id = '{sid}'")
            )
            db_session.execute(text(f"DELETE FROM data_sources WHERE id = '{sid}'"))
            db_session.commit()
