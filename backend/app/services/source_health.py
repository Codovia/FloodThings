"""
Dynamic source health service for FloodPulse.

Computes source health at runtime from:
- DataSource registration and activation state
- DataIngestionRun history, recent statuses, and consecutive failure counts
- Actual stored observation/forecast data timestamps

NOTE: All freshness thresholds applied here represent FloodPulse INTERNAL OPERATIONAL
POLICIES, configured in application settings. They are NOT SLAs or requirements
defined by upstream external data providers.

Health states:
- HEALTHY: Source is active, recent ingestion succeeded, and data is fresh per internal policy.
- DEGRADED: Source is active, but recent run failed (below failure threshold), returned
            partial errors, or data exceeds internal freshness policy threshold.
- DOWN: Source is inactive, has zero ingestion history, or has reached consecutive
        failure threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models.flood import FloodObservation
from app.db.models.hydrology import ReservoirObservation, RiverObservation
from app.db.models.system import DataIngestionRun, DataSource
from app.db.models.weather import RainfallObservation, WeatherObservation


class HealthStatus:
    """Supported source health states per Phase 2.5 specification."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class SourceHealthData:
    """Dynamic health evaluation for an external data source."""

    source_id: uuid.UUID
    name: str
    organization: str | None
    data_type: str | None
    update_frequency: str | None
    authority_level: str | None
    is_active: bool
    health_status: str
    health_reason: str
    last_attempted_at: datetime | None
    last_successful_at: datetime | None
    latest_data_timestamp: datetime | None
    latest_run_status: str | None
    consecutive_failures: int
    recent_error_message: str | None
    last_http_status_code: int | None = None


