"""
Base classes and interfaces for FloodPulse data ingestion adapters.

Every adapter:
1. Fetches raw data from verified external source and preserves raw files in data/raw/.
2. Validates incoming payload against schema, coordinate, unit, and timestamp rules.
3. Normalizes fields into internal data contract units (metres, MCM, m³/s, mm, °C, m/s).
4. Persists records idempotently to PostgreSQL/PostGIS.
5. Records execution metrics in DataIngestionRun for complete provenance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.orm import Session


@dataclass
class IngestionMetrics:
    """Standardized metrics collected during an ingestion run."""

    records_received: int = 0
    records_valid: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_rejected: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestionResult:
    """Final result of an adapter ingestion execution."""

    source_name: str
    run_id: uuid.UUID
    status: str  # 'SUCCESS', 'PARTIAL', 'FAILED'
    started_at: datetime
    completed_at: datetime
    metrics: IngestionMetrics
    error_message: str | None = None


class BaseAdapter(ABC):
    """Abstract base class for all FloodPulse external source adapters."""

    source_name: str
    organization: str
    source_url: str
    access_method: str
    data_type: str
    update_frequency: str

    def __init__(self, session: Session):
        self.session = session

    @abstractmethod
    def ingest(self, **kwargs: Any) -> IngestionResult:
        """Execute the ingestion pipeline."""
        raise NotImplementedError
