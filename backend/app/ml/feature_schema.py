"""
Canonical feature schema and validation contracts for ML-ready historical features.

Step 2 of the ML Feature Engineering Pipeline.
Strictly adheres to:
- No future observations (zero temporal leakage).
- Preservation of cell_id, chunk_id, date, and raw payload SHA-256 provenance.
- Explicit NaN/None for missing or incomplete observation windows (zero silent zero-filling).
- Physical bounds and domain consistency validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date as dt_date, datetime
import math
from typing import Any

import pyarrow as pa


class FeatureContractError(ValueError):
    """Raised when a feature record violates schema, physical, or temporal contracts."""


@dataclass(frozen=True)
class MLFeatureRecord:
    """
    Canonical ML-ready historical observation record.

    Attributes
    ----------
    date : str
        UTC calendar date (YYYY-MM-DD).
    cell_id : str
        Authoritative 0.25° ERA5 cell identifier (e.g. ERA5_1425_07650).
    chunk_id : str
        Source extraction chunk identifier (e.g. era5_1969_batch_001).
    latitude : float
        Grid cell center latitude in WGS 84 decimal degrees.
    longitude : float
        Grid cell center longitude in WGS 84 decimal degrees.

    rainfall_1d : float | None
        1-day total precipitation in mm for the given calendar day (sum of 24h).
    rainfall_3d : float | None
        Rolling 3-day total precipitation in mm over [t-2, t].
    rainfall_7d : float | None
        Rolling 7-day total precipitation in mm over [t-6, t].
    rainfall_14d : float | None
        Rolling 14-day total precipitation in mm over [t-13, t].
    rainfall_30d : float | None
        Rolling 30-day total precipitation in mm over [t-29, t].

    temperature_mean_c : float | None
        Daily arithmetic mean 2m air temperature in °C.
    temperature_min_c : float | None
        Daily minimum 2m air temperature in °C.
    temperature_max_c : float | None
        Daily maximum 2m air temperature in °C.
    relative_humidity_mean_pct : float | None
        Daily arithmetic mean 2m relative humidity in %.
    surface_pressure_mean_hpa : float | None
        Daily arithmetic mean surface pressure in hPa.

    elevation : float | None
        Zonal mean elevation in meters (EGM2008) from Copernicus GLO-30 DEM.
    slope : float | None
        Zonal mean slope in degrees (Horn 1981 metric algorithm) from Copernicus GLO-30 DEM.

    basin_id : str | None
        CWC statutory major river basin UUID.
    basin_name : str | None
        CWC statutory major river basin name (e.g. Cauvery, Krishna).
    sub_basin_id : str | None
        HydroBASINS Level-7 hydrological catchment UUID.
    sub_basin_name : str | None
        HydroBASINS Level-7 catchment identifier (e.g. HYBAS_4071140230).
    hybas_id : int | None
        HydroBASINS Level-7 unique integer identifier.
    distance_to_river_m : float | None
        Geodesic distance in meters from cell centroid to nearest HydroRIVERS reach.
    nearest_river_id : str | None
        Identifier or name of nearest HydroRIVERS reach.
    district_id : str | None
        KSR-SAC administrative district UUID.
    district_name : str | None
        KSR-SAC administrative district name.

    hour_count : int
        Count of valid hourly observations contributing to day t (0–24).
    quality_status : str
        Quality status of day t: 'COMPLETE' (24h) or 'INCOMPLETE' (<24h).
    window_30d_valid_days : int
        Count of COMPLETE days available within the trailing 30-day window [t-29, t].
    is_complete : bool
        True iff all features (weather, 30d rolling rainfall, terrain, hydrology) are fully non-null.

    raw_chunk_id : str
        Raw extraction chunk identifier.
    raw_payload_sha256 : str
        SHA-256 hash of the uncompressed source JSON payload.
    feature_version : str
        Feature engineering pipeline version (e.g. '1.0').
    """

    # Identity
    date: str
    cell_id: str
    chunk_id: str
    latitude: float
    longitude: float

    # Precipitation (rolling backward-looking sums in mm)
    rainfall_1d: float | None
    rainfall_3d: float | None
    rainfall_7d: float | None
    rainfall_14d: float | None
    rainfall_30d: float | None

    # Weather (daily stats)
    temperature_mean_c: float | None
    temperature_min_c: float | None
    temperature_max_c: float | None
    relative_humidity_mean_pct: float | None
    surface_pressure_mean_hpa: float | None

    # Terrain
    elevation: float | None
    slope: float | None

    # Hydrology & Administrative
    basin_id: str | None = None
    basin_name: str | None = None
    sub_basin_id: str | None = None
    sub_basin_name: str | None = None
    hybas_id: int | None = None
    distance_to_river_m: float | None = None
    nearest_river_id: str | None = None
    district_id: str | None = None
    district_name: str | None = None

    # Quality & Provenance
    hour_count: int = 24
    quality_status: str = "COMPLETE"
    window_30d_valid_days: int = 30
    is_complete: bool = True
    raw_chunk_id: str = ""
    raw_payload_sha256: str = ""
    feature_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert feature record to dictionary."""
        return asdict(self)


