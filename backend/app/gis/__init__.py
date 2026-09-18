"""
FloodPulse GIS Foundation Package.

Provides GIS normalization, projection, and spatial utilities
for authoritative Karnataka boundaries, hydrology, and terrain.
"""

from app.gis.ksrsac import (
    GeometryRepairRecord,
    KsrsacAdminNormalizer,
    KsrsacCrsError,
    KsrsacFileNotFoundError,
    KsrsacNormalizationResult,
    KsrsacSchemaError,
    KsrsacTopologyError,
    KsrsacValidationError,
    NormalizedDistrict,
    NormalizedTaluk,
)

__all__ = [
    "GeometryRepairRecord",
    "KsrsacAdminNormalizer",
    "KsrsacCrsError",
    "KsrsacFileNotFoundError",
    "KsrsacNormalizationResult",
    "KsrsacSchemaError",
    "KsrsacTopologyError",
    "KsrsacValidationError",
    "NormalizedDistrict",
    "NormalizedTaluk",
]
