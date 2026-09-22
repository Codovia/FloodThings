"""
Data models and configuration for historical meteorological daily processing and aggregation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DailyQualityStatus(str, Enum):
    """Quality status of a daily aggregated record."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class DailyProcessingStatus(str, Enum):
    """Lifecycle statuses for daily chunk processing."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class DailyRecord:
    """
    Canonical daily meteorological observation for a single 0.25° ERA5 grid cell and UTC date.

    Contract:
    - UTC calendar day (YYYY-MM-DD).
    - Precipitation is total sum of valid hourly intervals (mm).
    - Temperature, RH, pressure are arithmetic means (plus min/max for temperature).
    - Completeness explicitly tracked via hour_count and quality_status.
    - Full provenance back to raw ERA5 extraction chunk and payload SHA-256.
    """

    date: str
    latitude: float
    longitude: float
    precipitation_total_mm: float
    temperature_mean_c: float
    temperature_min_c: float
    temperature_max_c: float
    relative_humidity_mean_pct: float
    surface_pressure_mean_hpa: float
    hour_count: int
    quality_status: str
    cell_id: str = ""
    chunk_id: str = ""
    source: str = "Open-Meteo Historical Weather API"
    dataset_model: str = "ERA5"
    raw_chunk_id: str = ""
    raw_payload_sha256: str = ""
    processing_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.cell_id:
            lat_str = f"{int(round(self.latitude * 100)):04d}"
            lon_str = f"{int(round(self.longitude * 100)):05d}"
            object.__setattr__(self, "cell_id", f"ERA5_{lat_str}_{lon_str}")
        if not self.chunk_id and self.raw_chunk_id:
            object.__setattr__(self, "chunk_id", self.raw_chunk_id)
        elif not self.raw_chunk_id and self.chunk_id:
            object.__setattr__(self, "raw_chunk_id", self.chunk_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert daily record to dictionary."""
        return asdict(self)


@dataclass
class DailyValidationResult:
    """Result of validating an aggregated daily dataset for a chunk."""

    is_valid: bool
    status: DailyProcessingStatus
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records_validated: int = 0
    cells_validated: int = 0
    complete_days: int = 0
    incomplete_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "status": self.status.value,
            "errors": self.errors,
            "warnings": self.warnings,
            "records_validated": self.records_validated,
            "cells_validated": self.cells_validated,
            "complete_days": self.complete_days,
            "incomplete_days": self.incomplete_days,
        }


@dataclass
class DailyProcessingConfig:
    """Configuration parameters for historical daily meteorological aggregation."""

    raw_base_dir: Path = Path("data/raw/era5_historical")
    processed_base_dir: Path = Path("data/processed/era5_daily")
    manifest_path: Path = Path("data/processed/era5_daily/processing_manifest.json")
    processing_version: str = "1.0"
    compression: str = "snappy"
    expected_hours_per_day: int = 24
    dry_run: bool = False
