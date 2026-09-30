"""
Hydrology ML Integration Package.

Provides auditing, crosswalk generation, feature design, and historical coverage gating
for river-stage observations in Karnataka.
"""

from app.ml.hydrology.audit import (
    HydrologicalAuditSummary,
    HydrologicalDataAuditor,
    RiverStationRecord,
)
from app.ml.hydrology.crosswalk import (
    DistrictBasinLink,
    DistrictSubBasinLink,
    GaugeHydrologyLink,
    HydrologicalCrosswalk,
)
from app.ml.hydrology.features import (
    ABLATION_GROUPS,
    CANONICAL_27_PREDICTORS,
    CANDIDATE_HYDROLOGICAL_FEATURES,
    FeatureObservation,
    HydrologicalFeatureEngine,
)
from app.ml.hydrology.coverage import (
    HistoricalCoverageGate,
    SupervisedPeriodCoverage,
)

__all__ = [
    "HydrologicalAuditSummary",
    "HydrologicalDataAuditor",
    "RiverStationRecord",
    "DistrictBasinLink",
    "DistrictSubBasinLink",
    "GaugeHydrologyLink",
    "HydrologicalCrosswalk",
    "ABLATION_GROUPS",
    "CANONICAL_27_PREDICTORS",
    "CANDIDATE_HYDROLOGICAL_FEATURES",
    "FeatureObservation",
    "HydrologicalFeatureEngine",
    "HistoricalCoverageGate",
    "SupervisedPeriodCoverage",
]
