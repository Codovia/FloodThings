"""
FloodPulse SQLAlchemy models — package root.

Imports all model modules so that Base.metadata contains the complete
schema when Alembic reads it.
"""

from app.db.models.geography import (  # noqa: F401
    District,
    Locality,
    State,
    Taluk,
)
from app.db.models.hydrology import (  # noqa: F401
    DistrictRiverBasin,
    DistrictSubBasin,
    Reservoir,
    ReservoirObservation,
    River,
    RiverBasin,
    RiverForecast,
    RiverObservation,
    RiverStation,
    SubBasin,
)
from app.db.models.weather import (  # noqa: F401
    RainfallObservation,
    WeatherForecast,
    WeatherObservation,
)
from app.db.models.flood import (  # noqa: F401
    FloodEvent,
    FloodHazardZone,
    FloodObservation,
)
from app.db.models.terrain import (  # noqa: F401
    LandCover,
    TerrainDataset,
    WaterBody,
)
from app.db.models.prediction import (  # noqa: F401
    FeatureSnapshot,
    FloodPrediction,
    MLDatasetVersion,
    MLModel,
    PredictionGridCell,
)
from app.db.models.emergency import (  # noqa: F401
    CommunityReport,
    EmergencyFacility,
)
from app.db.models.alert import (  # noqa: F401
    Alert,
    TelegramSubscription,
)
from app.db.models.system import (  # noqa: F401
    AuditLog,
    DataIngestionRun,
    DataSource,
    User,
)
