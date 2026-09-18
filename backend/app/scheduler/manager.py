"""
SchedulerManager for FloodPulse.

Initializes, configures, starts, and gracefully shuts down the APScheduler
AsyncIOScheduler instance integrated with the FastAPI application lifespan.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings, get_settings
from app.scheduler.jobs import run_open_meteo_operational_job

logger = logging.getLogger("floodpulse.scheduler.manager")


class SchedulerManager:
    """Manages APScheduler AsyncIOScheduler lifecycle within FastAPI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()
        self._is_started: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler has been started and is active."""
        return self._is_started and self._scheduler.running

    def register_jobs(self) -> None:
        """Register configured background ingestion jobs with single-instance protection."""
        interval_minutes = self.settings.openmeteo_ingestion_interval_minutes

        self._scheduler.add_job(
            run_open_meteo_operational_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="openmeteo_operational_ingestion",
            name="Open-Meteo Operational Weather & Forecast Ingestion",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        logger.info(
            "[Scheduler] Registered job 'openmeteo_operational_ingestion' (Interval: %d minutes, max_instances=1, coalesce=True)",
            interval_minutes,
        )

    def start(self) -> None:
        """Start the background scheduler if enabled in configuration."""
        if not self.settings.scheduler_enabled:
            logger.info(
                "[Scheduler] Scheduler is disabled by configuration (scheduler_enabled=False); skipping startup."
            )
            return

        if self._is_started and self._scheduler.running:
            logger.warning("[Scheduler] Scheduler is already running.")
            return

        self.register_jobs()
        self._scheduler.start()
        self._is_started = True
        logger.info("[Scheduler] AsyncIOScheduler successfully started.")

    def shutdown(self, wait: bool = False) -> None:
        """Gracefully shut down the background scheduler."""
        if self._is_started and self._scheduler.running:
            logger.info("[Scheduler] Shutting down AsyncIOScheduler (wait=%s)...", wait)
            self._scheduler.shutdown(wait=wait)
            self._is_started = False
            logger.info("[Scheduler] AsyncIOScheduler shutdown complete.")


# Global singleton instance
_scheduler_manager: SchedulerManager | None = None


def get_scheduler_manager() -> SchedulerManager:
    """Get or create the global SchedulerManager singleton."""
    global _scheduler_manager  # noqa: PLW0603
    if _scheduler_manager is None:
        _scheduler_manager = SchedulerManager()
    return _scheduler_manager
