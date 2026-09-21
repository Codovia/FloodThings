"""
Authoritative Karnataka 0.25° ERA5 grid definition and chunk generator.
"""

from __future__ import annotations

from typing import Any
from app.ingestion.historical.models import ExtractionChunk, GridCell

# 324 Karnataka-intersecting 0.25° ERA5 grid cells (253 centers inside, 71 boundary/coastal)
KARNATAKA_ERA5_CELLS: tuple[GridCell, ...] = (
    GridCell(lat=11.5, lon=76.5, center_inside=False),
    GridCell(lat=11.5, lon=76.75, center_inside=False),
    GridCell(lat=11.75, lon=76.0, center_inside=False),
    GridCell(lat=11.75, lon=76.25, center_inside=False),
    GridCell(lat=11.75, lon=76.5, center_inside=True),
    GridCell(lat=11.75, lon=76.75, center_inside=True),
    GridCell(lat=11.75, lon=77.0, center_inside=False),
    GridCell(lat=11.75, lon=77.25, center_inside=False),
    GridCell(lat=11.75, lon=77.5, center_inside=False),
    GridCell(lat=12.0, lon=75.75, center_inside=False),
    GridCell(lat=12.0, lon=76.0, center_inside=True),
    GridCell(lat=12.0, lon=76.25, center_inside=True),
    GridCell(lat=12.0, lon=76.5, center_inside=True),
    GridCell(lat=12.0, lon=76.75, center_inside=True),
    GridCell(lat=12.0, lon=77.0, center_inside=True),
    GridCell(lat=12.0, lon=77.25, center_inside=True),
    GridCell(lat=12.0, lon=77.5, center_inside=True),
    GridCell(lat=12.0, lon=77.75, center_inside=False),
    GridCell(lat=12.25, lon=75.5, center_inside=False),
    GridCell(lat=12.25, lon=75.75, center_inside=True),
    GridCell(lat=12.25, lon=76.0, center_inside=True),
    GridCell(lat=12.25, lon=76.25, center_inside=True),
    GridCell(lat=12.25, lon=76.5, center_inside=True),
    GridCell(lat=12.25, lon=76.75, center_inside=True),
    GridCell(lat=12.25, lon=77.0, center_inside=True),
    GridCell(lat=12.25, lon=77.25, center_inside=True),
    GridCell(lat=12.25, lon=77.5, center_inside=False),
    GridCell(lat=12.25, lon=77.75, center_inside=False),
    GridCell(lat=12.5, lon=75.25, center_inside=False),
    GridCell(lat=12.5, lon=75.5, center_inside=True),
    GridCell(lat=12.5, lon=75.75, center_inside=True),
    GridCell(lat=12.5, lon=76.0, center_inside=True),
    GridCell(lat=12.5, lon=76.25, center_inside=True),
    GridCell(lat=12.5, lon=76.5, center_inside=True),
    GridCell(lat=12.5, lon=76.75, center_inside=True),
    GridCell(lat=12.5, lon=77.0, center_inside=True),
    GridCell(lat=12.5, lon=77.25, center_inside=True),
    GridCell(lat=12.5, lon=77.5, center_inside=True),
    GridCell(lat=12.5, lon=77.75, center_inside=False),
    GridCell(lat=12.75, lon=74.75, center_inside=False),
    GridCell(lat=12.75, lon=75.0, center_inside=True),
    GridCell(lat=12.75, lon=75.25, center_inside=True),
    GridCell(lat=12.75, lon=75.5, center_inside=True),
    GridCell(lat=12.75, lon=75.75, center_inside=True),
    GridCell(lat=12.75, lon=76.0, center_inside=True),
    GridCell(lat=12.75, lon=76.25, center_inside=True),
    GridCell(lat=12.75, lon=76.5, center_inside=True),
    GridCell(lat=12.75, lon=76.75, center_inside=True),
    GridCell(lat=12.75, lon=77.0, center_inside=True),
    GridCell(lat=12.75, lon=77.25, center_inside=True),
    GridCell(lat=12.75, lon=77.5, center_inside=True),
    GridCell(lat=12.75, lon=77.75, center_inside=True),
    GridCell(lat=12.75, lon=78.0, center_inside=False),
    GridCell(lat=12.75, lon=78.25, center_inside=False),
    GridCell(lat=12.75, lon=78.5, center_inside=False),
    GridCell(lat=13.0, lon=74.75, center_inside=False),
    GridCell(lat=13.0, lon=75.0, center_inside=True),
    GridCell(lat=13.0, lon=75.25, center_inside=True),
    GridCell(lat=13.0, lon=75.5, center_inside=True),
    GridCell(lat=13.0, lon=75.75, center_inside=True),
    GridCell(lat=13.0, lon=76.0, center_inside=True),
    GridCell(lat=13.0, lon=76.25, center_inside=True),
    GridCell(lat=13.0, lon=76.5, center_inside=True),
    GridCell(lat=13.0, lon=76.75, center_inside=True),
    GridCell(lat=13.0, lon=77.0, center_inside=True),
    GridCell(lat=13.0, lon=77.25, center_inside=True),
    GridCell(lat=13.0, lon=77.5, center_inside=True),
    GridCell(lat=13.0, lon=77.75, center_inside=True),
    GridCell(lat=13.0, lon=78.0, center_inside=True),
    GridCell(lat=13.0, lon=78.25, center_inside=True),
    GridCell(lat=13.0, lon=78.5, center_inside=False),
    GridCell(lat=13.25, lon=74.75, center_inside=True),
    GridCell(lat=13.25, lon=75.0, center_inside=True),
    GridCell(lat=13.25, lon=75.25, center_inside=True),
    GridCell(lat=13.25, lon=75.5, center_inside=True),
    GridCell(lat=13.25, lon=75.75, center_inside=True),
    GridCell(lat=13.25, lon=76.0, center_inside=True),
    GridCell(lat=13.25, lon=76.25, center_inside=True),
    GridCell(lat=13.25, lon=76.5, center_inside=True),
    GridCell(lat=13.25, lon=76.75, center_inside=True),
    GridCell(lat=13.25, lon=77.0, center_inside=True),
    GridCell(lat=13.25, lon=77.25, center_inside=True),
    GridCell(lat=13.25, lon=77.5, center_inside=True),
    GridCell(lat=13.25, lon=77.75, center_inside=True),
    GridCell(lat=13.25, lon=78.0, center_inside=True),
    GridCell(lat=13.25, lon=78.25, center_inside=True),
    GridCell(lat=13.25, lon=78.5, center_inside=True),
    GridCell(lat=13.5, lon=74.75, center_inside=True),
    GridCell(lat=13.5, lon=75.0, center_inside=True),
    GridCell(lat=13.5, lon=75.25, center_inside=True),
    GridCell(lat=13.5, lon=75.5, center_inside=True),
    GridCell(lat=13.5, lon=75.75, center_inside=True),
    GridCell(lat=13.5, lon=76.0, center_inside=True),
    GridCell(lat=13.5, lon=76.25, center_inside=True),
    GridCell(lat=13.5, lon=76.5, center_inside=True),
    GridCell(lat=13.5, lon=76.75, center_inside=True),
    GridCell(lat=13.5, lon=77.0, center_inside=True),
    GridCell(lat=13.5, lon=77.25, center_inside=True),
    GridCell(lat=13.5, lon=77.5, center_inside=True),
    GridCell(lat=13.5, lon=77.75, center_inside=True),
    GridCell(lat=13.5, lon=78.0, center_inside=True),
    GridCell(lat=13.5, lon=78.25, center_inside=True),
    GridCell(lat=13.5, lon=78.5, center_inside=False),
    GridCell(lat=13.75, lon=74.5, center_inside=False),
    GridCell(lat=13.75, lon=74.75, center_inside=True),
    GridCell(lat=13.75, lon=75.0, center_inside=True),
    GridCell(lat=13.75, lon=75.25, center_inside=True),
    GridCell(lat=13.75, lon=75.5, center_inside=True),
    GridCell(lat=13.75, lon=75.75, center_inside=True),
    GridCell(lat=13.75, lon=76.0, center_inside=True),
    GridCell(lat=13.75, lon=76.25, center_inside=True),
    GridCell(lat=13.75, lon=76.5, center_inside=True),
    GridCell(lat=13.75, lon=76.75, center_inside=True),
    GridCell(lat=13.75, lon=77.0, center_inside=False),
    GridCell(lat=13.75, lon=77.25, center_inside=True),
    GridCell(lat=13.75, lon=77.5, center_inside=False),
    GridCell(lat=13.75, lon=77.75, center_inside=True),
    GridCell(lat=13.75, lon=78.0, center_inside=True),
    GridCell(lat=13.75, lon=78.25, center_inside=False),
    GridCell(lat=14.0, lon=74.5, center_inside=False),
    GridCell(lat=14.0, lon=74.75, center_inside=True),
    GridCell(lat=14.0, lon=75.0, center_inside=True),
    GridCell(lat=14.0, lon=75.25, center_inside=True),
    GridCell(lat=14.0, lon=75.5, center_inside=True),
    GridCell(lat=14.0, lon=75.75, center_inside=True),
    GridCell(lat=14.0, lon=76.0, center_inside=True),
    GridCell(lat=14.0, lon=76.25, center_inside=True),
    GridCell(lat=14.0, lon=76.5, center_inside=True),
    GridCell(lat=14.0, lon=76.75, center_inside=True),
    GridCell(lat=14.0, lon=77.0, center_inside=False),
    GridCell(lat=14.0, lon=77.25, center_inside=False),
    GridCell(lat=14.0, lon=77.5, center_inside=False),
    GridCell(lat=14.0, lon=77.75, center_inside=False),
    GridCell(lat=14.0, lon=78.0, center_inside=False),
    GridCell(lat=14.25, lon=74.5, center_inside=True),
    GridCell(lat=14.25, lon=74.75, center_inside=True),
    GridCell(lat=14.25, lon=75.0, center_inside=True),
    GridCell(lat=14.25, lon=75.25, center_inside=True),
    GridCell(lat=14.25, lon=75.5, center_inside=True),
    GridCell(lat=14.25, lon=75.75, center_inside=True),
    GridCell(lat=14.25, lon=76.0, center_inside=True),
    GridCell(lat=14.25, lon=76.25, center_inside=True),
    GridCell(lat=14.25, lon=76.5, center_inside=True),
    GridCell(lat=14.25, lon=76.75, center_inside=True),
    GridCell(lat=14.25, lon=77.0, center_inside=False),
    GridCell(lat=14.25, lon=77.25, center_inside=True),
    GridCell(lat=14.25, lon=77.5, center_inside=True),
    GridCell(lat=14.5, lon=74.25, center_inside=False),
    GridCell(lat=14.5, lon=74.5, center_inside=True),
    GridCell(lat=14.5, lon=74.75, center_inside=True),
    GridCell(lat=14.5, lon=75.0, center_inside=True),
    GridCell(lat=14.5, lon=75.25, center_inside=True),
    GridCell(lat=14.5, lon=75.5, center_inside=True),
    GridCell(lat=14.5, lon=75.75, center_inside=True),
    GridCell(lat=14.5, lon=76.0, center_inside=True),
    GridCell(lat=14.5, lon=76.25, center_inside=True),
    GridCell(lat=14.5, lon=76.5, center_inside=True),
    GridCell(lat=14.5, lon=76.75, center_inside=True),
    GridCell(lat=14.5, lon=77.0, center_inside=False),
    GridCell(lat=14.75, lon=74.0, center_inside=False),
    GridCell(lat=14.75, lon=74.25, center_inside=True),
    GridCell(lat=14.75, lon=74.5, center_inside=True),
    GridCell(lat=14.75, lon=74.75, center_inside=True),
    GridCell(lat=14.75, lon=75.0, center_inside=True),
    GridCell(lat=14.75, lon=75.25, center_inside=True),
    GridCell(lat=14.75, lon=75.5, center_inside=True),
    GridCell(lat=14.75, lon=75.75, center_inside=True),
    GridCell(lat=14.75, lon=76.0, center_inside=True),
    GridCell(lat=14.75, lon=76.25, center_inside=True),
    GridCell(lat=14.75, lon=76.5, center_inside=True),
    GridCell(lat=14.75, lon=76.75, center_inside=True),
    GridCell(lat=15.0, lon=74.0, center_inside=False),
    GridCell(lat=15.0, lon=74.25, center_inside=False),
    GridCell(lat=15.0, lon=74.5, center_inside=True),
    GridCell(lat=15.0, lon=74.75, center_inside=True),
    GridCell(lat=15.0, lon=75.0, center_inside=True),
    GridCell(lat=15.0, lon=75.25, center_inside=True),
    GridCell(lat=15.0, lon=75.5, center_inside=True),
    GridCell(lat=15.0, lon=75.75, center_inside=True),
    GridCell(lat=15.0, lon=76.0, center_inside=True),
    GridCell(lat=15.0, lon=76.25, center_inside=True),
    GridCell(lat=15.0, lon=76.5, center_inside=True),
    GridCell(lat=15.0, lon=76.75, center_inside=True),
    GridCell(lat=15.0, lon=77.0, center_inside=False),
    GridCell(lat=15.0, lon=77.25, center_inside=False),
    GridCell(lat=15.25, lon=74.25, center_inside=False),
    GridCell(lat=15.25, lon=74.5, center_inside=True),
    GridCell(lat=15.25, lon=74.75, center_inside=True),
    GridCell(lat=15.25, lon=75.0, center_inside=True),
    GridCell(lat=15.25, lon=75.25, center_inside=True),
    GridCell(lat=15.25, lon=75.5, center_inside=True),
    GridCell(lat=15.25, lon=75.75, center_inside=True),
    GridCell(lat=15.25, lon=76.0, center_inside=True),
    GridCell(lat=15.25, lon=76.25, center_inside=True),
    GridCell(lat=15.25, lon=76.5, center_inside=True),
    GridCell(lat=15.25, lon=76.75, center_inside=True),
    GridCell(lat=15.25, lon=77.0, center_inside=True),
    GridCell(lat=15.25, lon=77.25, center_inside=False),
    GridCell(lat=15.5, lon=74.25, center_inside=False),
    GridCell(lat=15.5, lon=74.5, center_inside=True),
    GridCell(lat=15.5, lon=74.75, center_inside=True),
    GridCell(lat=15.5, lon=75.0, center_inside=True),
    GridCell(lat=15.5, lon=75.25, center_inside=True),
    GridCell(lat=15.5, lon=75.5, center_inside=True),
    GridCell(lat=15.5, lon=75.75, center_inside=True),
    GridCell(lat=15.5, lon=76.0, center_inside=True),
    GridCell(lat=15.5, lon=76.25, center_inside=True),
    GridCell(lat=15.5, lon=76.5, center_inside=True),
    GridCell(lat=15.5, lon=76.75, center_inside=True),
    GridCell(lat=15.5, lon=77.0, center_inside=False),
    GridCell(lat=15.75, lon=74.0, center_inside=False),
    GridCell(lat=15.75, lon=74.25, center_inside=False),
    GridCell(lat=15.75, lon=74.5, center_inside=True),
    GridCell(lat=15.75, lon=74.75, center_inside=True),
    GridCell(lat=15.75, lon=75.0, center_inside=True),
    GridCell(lat=15.75, lon=75.25, center_inside=True),
    GridCell(lat=15.75, lon=75.5, center_inside=True),
    GridCell(lat=15.75, lon=75.75, center_inside=True),
    GridCell(lat=15.75, lon=76.0, center_inside=True),
    GridCell(lat=15.75, lon=76.25, center_inside=True),
    GridCell(lat=15.75, lon=76.5, center_inside=True),
    GridCell(lat=15.75, lon=76.75, center_inside=True),
    GridCell(lat=15.75, lon=77.0, center_inside=True),
    GridCell(lat=15.75, lon=77.25, center_inside=False),
    GridCell(lat=16.0, lon=74.25, center_inside=False),
    GridCell(lat=16.0, lon=74.5, center_inside=True),
    GridCell(lat=16.0, lon=74.75, center_inside=True),
    GridCell(lat=16.0, lon=75.0, center_inside=True),
    GridCell(lat=16.0, lon=75.25, center_inside=True),
    GridCell(lat=16.0, lon=75.5, center_inside=True),
    GridCell(lat=16.0, lon=75.75, center_inside=True),
    GridCell(lat=16.0, lon=76.0, center_inside=True),
    GridCell(lat=16.0, lon=76.25, center_inside=True),
    GridCell(lat=16.0, lon=76.5, center_inside=True),
    GridCell(lat=16.0, lon=76.75, center_inside=True),
    GridCell(lat=16.0, lon=77.0, center_inside=True),
    GridCell(lat=16.0, lon=77.25, center_inside=True),
    GridCell(lat=16.0, lon=77.5, center_inside=True),
    GridCell(lat=16.25, lon=74.25, center_inside=False),
    GridCell(lat=16.25, lon=74.5, center_inside=True),
    GridCell(lat=16.25, lon=74.75, center_inside=True),
    GridCell(lat=16.25, lon=75.0, center_inside=True),
    GridCell(lat=16.25, lon=75.25, center_inside=True),
    GridCell(lat=16.25, lon=75.5, center_inside=True),
    GridCell(lat=16.25, lon=75.75, center_inside=True),
    GridCell(lat=16.25, lon=76.0, center_inside=True),
    GridCell(lat=16.25, lon=76.25, center_inside=True),
    GridCell(lat=16.25, lon=76.5, center_inside=True),
    GridCell(lat=16.25, lon=76.75, center_inside=True),
    GridCell(lat=16.25, lon=77.0, center_inside=True),
    GridCell(lat=16.25, lon=77.25, center_inside=True),
    GridCell(lat=16.25, lon=77.5, center_inside=False),
    GridCell(lat=16.5, lon=74.25, center_inside=False),
    GridCell(lat=16.5, lon=74.5, center_inside=True),
    GridCell(lat=16.5, lon=74.75, center_inside=True),
    GridCell(lat=16.5, lon=75.0, center_inside=True),
    GridCell(lat=16.5, lon=75.25, center_inside=True),
    GridCell(lat=16.5, lon=75.5, center_inside=True),
    GridCell(lat=16.5, lon=75.75, center_inside=True),
    GridCell(lat=16.5, lon=76.0, center_inside=True),
    GridCell(lat=16.5, lon=76.25, center_inside=True),
    GridCell(lat=16.5, lon=76.5, center_inside=True),
    GridCell(lat=16.5, lon=76.75, center_inside=True),
    GridCell(lat=16.5, lon=77.0, center_inside=True),
    GridCell(lat=16.5, lon=77.25, center_inside=True),
    GridCell(lat=16.5, lon=77.5, center_inside=False),
    GridCell(lat=16.75, lon=74.5, center_inside=False),
    GridCell(lat=16.75, lon=74.75, center_inside=False),
    GridCell(lat=16.75, lon=75.0, center_inside=True),
    GridCell(lat=16.75, lon=75.25, center_inside=True),
    GridCell(lat=16.75, lon=75.5, center_inside=True),
    GridCell(lat=16.75, lon=75.75, center_inside=True),
    GridCell(lat=16.75, lon=76.0, center_inside=True),
    GridCell(lat=16.75, lon=76.25, center_inside=True),
    GridCell(lat=16.75, lon=76.5, center_inside=True),
    GridCell(lat=16.75, lon=76.75, center_inside=True),
    GridCell(lat=16.75, lon=77.0, center_inside=True),
    GridCell(lat=16.75, lon=77.25, center_inside=True),
    GridCell(lat=16.75, lon=77.5, center_inside=False),
    GridCell(lat=17.0, lon=75.0, center_inside=False),
    GridCell(lat=17.0, lon=75.25, center_inside=False),
    GridCell(lat=17.0, lon=75.5, center_inside=False),
    GridCell(lat=17.0, lon=75.75, center_inside=True),
    GridCell(lat=17.0, lon=76.0, center_inside=True),
    GridCell(lat=17.0, lon=76.25, center_inside=True),
    GridCell(lat=17.0, lon=76.5, center_inside=True),
    GridCell(lat=17.0, lon=76.75, center_inside=True),
    GridCell(lat=17.0, lon=77.0, center_inside=True),
    GridCell(lat=17.0, lon=77.25, center_inside=True),
    GridCell(lat=17.0, lon=77.5, center_inside=False),
    GridCell(lat=17.25, lon=75.5, center_inside=False),
    GridCell(lat=17.25, lon=75.75, center_inside=True),
    GridCell(lat=17.25, lon=76.0, center_inside=True),
    GridCell(lat=17.25, lon=76.25, center_inside=True),
    GridCell(lat=17.25, lon=76.5, center_inside=True),
    GridCell(lat=17.25, lon=76.75, center_inside=True),
    GridCell(lat=17.25, lon=77.0, center_inside=True),
    GridCell(lat=17.25, lon=77.25, center_inside=True),
    GridCell(lat=17.25, lon=77.5, center_inside=False),
    GridCell(lat=17.5, lon=75.5, center_inside=False),
    GridCell(lat=17.5, lon=75.75, center_inside=False),
    GridCell(lat=17.5, lon=76.0, center_inside=False),
    GridCell(lat=17.5, lon=76.25, center_inside=False),
    GridCell(lat=17.5, lon=76.5, center_inside=True),
    GridCell(lat=17.5, lon=76.75, center_inside=True),
    GridCell(lat=17.5, lon=77.0, center_inside=True),
    GridCell(lat=17.5, lon=77.25, center_inside=True),
    GridCell(lat=17.5, lon=77.5, center_inside=True),
    GridCell(lat=17.5, lon=77.75, center_inside=False),
    GridCell(lat=17.75, lon=76.5, center_inside=False),
    GridCell(lat=17.75, lon=76.75, center_inside=True),
    GridCell(lat=17.75, lon=77.0, center_inside=True),
    GridCell(lat=17.75, lon=77.25, center_inside=True),
    GridCell(lat=17.75, lon=77.5, center_inside=True),
    GridCell(lat=18.0, lon=76.75, center_inside=False),
    GridCell(lat=18.0, lon=77.0, center_inside=True),
    GridCell(lat=18.0, lon=77.25, center_inside=True),
    GridCell(lat=18.0, lon=77.5, center_inside=True),
    GridCell(lat=18.0, lon=77.75, center_inside=False),
    GridCell(lat=18.25, lon=77.0, center_inside=False),
    GridCell(lat=18.25, lon=77.25, center_inside=True),
    GridCell(lat=18.25, lon=77.5, center_inside=True),
    GridCell(lat=18.5, lon=77.25, center_inside=False),
    GridCell(lat=18.5, lon=77.5, center_inside=False),
)


