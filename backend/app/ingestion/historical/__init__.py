"""
Historical meteorological extraction engine (Open-Meteo ERA5 Reanalysis).
"""

from app.ingestion.historical.client import HistoricalOpenMeteoClient
from app.ingestion.historical.extractor import HistoricalExtractor
from app.ingestion.historical.grid import (
    ERA5_EXCLUDED_CELL_IDS,
    ERA5_EXCLUSION_REASON,
    compute_spatial_fingerprint,
    generate_chunks,
    get_era5_eligible_grid,
    get_era5_excluded_cells,
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
    "get_era5_eligible_grid",
    "get_era5_excluded_cells",
    "ERA5_EXCLUDED_CELL_IDS",
    "ERA5_EXCLUSION_REASON",
    "compute_spatial_fingerprint",
    "get_spatial_batches",
    "generate_chunks",
    "verify_grid_against_postgis",
]
