"""
Historical Coverage Gate & Hydrological Data Quality Auditor.

Audits hydrological observation coverage across calendar years, stations,
and districts to enforce the scientific gate for ML dataset integration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DistrictYearCoverage:
    year: int
    district_name: str
    station_count: int
    observation_count: int
    expected_days: int
    observed_days: int
    coverage_pct: float
    status: str  # "BLOCKED_FOR_HISTORICAL_TRAINING" or "SUFFICIENT"


@dataclass(frozen=True)
class SupervisedPeriodCoverage:
    period_name: str
    start_date: str
    end_date: str
    total_calendar_days: int
    total_districts: int
    total_district_days: int
    districts_with_observations: int
    district_coverage_pct: float
    total_observations: int
    temporal_coverage_pct: float
    status: str
    decision_rationale: str


class HistoricalCoverageGate:
    """Evaluates hydrological coverage and governs eligibility for ML matrix integration."""

    HISTORICAL_BASELINE_PERIOD = ("1969-01-01", "1994-12-31", 9496, 294376)
    RECENT_SUPERVISED_PERIOD = ("2011-01-01", "2023-07-24", 4588, 142228)
    RECENT_INFERENCE_PERIOD = ("2023-07-25", "2025-12-31", 890, 27590)
    OPERATIONAL_FEED_PERIOD = ("2026-01-01", "2026-08-31", 243, 7533)

    MIN_REQUIRED_COVERAGE_PCT: float = 70.0  # Minimum temporal coverage threshold to unlock training

    @classmethod
    def evaluate_period(
        cls,
        period_name: str,
        start_date: str,
        end_date: str,
        total_calendar_days: int,
        total_district_days: int,
        observations_in_period: int,
        districts_with_obs: int,
    ) -> SupervisedPeriodCoverage:
        """Evaluate whether a specific period meets the scientific threshold for ML training."""
        dist_cov_pct = (districts_with_obs / 31.0) * 100.0
        # Expected observations if 1 reading per district-day
        temp_cov_pct = (observations_in_period / float(total_district_days)) * 100.0 if total_district_days > 0 else 0.0

        if temp_cov_pct < cls.MIN_REQUIRED_COVERAGE_PCT:
            status = "BLOCKED_FOR_HISTORICAL_TRAINING"
            rationale = (
                f"Coverage ({temp_cov_pct:.4f}%) is below the {cls.MIN_REQUIRED_COVERAGE_PCT}% "
                f"scientific threshold. Total observations = {observations_in_period} across "
                f"{total_district_days} district-days. Zero-filling or synthetic imputation is prohibited."
            )
        else:
            status = "SUFFICIENT"
            rationale = f"Coverage ({temp_cov_pct:.2f}%) satisfies minimum data completeness standards."

        return SupervisedPeriodCoverage(
            period_name=period_name,
            start_date=start_date,
            end_date=end_date,
            total_calendar_days=total_calendar_days,
            total_districts=31,
            total_district_days=total_district_days,
            districts_with_observations=districts_with_obs,
            district_coverage_pct=round(dist_cov_pct, 2),
            total_observations=observations_in_period,
            temporal_coverage_pct=round(temp_cov_pct, 4),
            status=status,
            decision_rationale=rationale,
        )

    @classmethod
    def evaluate_all_periods(cls, session: Session) -> dict[str, SupervisedPeriodCoverage]:
        """Query database and evaluate all canonical ML periods."""
        q = text("""
            SELECT
                count(CASE WHEN observed_at >= '1969-01-01' AND observed_at <= '1994-12-31 23:59:59' THEN 1 END) as count_historical,
                count(DISTINCT CASE WHEN observed_at >= '1969-01-01' AND observed_at <= '1994-12-31 23:59:59' THEN rs.district_id END) as dist_historical,
                count(CASE WHEN observed_at >= '2011-01-01' AND observed_at <= '2023-07-24 23:59:59' THEN 1 END) as count_recent,
                count(DISTINCT CASE WHEN observed_at >= '2011-01-01' AND observed_at <= '2023-07-24 23:59:59' THEN rs.district_id END) as dist_recent,
                count(CASE WHEN observed_at >= '2023-07-25' AND observed_at <= '2025-12-31 23:59:59' THEN 1 END) as count_inference,
                count(DISTINCT CASE WHEN observed_at >= '2023-07-25' AND observed_at <= '2025-12-31 23:59:59' THEN rs.district_id END) as dist_inference,
                count(CASE WHEN observed_at >= '2026-01-01' THEN 1 END) as count_operational,
                count(DISTINCT CASE WHEN observed_at >= '2026-01-01' THEN rs.district_id END) as dist_operational
            FROM river_observations ro
            JOIN river_stations rs ON ro.station_id = rs.id;
        """)
        row = session.execute(q).fetchone()

        hist = cls.evaluate_period(
            period_name="historical_baseline_1969_1994",
            start_date=cls.HISTORICAL_BASELINE_PERIOD[0],
            end_date=cls.HISTORICAL_BASELINE_PERIOD[1],
            total_calendar_days=cls.HISTORICAL_BASELINE_PERIOD[2],
            total_district_days=cls.HISTORICAL_BASELINE_PERIOD[3],
            observations_in_period=row.count_historical or 0,
            districts_with_obs=row.dist_historical or 0,
        )

        recent = cls.evaluate_period(
            period_name="recent_supervised_2011_2023",
            start_date=cls.RECENT_SUPERVISED_PERIOD[0],
            end_date=cls.RECENT_SUPERVISED_PERIOD[1],
            total_calendar_days=cls.RECENT_SUPERVISED_PERIOD[2],
            total_district_days=cls.RECENT_SUPERVISED_PERIOD[3],
            observations_in_period=row.count_recent or 0,
            districts_with_obs=row.dist_recent or 0,
        )

        inference = cls.evaluate_period(
            period_name="forward_inference_2023_2025",
            start_date=cls.RECENT_INFERENCE_PERIOD[0],
            end_date=cls.RECENT_INFERENCE_PERIOD[1],
            total_calendar_days=cls.RECENT_INFERENCE_PERIOD[2],
            total_district_days=cls.RECENT_INFERENCE_PERIOD[3],
            observations_in_period=row.count_inference or 0,
            districts_with_obs=row.dist_inference or 0,
        )

        operational = cls.evaluate_period(
            period_name="operational_telemetry_2026",
            start_date=cls.OPERATIONAL_FEED_PERIOD[0],
            end_date=cls.OPERATIONAL_FEED_PERIOD[1],
            total_calendar_days=cls.OPERATIONAL_FEED_PERIOD[2],
            total_district_days=cls.OPERATIONAL_FEED_PERIOD[3],
            observations_in_period=row.count_operational or 0,
            districts_with_obs=row.dist_operational or 0,
        )

        return {
            "historical_baseline_1969_1994": hist,
            "recent_supervised_2011_2023": recent,
            "forward_inference_2023_2025": inference,
            "operational_telemetry_2026": operational,
        }