ERA5_EXCLUSION_REASON: str = (
    "Open-Meteo ERA5 archive snaps requested offshore coordinate to a"
    " neighboring land-side ERA5 coordinate, preventing one-to-one spatial"
    " identity."
)

ERA5_EXCLUDED_CELL_IDS: frozenset[str] = frozenset(
    {
        "ERA5_1275_07475",
        "ERA5_1375_07450",
        "ERA5_1400_07450",
        "ERA5_1450_07425",
        "ERA5_1475_07400",
        "ERA5_1500_07400",
    }
)


def get_karnataka_grid() -> list[GridCell]:
    """Return the authoritative 324 Karnataka-intersecting ERA5 0.25° grid cells."""
    return list(KARNATAKA_ERA5_CELLS)


def get_era5_eligible_grid() -> list[GridCell]:
    """
    Return the 318 ERA5 extraction-eligible Karnataka grid cells.

    Excludes the 6 offshore Arabian Sea boundary cells where Open-Meteo ERA5 snaps
    requested coordinates to neighboring land-side cells.
    """
    return [c for c in KARNATAKA_ERA5_CELLS if c.cell_id not in ERA5_EXCLUDED_CELL_IDS]


def get_era5_excluded_cells() -> list[GridCell]:
    """Return the 6 offshore boundary cells excluded from ERA5 extraction."""
    return [c for c in KARNATAKA_ERA5_CELLS if c.cell_id in ERA5_EXCLUDED_CELL_IDS]