# Explicit PyArrow schema for serializing ML features to Parquet
ARROW_FEATURE_SCHEMA = pa.schema(
    [
        ("date", pa.string()),
        ("cell_id", pa.string()),
        ("chunk_id", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("rainfall_1d", pa.float64()),
        ("rainfall_3d", pa.float64()),
        ("rainfall_7d", pa.float64()),
        ("rainfall_14d", pa.float64()),
        ("rainfall_30d", pa.float64()),
        ("temperature_mean_c", pa.float64()),
        ("temperature_min_c", pa.float64()),
        ("temperature_max_c", pa.float64()),
        ("relative_humidity_mean_pct", pa.float64()),
        ("surface_pressure_mean_hpa", pa.float64()),
        ("elevation", pa.float64()),
        ("slope", pa.float64()),
        ("basin_id", pa.string()),
        ("basin_name", pa.string()),
        ("sub_basin_id", pa.string()),
        ("sub_basin_name", pa.string()),
        ("hybas_id", pa.int64()),
        ("distance_to_river_m", pa.float64()),
        ("nearest_river_id", pa.string()),
        ("district_id", pa.string()),
        ("district_name", pa.string()),
        ("hour_count", pa.int32()),
        ("quality_status", pa.string()),
        ("window_30d_valid_days", pa.int32()),
        ("is_complete", pa.bool_()),
        ("raw_chunk_id", pa.string()),
        ("raw_payload_sha256", pa.string()),
        ("feature_version", pa.string()),
    ],
    metadata={
        b"source": b"Open-Meteo ERA5 / Copernicus DEM GLO-30 / HydroSHEDS / KSR-SAC",
        b"pipeline": b"FloodPulse ML Historical Feature Pipeline",
        b"temporal_leakage_prevented": b"true",
        b"zero_synthetic_data": b"true",
    },
)


class FeatureQualityValidator:
    """Validates physical domain, temporal order, and contract invariants on ML feature records."""

    @staticmethod
    def validate_record(record: MLFeatureRecord) -> list[str]:
        """Validate an individual ML feature record against physical and semantic invariants."""
        errors: list[str] = []

        # 1. Date format check (YYYY-MM-DD)
        try:
            d_parts = [int(p) for p in record.date.split("-")]
            if len(d_parts) != 3:
                errors.append(f"Invalid date format '{record.date}', expected YYYY-MM-DD")
            else:
                dt_date(d_parts[0], d_parts[1], d_parts[2])
        except Exception:
            errors.append(f"Unparseable date '{record.date}'")

        # 2. Cell ID identity check
        expected_cell_id = (
            f"ERA5_{int(round(record.latitude * 100)):04d}_{int(round(record.longitude * 100)):05d}"
        )
        if record.cell_id != expected_cell_id:
            errors.append(
                f"cell_id '{record.cell_id}' does not match coordinates "
                f"({record.latitude}, {record.longitude}); expected '{expected_cell_id}'"
            )

        # 3. Rainfall non-negativity
        for w_name, val in [
            ("rainfall_1d", record.rainfall_1d),
            ("rainfall_3d", record.rainfall_3d),
            ("rainfall_7d", record.rainfall_7d),
            ("rainfall_14d", record.rainfall_14d),
            ("rainfall_30d", record.rainfall_30d),
        ]:
            if val is not None:
                if math.isnan(val) or math.isinf(val):
                    errors.append(f"{w_name} is non-finite: {val}")
                elif val < 0.0:
                    errors.append(f"{w_name} is negative: {val}")

        # 4. Rainfall monotonicity in complete windows: rainfall_1d <= rainfall_3d <= ...
        # Only valid when all windows are non-null and valid
        if (
            record.rainfall_1d is not None
            and record.rainfall_3d is not None
            and record.rainfall_1d > (record.rainfall_3d + 1e-4)
        ):
            errors.append(
                f"1d rainfall ({record.rainfall_1d}) exceeds 3d rainfall ({record.rainfall_3d})"
            )
        if (
            record.rainfall_3d is not None
            and record.rainfall_7d is not None
            and record.rainfall_3d > (record.rainfall_7d + 1e-4)
        ):
            errors.append(
                f"3d rainfall ({record.rainfall_3d}) exceeds 7d rainfall ({record.rainfall_7d})"
            )
        if (
            record.rainfall_7d is not None
            and record.rainfall_14d is not None
            and record.rainfall_7d > (record.rainfall_14d + 1e-4)
        ):
            errors.append(
                f"7d rainfall ({record.rainfall_7d}) exceeds 14d rainfall ({record.rainfall_14d})"
            )
        if (
            record.rainfall_14d is not None
            and record.rainfall_30d is not None
            and record.rainfall_14d > (record.rainfall_30d + 1e-4)
        ):
            errors.append(
                f"14d rainfall ({record.rainfall_14d}) exceeds 30d rainfall ({record.rainfall_30d})"
            )

        # 5. Temperature physical bounds and hierarchy: min <= mean <= max
        for t_name, val in [
            ("mean", record.temperature_mean_c),
            ("min", record.temperature_min_c),
            ("max", record.temperature_max_c),
        ]:
            if val is not None:
                if math.isnan(val) or math.isinf(val):
                    errors.append(f"temperature_{t_name}_c is non-finite: {val}")
                elif val < -50.0 or val > 65.0:
                    errors.append(f"temperature_{t_name}_c ({val}) out of realistic range [-50, 65] °C")

        if (
            record.temperature_min_c is not None
            and record.temperature_mean_c is not None
            and record.temperature_max_c is not None
        ):
            if not (record.temperature_min_c <= record.temperature_mean_c <= record.temperature_max_c):
                errors.append(
                    f"Inconsistent temperature hierarchy: min={record.temperature_min_c}, "
                    f"mean={record.temperature_mean_c}, max={record.temperature_max_c}"
                )

        # 6. Relative humidity [0, 100]
        if record.relative_humidity_mean_pct is not None:
            if math.isnan(record.relative_humidity_mean_pct) or math.isinf(record.relative_humidity_mean_pct):
                errors.append(f"relative_humidity_mean_pct is non-finite: {record.relative_humidity_mean_pct}")
            elif not (0.0 <= record.relative_humidity_mean_pct <= 100.0):
                errors.append(
                    f"relative_humidity_mean_pct ({record.relative_humidity_mean_pct}) out of [0, 100]"
                )

        # 7. Surface pressure > 0 hPa
        if record.surface_pressure_mean_hpa is not None:
            if math.isnan(record.surface_pressure_mean_hpa) or math.isinf(record.surface_pressure_mean_hpa):
                errors.append(f"surface_pressure_mean_hpa is non-finite: {record.surface_pressure_mean_hpa}")
            elif record.surface_pressure_mean_hpa <= 300.0 or record.surface_pressure_mean_hpa >= 1100.0:
                errors.append(
                    f"surface_pressure_mean_hpa ({record.surface_pressure_mean_hpa}) out of realistic range [300, 1100] hPa"
                )

        # 8. Elevation bounds for Karnataka (-50m to 3000m)
        if record.elevation is not None:
            if math.isnan(record.elevation) or math.isinf(record.elevation):
                errors.append(f"elevation is non-finite: {record.elevation}")
            elif not (-50.0 <= record.elevation <= 3000.0):
                errors.append(f"elevation ({record.elevation} m) out of realistic range [-50, 3000] m")

        # 9. Slope bounds [0, 90] degrees
        if record.slope is not None:
            if math.isnan(record.slope) or math.isinf(record.slope):
                errors.append(f"slope is non-finite: {record.slope}")
            elif not (0.0 <= record.slope <= 90.0):
                errors.append(f"slope ({record.slope}°) out of [0, 90] degrees")

        # 10. Distance to river >= 0
        if record.distance_to_river_m is not None:
            if math.isnan(record.distance_to_river_m) or math.isinf(record.distance_to_river_m):
                errors.append(f"distance_to_river_m is non-finite: {record.distance_to_river_m}")
            elif record.distance_to_river_m < 0.0:
                errors.append(f"distance_to_river_m ({record.distance_to_river_m} m) is negative")

        # 11. Provenance check
        if not record.chunk_id:
            errors.append("chunk_id must not be empty")
        if not record.raw_chunk_id:
            errors.append("raw_chunk_id must not be empty")
        if not record.raw_payload_sha256 or len(record.raw_payload_sha256) != 64:
            errors.append("raw_payload_sha256 must be a 64-character SHA-256 hex string")

        return errors
