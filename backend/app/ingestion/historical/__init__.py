"""
Historical meteorological extraction engine (Open-Meteo ERA5 Reanalysis).
"""

from app.ingestion.historical.client import HistoricalOpenMeteoClient
from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import (
    generate_chunks,
    get_karnataka_grid,
    get_spatial_batches,
    verify_grid_against_postgis,
)
from app.ingestion.historical.manifest import HistoricalExtractionManifest
from app.ingestion.historical.models import (
    ChunkStatus,
    ExtractionChunk,
    ExtractionConfig,
    ExtractionMetadata,
    GridCell,
    ValidationResult,
)
from app.ingestion.historical.validator import HistoricalChunkValidator

__all__ = [
    "HistoricalOpenMeteoClient",
    "HistoricalExtractor",
    "HistoricalExtractionManifest",
    "HistoricalChunkValidator",
    "GridCell",
    "ExtractionChunk",
    "ChunkStatus",
    "ExtractionMetadata",
    "ValidationResult",
    "ExtractionConfig",
    "get_karnataka_grid",
    "get_spatial_batches",
    "generate_chunks",
    "verify_grid_against_postgis",
]