def compute_spatial_fingerprint(cells: list[GridCell]) -> str:
    """Compute deterministic 8-character hex SHA-256 fingerprint for a list of grid cells."""
    import hashlib
    cell_str = ",".join(sorted(c.cell_id for c in cells))
    return hashlib.sha256(cell_str.encode("utf-8")).hexdigest()[:8]


def get_spatial_batches(batch_size: int = 10, eligible_only: bool = True) -> list[list[GridCell]]:
    """
    Partition authoritative Karnataka cells into deterministic batches of size batch_size.

    The authoritative 324 cells define 33 permanent spatial batches (32 batches of 10
    and 1 final batch of 4).

    If eligible_only is True (default for ERA5 extraction), each batch filters its
    constituent cells to exclude source-incompatible coordinates (ERA5_EXCLUDED_CELL_IDS),
    maintaining fixed spatial envelopes without shifting batch boundaries across the state.
    This yields:
      - 26 batches with 10 eligible cells
      - 6 batches with 9 eligible cells (batches 004, 011, 012, 015, 016, 018)
      - 1 batch with 4 eligible cells (batch 033)
      Total: 33 batches, 318 eligible cells.

    If eligible_only is False, returns all 324 authoritative cells across the 33 batches.
    """
    all_cells = get_karnataka_grid()
    batches = [all_cells[i : i + batch_size] for i in range(0, len(all_cells), batch_size)]
    if eligible_only:
        return [
            [c for c in b if c.cell_id not in ERA5_EXCLUDED_CELL_IDS]
            for b in batches
        ]
    return batches


