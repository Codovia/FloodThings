"""
Unit and concurrency tests for FloodPulse background scheduler.

Verifies:
- Scheduler startup when enabled.
- Scheduler suppression when disabled by configuration.
- Graceful scheduler shutdown.
- Job registration with single-instance constraints (max_instances=1, coalesce=True).
- Concurrency protection: overlapping adapter executions are safely skipped.
- Lock release after failure: runner does not remain permanently locked if an error occurs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.models.system import DataIngestionRun, DataSource
from app.db.session import _get_session_factory
from app.ingestion.base import BaseAdapter, IngestionMetrics, IngestionResult
from app.ingestion.sources.open_meteo import OpenMeteoAdapter
from app.scheduler.jobs import run_open_meteo_operational_job
from app.scheduler.manager import SchedulerManager
from app.scheduler.runner import IngestionJobRunner


class MockAdapter(BaseAdapter):
    """Mock adapter for scheduler runner testing."""

    source_name = "Mock Adapter"

    def ingest(self, **kwargs) -> IngestionResult:
        return IngestionResult(
            source_name=self.source_name,
            run_id=uuid.uuid4(),
            status="SUCCESS",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics=IngestionMetrics(records_received=10, records_valid=10, records_inserted=5),
        )


class FailingMockAdapter(BaseAdapter):
    """Mock adapter that raises an unhandled exception."""

    source_name = "Failing Mock Adapter"

    def ingest(self, **kwargs) -> IngestionResult:
        raise RuntimeError("Simulated upstream network timeout")


class SlowMockAdapter(BaseAdapter):
    """Mock adapter simulating long-running network/database operation."""

    source_name = "Slow Mock Adapter"

    def ingest(self, delay: float = 0.2, **kwargs) -> IngestionResult:
        import time
        time.sleep(delay)
        return IngestionResult(
            source_name=self.source_name,
            run_id=uuid.uuid4(),
            status="SUCCESS",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics=IngestionMetrics(),
        )


class TestSchedulerLifecycle:
    """Tests covering SchedulerManager lifecycle methods."""

    def test_scheduler_disabled_by_config(self):
        """When scheduler_enabled is False, start() must not start the AsyncIOScheduler."""
        settings = Settings(scheduler_enabled=False)
        manager = SchedulerManager(settings=settings)

        assert not manager.is_running
        manager.start()
        assert not manager.is_running

    def test_scheduler_starts_and_stops_cleanly(self):
        """When scheduler_enabled is True, start() launches scheduler and shutdown() stops it."""
        settings = Settings(scheduler_enabled=True, openmeteo_ingestion_interval_minutes=30)
        manager = SchedulerManager(settings=settings)

        try:
            assert not manager.is_running
            manager.start()
            assert manager.is_running

            # Verify registered job
            jobs = manager._scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            assert "openmeteo_operational_ingestion" in job_ids

            job = manager._scheduler.get_job("openmeteo_operational_ingestion")
            assert job.max_instances == 1
            assert job.coalesce is True
        finally:
            manager.shutdown(wait=False)
            assert not manager.is_running

    def test_repeated_start_is_idempotent(self):
        """Calling start() multiple times does not raise or duplicate jobs."""
        settings = Settings(scheduler_enabled=True)
        manager = SchedulerManager(settings=settings)

        try:
            manager.start()
            assert manager.is_running
            # Second start call
            manager.start()
            assert manager.is_running
            jobs = manager._scheduler.get_jobs()
            assert len([j for j in jobs if j.id == "openmeteo_operational_ingestion"]) == 1
        finally:
            manager.shutdown(wait=False)


@pytest.mark.anyio
class TestSchedulerConcurrencyAndRunner:
    """Async tests verifying IngestionJobRunner concurrency and thread-safety."""

    async def test_successful_runner_execution(self):
        """Runner executes adapter in worker thread and returns IngestionResult."""
        runner = IngestionJobRunner()
        res = await runner.run_adapter(
            source_key="test_mock",
            adapter_cls=MockAdapter,
        )

        assert res is not None
        assert res.status == "SUCCESS"
        assert res.metrics.records_received == 10
        assert not runner.is_locked("test_mock")

    async def test_overlapping_execution_is_prevented(self):
        """When a job for a source is currently running, a second trigger must be skipped (return None)."""
        runner = IngestionJobRunner()

        # Launch slow job
        task1 = asyncio.create_task(
            runner.run_adapter("test_concurrency", SlowMockAdapter, delay=0.15)
        )

        # Allow task1 to start and acquire lock
        await asyncio.sleep(0.02)
        assert runner.is_locked("test_concurrency")

        # Second overlapping call must be skipped immediately
        res2 = await runner.run_adapter("test_concurrency", MockAdapter)
        assert res2 is None  # Skipped due to active lock!

        # Await completion of task1
        res1 = await task1
        assert res1 is not None
        assert res1.status == "SUCCESS"
        assert not runner.is_locked("test_concurrency")

    async def test_lock_released_after_failure(self):
        """If an adapter raises an unhandled exception, the lock must still be released."""
        runner = IngestionJobRunner()

        res = await runner.run_adapter("test_failing", FailingMockAdapter)
        assert res is None  # Handled safely without crashing
        assert not runner.is_locked("test_failing")  # Lock is NOT held

        # Subsequent execution must succeed
        res2 = await runner.run_adapter("test_failing", MockAdapter)
        assert res2 is not None
        assert res2.status == "SUCCESS"

    async def test_job_dispatch_invokes_runner(self):
        """The scheduled open_meteo job function correctly delegates to the runner."""
        with patch("app.scheduler.jobs.runner.run_adapter", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(status="SUCCESS")
            res = await run_open_meteo_operational_job()
            assert res is not None
            assert res.status == "SUCCESS"
            mock_run.assert_awaited_once()
            args, kwargs = mock_run.call_args
            assert kwargs.get("source_key") == "open_meteo"
            assert kwargs.get("mode") == "operational"

    async def test_scheduled_execution_creates_single_ingestion_run(self):
        """REQUIRED FIX 5 & 6: Verify scheduled execution delegates directly to adapter and creates exactly 1 DataIngestionRun."""
        factory = _get_session_factory()
        runner = IngestionJobRunner()

        with factory() as session:
            source = session.query(DataSource).filter(DataSource.name == "Open-Meteo Weather API").first()
            assert source is not None
            source_id = source.id
            runs_before = session.query(DataIngestionRun).filter(DataIngestionRun.source_id == source_id).count()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latitude": 12.98,
            "longitude": 77.60,
            "timezone": "UTC",
            "hourly": {
                "time": ["2026-09-18T00:00"],
                "temperature_2m": [25.0],
                "relative_humidity_2m": [70.0],
                "surface_pressure": [1013.2],
                "wind_speed_10m": [3.5],
                "precipitation": [0.0],
            },
        }
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        test_locations = [{"name": "Single Run Test Point", "lat": 12.9800, "lon": 77.6000}]
        res = await runner.run_adapter(
            source_key="open_meteo",
            adapter_cls=OpenMeteoAdapter,
            mode="operational",
            locations=test_locations,
            client=mock_client,
        )
        assert res is not None
        assert res.status == "SUCCESS"
        run_id = res.run_id

        try:
            with factory() as session:
                runs_after = session.query(DataIngestionRun).filter(DataIngestionRun.source_id == source_id).count()
                # Must create exactly ONE run, not two!
                assert runs_after == runs_before + 1
                created_run = session.get(DataIngestionRun, run_id)
                assert created_run is not None
                assert created_run.status == "SUCCESS"
        finally:
            with factory() as session:
                session.execute(text("DELETE FROM weather_observations WHERE source_record_id LIKE '%12.9800_77.6000%'"))
                session.execute(text("DELETE FROM rainfall_observations WHERE source_record_id LIKE '%12.9800_77.6000%'"))
                session.execute(text(f"DELETE FROM data_ingestion_runs WHERE id = '{run_id}'"))
                session.commit()
