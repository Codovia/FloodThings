"""
Data models and configuration for historical meteorological extraction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChunkStatus(str, Enum):
    """Extraction chunk lifecycle statuses."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE = "RETRYABLE"
    PERMANENTLY_FAILED = "PERMANENTLY_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class GridCell:
    """Represents a single 0.25° ERA5 grid cell."""

    lat: float
    lon: float
    center_inside: bool = True
    name: str | None = None

    @property
    def cell_id(self) -> str:
        """Deterministic cell identifier e.g. ERA5_1425_07650."""
        lat_str = f"{int(round(self.lat * 100)):04d}"
        lon_str = f"{int(round(self.lon * 100)):05d}"
        return f"ERA5_{lat_str}_{lon_str}"


@dataclass(frozen=True)
class ExtractionChunk:
    """A deterministic extraction unit: 1 spatial batch of grid cells for 1 calendar year."""

    chunk_id: str
    year: int
    batch_id: int
    cells: list[GridCell]

    @property
    def coordinates(self) -> list[tuple[float, float]]:
        """List of (latitude, longitude) tuples in the chunk."""
        return [(c.lat, c.lon) for c in self.cells]

    @property
    def cell_ids(self) -> list[str]:
        """List of cell IDs in the chunk."""
        return [c.cell_id for c in self.cells]


@dataclass
class ExtractionMetadata:
    """Provenance and execution metadata attached to every raw extraction payload."""

    chunk_id: str
    year: int
    batch_id: int
    requested_url: str
    requested_model: str
    requested_coordinates: list[list[float]]
    requested_start_date: str
    requested_end_date: str
    requested_timezone: str
    retrieved_at_utc: str
    http_status: int
    response_latency_seconds: float
    uncompressed_bytes: int
    compressed_bytes: int
    payload_sha256: str
    compressed_sha256: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)


@dataclass
class ValidationResult:
    """Result of validating an extracted chunk payload."""

    is_valid: bool
    status: ChunkStatus
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    locations_validated: int = 0
    records_validated: int = 0
    null_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "status": self.status.value,
            "errors": self.errors,
            "warnings": self.warnings,
            "locations_validated": self.locations_validated,
            "records_validated": self.records_validated,
            "null_counts": self.null_counts,
        }


@dataclass
class ExtractionConfig:
    """Configuration parameters for the historical meteorological extraction engine."""

    raw_base_dir: Path = Path("data/raw/era5_historical")
    manifest_path: Path = Path("data/raw/era5_historical/extraction_manifest.json")
    model: str = "era5"
    timezone: str = "UTC"
    precipitation_unit: str = "mm"
    temperature_unit: str = "celsius"
    hourly_variables: list[str] = field(
        default_factory=lambda: [
            "precipitation",
            "temperature_2m",
            "relative_humidity_2m",
            "surface_pressure",
        ]
    )
    batch_size: int = 10
    connection_timeout: float = 15.0
    read_timeout: float = 30.0
    max_retries: int = 4
    backoff_factor: float = 2.0
    pacing_delay_seconds: float = 0.5
    dry_run: bool = False