class SourceHealthService:
    """Evaluates external source health dynamically without schema alterations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_freshness_threshold_hours(self, source: DataSource) -> float | None:
        """Determine applicable FloodPulse internal operational freshness threshold in hours.

        Operational policy rules for Phase 2.5:
        1. Static / historical reference datasets (e.g. LGD administrative boundaries,
           IFI historical flood inventory) have update_frequency='STATIC' or data_type in
           ('GEOSPATIAL', 'HISTORICAL_FLOOD_DISASTER'). They have NO recurring operational
           freshness requirement (returns None).
        2. Group A automated source: Open-Meteo Weather API (operational weather and forecasts)
           applies the configured internal operational freshness threshold
           (self.settings.openmeteo_freshness_threshold_hours, default: 4 hours).
        3. All other sources (e.g. NWIC river stage telemetry, NWIC reservoir telemetry)
           do NOT have an automated recurring freshness policy defined in Phase 2.5 and must
           not silently inherit the Open-Meteo policy (returns None).

        NOTE: Freshness thresholds are FloodPulse internal operational policies, NOT
        upstream provider SLAs.
        """
        if source.update_frequency == "STATIC":
            return None
        if source.data_type in ("GEOSPATIAL", "HISTORICAL_FLOOD_DISASTER"):
            return None

        # Check if source is Open-Meteo operational meteorological source
        name_lower = (source.name or "").lower()
        org_lower = (source.organization or "").lower()
        if "open-meteo" in name_lower or "openmeteo" in name_lower or "open-meteo" in org_lower:
            return float(self.settings.openmeteo_freshness_threshold_hours)

        # Other sources without an explicitly defined freshness policy in Phase 2.5
        return None

    def get_source_health(
        self, session: Session, source_id: uuid.UUID
    ) -> SourceHealthData | None:
        """Compute dynamic health for a single DataSource."""
        source = session.get(DataSource, source_id)
        if source is None:
            return None
        return self._evaluate_source(session, source)

    def get_all_sources_health(self, session: Session) -> list[SourceHealthData]:
        """Compute dynamic health across all registered DataSources."""
        sources = session.scalars(
            select(DataSource).order_by(DataSource.name)
        ).all()
        return [self._evaluate_source(session, s) for s in sources]

    def get_source_runs(
        self,
        session: Session,
        source_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[DataIngestionRun], int]:
        """Retrieve paginated ingestion runs for a source ordered by started_at DESC."""
        total = session.execute(
            select(func.count(DataIngestionRun.id)).where(
                DataIngestionRun.source_id == source_id
            )
        ).scalar() or 0

        runs = session.scalars(
            select(DataIngestionRun)
            .where(DataIngestionRun.source_id == source_id)
            .order_by(DataIngestionRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        return list(runs), total

    def _evaluate_source(
        self, session: Session, source: DataSource
    ) -> SourceHealthData:
        """Evaluate dynamic health for a DataSource from current database state."""
        # 1. Source activation check
        if not source.is_active:
            return SourceHealthData(
                source_id=source.id,
                name=source.name,
                organization=source.organization,
                data_type=source.data_type,
                update_frequency=source.update_frequency,
                authority_level=source.authority_level,
                is_active=False,
                health_status=HealthStatus.DOWN,
                health_reason="Source is deactivated (is_active=False)",
                last_attempted_at=None,
                last_successful_at=None,
                latest_data_timestamp=None,
                latest_run_status=None,
                consecutive_failures=0,
                recent_error_message=None,
                last_http_status_code=None,
            )

        # 2. Retrieve recent ingestion runs (most recent first)
        recent_runs = session.scalars(
            select(DataIngestionRun)
            .where(DataIngestionRun.source_id == source.id)
            .order_by(DataIngestionRun.started_at.desc())
            .limit(10)
        ).all()

        if not recent_runs:
            return SourceHealthData(
                source_id=source.id,
                name=source.name,
                organization=source.organization,
                data_type=source.data_type,
                update_frequency=source.update_frequency,
                authority_level=source.authority_level,
                is_active=True,
                health_status=HealthStatus.DOWN,
                health_reason="No ingestion runs recorded in system history",
                last_attempted_at=None,
                last_successful_at=None,
                latest_data_timestamp=None,
                latest_run_status=None,
                consecutive_failures=0,
                recent_error_message=None,
                last_http_status_code=None,
            )

        latest_run = recent_runs[0]
        last_attempted_at = latest_run.started_at
        latest_run_status = latest_run.status
        recent_error_message = latest_run.error_message

        # Derive the most recently recorded HTTP status from runs that have one
        last_http_status_code: int | None = next(
            (r.http_status_code for r in recent_runs if r.http_status_code is not None),
            None,
        )

        # Count consecutive failures starting from latest completed run backwards
        consecutive_failures = 0
        for r in recent_runs:
            if r.status == "RUNNING":
                continue
            if r.status == "FAILED":
                consecutive_failures += 1
            else:
                break

        # Find latest successful completion timestamp (ingestion lifecycle)
        last_successful_at = session.execute(
            select(func.max(DataIngestionRun.completed_at)).where(
                DataIngestionRun.source_id == source.id,
                DataIngestionRun.status.in_(["SUCCESS", "PARTIAL"]),
            )
        ).scalar()

        # Retrieve actual latest observation/evidence timestamp stored in database
        latest_data_timestamp = self._get_latest_data_timestamp(session, source.id)

        # 3. Apply deterministic health algorithm
        failure_threshold = self.settings.source_health_consecutive_failure_threshold
        freshness_threshold_hours = self.get_freshness_threshold_hours(source)

        # Consecutive failure escalation to DOWN
        if consecutive_failures >= failure_threshold:
            health_status = HealthStatus.DOWN
            if latest_run_status == "RUNNING":
                health_reason = (
                    f"Down: {consecutive_failures} consecutive ingestion failures "
                    f"(threshold: {failure_threshold}); new ingestion attempt currently in progress. "
                    f"Latest error: {recent_error_message or 'unknown'}"
                )
            else:
                health_reason = (
                    f"Down: {consecutive_failures} consecutive ingestion failures "
                    f"(threshold: {failure_threshold}). Latest error: {recent_error_message or 'unknown'}"
                )
        elif latest_run_status == "FAILED":
            health_status = HealthStatus.DEGRADED
            health_reason = (
                f"Degraded: latest ingestion attempt failed ({consecutive_failures} failures); "
                f"previous valid data retained. Error: {recent_error_message or 'unknown'}"
            )
        elif latest_run_status == "PARTIAL":
            health_status = HealthStatus.DEGRADED
            health_reason = (
                f"Degraded: latest ingestion run completed with partial errors or record rejections. "
                f"Detail: {recent_error_message or 'partial failures reported'}"
            )
        elif latest_run_status == "RUNNING":
            # Semantically safe evaluation: RUNNING cannot automatically establish HEALTHY.
            # Health depends on existing verified data state and prior completed runs.
            completed_runs = [r for r in recent_runs if r.status != "RUNNING"]
            if not completed_runs:
                health_status = HealthStatus.DEGRADED
                health_reason = (
                    "Degraded: initial ingestion run in progress; no prior ingestion history or verified data exists"
                )
            else:
                prior_run = completed_runs[0]
                if prior_run.status == "FAILED":
                    health_status = HealthStatus.DEGRADED
                    health_reason = (
                        f"Degraded: previous ingestion run failed ({recent_error_message or 'error'}); "
                        f"new ingestion attempt currently in progress"
                    )
                elif prior_run.status == "PARTIAL":
                    health_status = HealthStatus.DEGRADED
                    health_reason = (
                        "Degraded: previous ingestion run completed with partial errors; "
                        "new ingestion attempt currently in progress"
                    )
                else:
                    # Prior run succeeded; check if existing data is fresh
                    if freshness_threshold_hours is not None:
                        if latest_data_timestamp is None:
                            health_status = HealthStatus.DEGRADED
                            health_reason = (
                                "Degraded: ingestion run in progress; no prior observation or model data stored"
                            )
                        else:
                            now = datetime.now(timezone.utc)
                            data_dt = (
                                latest_data_timestamp
                                if latest_data_timestamp.tzinfo
                                else latest_data_timestamp.replace(tzinfo=timezone.utc)
                            )
                            elapsed_hours = max(0.0, (now - data_dt).total_seconds() / 3600.0)
                            if elapsed_hours > freshness_threshold_hours:
                                health_status = HealthStatus.DEGRADED
                                health_reason = (
                                    f"Degraded: ingestion run in progress, but existing data is stale "
                                    f"per FloodPulse internal policy ({elapsed_hours:.1f}h since latest data, "
                                    f"threshold: {freshness_threshold_hours:.1f}h)"
                                )
                            else:
                                health_status = HealthStatus.HEALTHY
                                health_reason = (
                                    f"Healthy: ingestion run in progress; existing data remains fresh "
                                    f"per FloodPulse internal policy ({elapsed_hours:.1f}h since latest data, "
                                    f"threshold: {freshness_threshold_hours:.1f}h)"
                                )
                    else:
                        if latest_data_timestamp is not None or last_successful_at is not None:
                            health_status = HealthStatus.HEALTHY
                            health_reason = (
                                "Healthy: ingestion run in progress; existing verified baseline data is available"
                            )
                        else:
                            health_status = HealthStatus.DEGRADED
                            health_reason = (
                                "Degraded: ingestion run in progress; no prior verified data available"
                            )
        elif latest_run_status == "SUCCESS":
            # Check actual data freshness against FloodPulse internal policy where applicable
            if freshness_threshold_hours is not None:
                if latest_data_timestamp is None:
                    health_status = HealthStatus.DEGRADED
                    health_reason = (
                        "Degraded: ingestion succeeded but no observation or model data is stored in the database"
                    )
                else:
                    now = datetime.now(timezone.utc)
                    data_dt = (
                        latest_data_timestamp
                        if latest_data_timestamp.tzinfo
                        else latest_data_timestamp.replace(tzinfo=timezone.utc)
                    )
                    elapsed_hours = max(0.0, (now - data_dt).total_seconds() / 3600.0)
                    if elapsed_hours > freshness_threshold_hours:
                        health_status = HealthStatus.DEGRADED
                        health_reason = (
                            f"Degraded: data is stale per FloodPulse internal operational policy "
                            f"({elapsed_hours:.1f}h since latest data, threshold: {freshness_threshold_hours:.1f}h)"
                        )
                    else:
                        health_status = HealthStatus.HEALTHY
                        health_reason = (
                            f"Healthy: latest ingestion successful and data is fresh per FloodPulse internal policy "
                            f"({elapsed_hours:.1f}h since latest data, threshold: {freshness_threshold_hours:.1f}h)"
                        )
            else:
                # Static / historical or source without operational freshness policy
                health_status = HealthStatus.HEALTHY
                if source.update_frequency == "STATIC" or source.data_type in ("GEOSPATIAL", "HISTORICAL_FLOOD_DISASTER"):
                    health_reason = (
                        "Healthy: source ingestion succeeded; static/historical reference dataset with no recurring operational freshness requirement"
                    )
                else:
                    health_reason = (
                        "Healthy: latest ingestion successful (no automated operational freshness policy configured for this source in Phase 2.5)"
                    )
        else:
            health_status = HealthStatus.DEGRADED
            health_reason = f"Degraded: unexpected run status '{latest_run_status}'"

        return SourceHealthData(
            source_id=source.id,
            name=source.name,
            organization=source.organization,
            data_type=source.data_type,
            update_frequency=source.update_frequency,
            authority_level=source.authority_level,
            is_active=source.is_active,
            health_status=health_status,
            health_reason=health_reason,
            last_attempted_at=last_attempted_at,
            last_successful_at=last_successful_at,
            latest_data_timestamp=latest_data_timestamp,
            latest_run_status=latest_run_status,
            consecutive_failures=consecutive_failures,
            recent_error_message=recent_error_message,
            last_http_status_code=last_http_status_code,
        )

    def _get_latest_data_timestamp(
        self, session: Session, source_id: uuid.UUID
    ) -> datetime | None:
        """Extract actual physical/model observation timestamp for a source."""
        timestamps: list[datetime] = []

        # 1. Weather observations
        w_ts = session.execute(
            select(func.max(WeatherObservation.observed_at)).where(
                WeatherObservation.source_id == source_id
            )
        ).scalar()
        if w_ts is not None:
            timestamps.append(w_ts)

        # 2. Rainfall observations
        rf_ts = session.execute(
            select(func.max(RainfallObservation.observed_at)).where(
                RainfallObservation.source_id == source_id
            )
        ).scalar()
        if rf_ts is not None:
            timestamps.append(rf_ts)

        # 3. River observations
        riv_ts = session.execute(
            select(func.max(RiverObservation.observed_at)).where(
                RiverObservation.source_id == source_id
            )
        ).scalar()
        if riv_ts is not None:
            timestamps.append(riv_ts)

        # 4. Reservoir observations
        res_ts = session.execute(
            select(func.max(ReservoirObservation.observed_at)).where(
                ReservoirObservation.source_id == source_id
            )
        ).scalar()
        if res_ts is not None:
            timestamps.append(res_ts)

        # 5. Flood observations
        f_ts = session.execute(
            select(func.max(FloodObservation.observation_time)).where(
                FloodObservation.source_id == source_id
            )
        ).scalar()
        if f_ts is not None:
            timestamps.append(f_ts)

        if not timestamps:
            return None

        # Return max across all observation types, ensuring timezone awareness
        return max(
            ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            for ts in timestamps
        )
