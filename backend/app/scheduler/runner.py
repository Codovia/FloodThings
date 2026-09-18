"""
Safe execution runner for scheduled ingestion adapters.

Guarantees:
1. Concurrency protection via in-process async locks (prevents overlapping runs).
2. Offloads blocking synchronous database & HTTP operations off the asyncio event loop
   using asyncio.to_thread.
3. Every scheduled run gets a fresh, isolated SQLAlchemy Session, closed in finally.
4. If a job is already running, suppresses execution and logs the skip cleanly without
   fabricating fake runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.db.session import _get_session_factory
from app.ingestion.base import BaseAdapter, IngestionResult

logger = logging.getLogger("floodpulse.scheduler.runner")


class IngestionJobRunner:
    """Manages thread-offloaded execution and concurrency locking for scheduled adapters."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, source_key: str) -> asyncio.Lock:
        """Retrieve or create an in-process asyncio Lock for a given source key."""
        if source_key not in self._locks:
            self._locks[source_key] = asyncio.Lock()
        return self._locks[source_key]

    def is_locked(self, source_key: str) -> bool:
        """Check whether a job for the given source is currently executing."""
        lock = self._get_lock(source_key)
        return lock.locked()

    async def run_adapter(
        self,
        source_key: str,
        adapter_cls: type[BaseAdapter],
        **ingest_kwargs: Any,
    ) -> IngestionResult | None:
        """Execute an ingestion adapter safely in a background worker thread.

        Args:
            source_key: Unique identifier for the job / adapter (e.g. 'open_meteo').
            adapter_cls: BaseAdapter subclass to instantiate with a fresh Session.
            **ingest_kwargs: Keyword arguments passed to adapter.ingest().

        Returns:
            IngestionResult on completion, or None if skipped due to concurrency lock.
        """
        lock = self._get_lock(source_key)

        # Single-instance concurrency guard: skip if already executing
        if lock.locked():
            logger.warning(
                "[Scheduler] Ingestion for '%s' is already running; skipping overlapping trigger.",
                source_key,
            )
            return None

        async with lock:
            logger.info("[Scheduler] Starting scheduled ingestion for '%s'...", source_key)

            def _sync_worker() -> IngestionResult:
                session_factory = _get_session_factory()
                session: Session = session_factory()
                try:
                    adapter = adapter_cls(session)
                    return adapter.ingest(**ingest_kwargs)
                finally:
                    session.close()

            try:
                # Offload blocking synchronous work off the asyncio event loop
                result: IngestionResult = await asyncio.to_thread(_sync_worker)
                logger.info(
                    "[Scheduler] Completed ingestion for '%s' with status: %s (Run ID: %s)",
                    source_key,
                    result.status,
                    result.run_id,
                )
                return result
            except Exception as exc:
                logger.exception(
                    "[Scheduler] Unhandled exception during ingestion for '%s': %s",
                    source_key,
                    exc,
                )
                # Ensure the exception does not crash the scheduler loop
                return None


# Global singleton runner instance
runner = IngestionJobRunner()
