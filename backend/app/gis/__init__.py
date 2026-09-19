"""
FloodPulse GIS Foundation Package.

Provides GIS normalization, projection, and spatial utilities
for authoritative Karnataka boundaries, hydrology, and terrain.
"""

from app.gis.ifi import (
    IfiEventNormalizer,
    IfiNormalizationResult,
    NormalizedIfiEvent,
    NormalizedIfiObservation,
    UnresolvedDistrictTokenRecord,
)
from app.gis.ksrsac import (
    EXPECTED_DISTRICT_COUNT,
    EXPECTED_STATE_COUNT,
    EXPECTED_TALUK_COUNT,
    EXPECTED_VIJAYANAGARA_TALUK_COUNT,
    GeometryRepairRecord,
    KsrsacAdminNormalizer,
    KsrsacCrsError,
    KsrsacFileNotFoundError,
    KsrsacNormalizationResult,
    KsrsacSchemaError,
    KsrsacTopologyError,
    KsrsacValidationError,
    NormalizedDistrict,
    NormalizedState,
    NormalizedTaluk,
    REQUIRED_DISTRICT_COLUMNS,
    REQUIRED_STATE_COLUMNS,
    REQUIRED_TALUK_COLUMNS,
)

__all__ = [
    "EXPECTED_DISTRICT_COUNT",
    "EXPECTED_STATE_COUNT",
    "EXPECTED_TALUK_COUNT",
    "EXPECTED_VIJAYANAGARA_TALUK_COUNT",
    "GeometryRepairRecord",
    "IfiEventNormalizer",
    "IfiNormalizationResult",
    "KsrsacAdminNormalizer",
    "KsrsacCrsError",
    "KsrsacFileNotFoundError",
    "KsrsacNormalizationResult",
    "KsrsacSchemaError",
    "KsrsacTopologyError",
    "KsrsacValidationError",
    "NormalizedDistrict",
    "NormalizedIfiEvent",
    "NormalizedIfiObservation",
    "NormalizedState",
    "NormalizedTaluk",
    "REQUIRED_DISTRICT_COLUMNS",
    "REQUIRED_STATE_COLUMNS",
    "REQUIRED_TALUK_COLUMNS",
    "UnresolvedDistrictTokenRecord",
]