def generate_chunks(
    start_year: int,
    end_year: int,
    batch_size: int = 10,
    eligible_only: bool = True,
) -> list[ExtractionChunk]:
    """
    Generate deterministic extraction chunks for a specified range of calendar years.

    Each chunk represents 1 spatial batch for 1 complete calendar year.
    For the full 1969–1994 span (26 years) and 33 batches, exactly 858 chunks are generated.
    """
    if start_year > end_year:
        raise ValueError(f"start_year ({start_year}) cannot exceed end_year ({end_year})")

    batches = get_spatial_batches(batch_size=batch_size, eligible_only=eligible_only)
    chunks: list[ExtractionChunk] = []

    for year in range(start_year, end_year + 1):
        for batch_idx, batch_cells in enumerate(batches, start=1):
            chunk_id = f"era5_{year}_batch_{batch_idx:03d}"
            chunks.append(
                ExtractionChunk(
                    chunk_id=chunk_id,
                    year=year,
                    batch_id=batch_idx,
                    cells=batch_cells,
                )
            )

    return chunks


def verify_grid_against_postgis(engine_or_conn: Any) -> tuple[bool, int, int]:
    """
    Read-only verification of KARNATAKA_ERA5_CELLS against PostGIS authoritative state boundary.
    Returns (matches, total_cells, centers_inside).
    """
    from sqlalchemy import text

    sql = """
    WITH grid AS (
        SELECT 
            round(lat::numeric, 2) as lat,
            round(lon::numeric, 2) as lon,
            ST_MakeEnvelope(lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125, 4326) as cell_geom,
            ST_SetSRID(ST_Point(lon, lat), 4326) as center_geom
        FROM generate_series(11.25, 18.75, 0.25) lat
        CROSS JOIN generate_series(73.75, 79.00, 0.25) lon
    )
    SELECT 
        g.lat, 
        g.lon,
        ST_Contains(s.geometry, g.center_geom) as center_inside
    FROM grid g
    CROSS JOIN states s
    WHERE s.name = 'Karnataka' AND ST_Intersects(s.geometry, g.cell_geom)
    ORDER BY g.lat, g.lon;
    """
    with (engine_or_conn.connect() if hasattr(engine_or_conn, "connect") else engine_or_conn) as conn:
        rows = conn.execute(text(sql)).fetchall()
        db_cells = [(float(r.lat), float(r.lon), bool(r.center_inside)) for r in rows]

    static_cells = [(c.lat, c.lon, c.center_inside) for c in KARNATAKA_ERA5_CELLS]
    matches = (db_cells == static_cells)
    centers_in = sum(1 for c in KARNATAKA_ERA5_CELLS if c.center_inside)
    return matches, len(KARNATAKA_ERA5_CELLS), centers_in
