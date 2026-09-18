"""
Job definitions for FloodPulse background scheduler.

Only Group A (Open-Meteo operational weather and forecast ingestion) is scheduled
for automated recurring execution.
"""

from __future__ import annotations

import logging

from app.ingestion.base import IngestionResult
from app.ingestion.sources.open_meteo import OpenMeteoAdapter
from app.scheduler.runner import runner

logger = logging.getLogger("floodpulse.scheduler.jobs")


async def run_open_meteo_operational_job() -> IngestionResult | None:
    """Scheduled job: execute operational Open-Meteo weather and forecast ingestion.

    Runs OpenMeteoAdapter in operational mode for the 5 configured district representative
    query points (Bengaluru, Belagavi, Mangaluru, Kalaburagi, Mandya).
    Does NOT expand to all 31 districts.
    """
    logger.info("[SchedulerJob] Triggering Open-Meteo operational ingestion...")
    result = await runner.run_adapter(
        source_key="open_meteo",
        adapter_cls=OpenMeteoAdapter,
        mode="operational",
    )
    return result
