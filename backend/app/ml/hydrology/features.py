"""
Hydrological Feature Engineering & Temporal Alignment Engine.

Defines candidate river-stage features, temporal anti-leakage filters,
staleness detection, and ablation feature groups for multi-scale flood modeling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Feature Group Definitions
# ---------------------------------------------------------------------------

CANONICAL_27_PREDICTORS: list[str] = [
    "precip_1d_mm", "precip_3d_sum_mm", "precip_7d_sum_mm", "precip_14d_sum_mm",
    "precip_30d_sum_mm", "precip_7d_max_mm", "precip_14d_max_mm",
    "temp_mean_1d_c", "temp_min_1d_c", "temp_max_1d_c", "temp_7d_mean_c",
    "rh_mean_1d_pct", "rh_7d_mean_pct", "pressure_mean_1d_hpa",
    "elevation_mean_m", "elevation_min_m", "elevation_max_m", "elevation_std_m",
    "slope_mean_deg", "slope_max_deg", "major_basin_count", "primary_basin_coverage_pct",
    "sub_basin_count", "mean_upstream_area_km2", "weather_cell_count",
    "day_of_year", "target_month",
]

CANDIDATE_HYDROLOGICAL_FEATURES: list[str] = [
    "river_level_current",
    "river_level_lag_1d",
    "river_level_lag_3d",
    "river_level_change_1d",
    "river_level_change_3d",
    "river_level_rolling_max_3d",
    "river_level_rolling_max_7d",
    "upstream_station_count",
    "upstream_max_level",
    "upstream_mean_level",
]

ABLATION_GROUPS: dict[str, list[str]] = {
    "group_a_baseline": CANONICAL_27_PREDICTORS,
    "group_b_weather_terrain_hydrology": CANONICAL_27_PREDICTORS + CANDIDATE_HYDROLOGICAL_FEATURES,
    "group_c_hydrology_diagnostic": CANDIDATE_HYDROLOGICAL_FEATURES,
}


@dataclass(frozen=True)
class FeatureObservation:
    station_code: str
    observed_at_utc: datetime
    water_level_m: float
    district_name: str
    sub_basin_id: int | None = None
    is_upstream: bool = False


class HydrologicalFeatureEngine:
    """Computes district-day hydrological features with strict anti-leakage boundaries."""

    LOOKBACK_DAYS: int = 30
    STALENESS_HOURS: float = 72.0

    @classmethod
    def get_feature_window(cls, target_date: date) -> tuple[datetime, datetime]:
        """
        Return the strict [t-30, t-1] lookback window in UTC for target date t.
        
        Anchor: 00:00 UTC on target_date t.
        Window Start: 00:00 UTC on target_date - 30 days.
        Window End: 23:59:59.999999 UTC on target_date - 1 day.
        """
        target_midnight = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        window_end = target_midnight - timedelta(microseconds=1)
        window_start = target_midnight - timedelta(days=cls.LOOKBACK_DAYS)
        return window_start, window_end

    @classmethod
    def filter_observations_anti_leakage(
        cls,
        observations: list[FeatureObservation],
        target_date: date,
    ) -> list[FeatureObservation]:
        """
        Filter observations strictly to the [t-30, t-1] lookback window.
        
        Any observation with timestamp >= target_date 00:00 UTC is strictly rejected
        to prevent future target leakage.
        """
        window_start, window_end = cls.get_feature_window(target_date)
        return [
            obs for obs in observations
            if window_start <= obs.observed_at_utc <= window_end
        ]

    @classmethod
    def compute_district_hydrological_features(
        cls,
        target_date: date,
        district_name: str,
        observations: list[FeatureObservation],
    ) -> dict[str, float | None]:
        """
        Compute candidate hydrological features for a specific district-day.
        
        If observations are missing or empty:
        Returns float(np.nan) for numeric level features and 0 for station count.
        NEVER converts missing river levels to 0.0.
        """
        valid_obs = cls.filter_observations_anti_leakage(observations, target_date)
        district_obs = [o for o in valid_obs if o.district_name == district_name]

        features: dict[str, float | None] = {f: np.nan for f in CANDIDATE_HYDROLOGICAL_FEATURES}
        features["upstream_station_count"] = 0.0

        if not district_obs:
            return features

        # Sort chronologically
        district_obs.sort(key=lambda o: o.observed_at_utc)

        # Most recent observation in lookback window
        latest_obs = district_obs[-1]
        features["river_level_current"] = latest_obs.water_level_m

        # Staleness check
        target_midnight = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        age_hours = (target_midnight - latest_obs.observed_at_utc).total_seconds() / 3600.0
        is_stale = age_hours > cls.STALENESS_HOURS

        # Day t-1 observation (between [t-1 00:00, t-1 23:59])
        t_minus_1_start = target_midnight - timedelta(days=1)
        t_minus_1_end = target_midnight - timedelta(microseconds=1)
        obs_1d = [o for o in district_obs if t_minus_1_start <= o.observed_at_utc <= t_minus_1_end]
        if obs_1d:
            features["river_level_lag_1d"] = obs_1d[-1].water_level_m

        # Day t-2 observation
        t_minus_2_start = target_midnight - timedelta(days=2)
        t_minus_2_end = t_minus_1_start - timedelta(microseconds=1)
        obs_2d = [o for o in district_obs if t_minus_2_start <= o.observed_at_utc <= t_minus_2_end]

        # Day t-3 observation
        t_minus_3_start = target_midnight - timedelta(days=3)
        t_minus_3_end = t_minus_2_start - timedelta(microseconds=1)
        obs_3d = [o for o in district_obs if t_minus_3_start <= o.observed_at_utc <= t_minus_3_end]
        if obs_3d:
            features["river_level_lag_3d"] = obs_3d[-1].water_level_m

        # Day t-4 observation
        t_minus_4_start = target_midnight - timedelta(days=4)
        t_minus_4_end = t_minus_3_start - timedelta(microseconds=1)
        obs_4d = [o for o in district_obs if t_minus_4_start <= o.observed_at_utc <= t_minus_4_end]

        # Level change 1d: level(t-1) - level(t-2)
        if obs_1d and obs_2d:
            features["river_level_change_1d"] = obs_1d[-1].water_level_m - obs_2d[-1].water_level_m

        # Level change 3d: level(t-1) - level(t-4)
        if obs_1d and obs_4d:
            features["river_level_change_3d"] = obs_1d[-1].water_level_m - obs_4d[-1].water_level_m

        # Rolling max 3d: max within [t-3, t-1]
        obs_3d_window = [o for o in district_obs if t_minus_3_start <= o.observed_at_utc <= t_minus_1_end]
        if obs_3d_window:
            features["river_level_rolling_max_3d"] = max(o.water_level_m for o in obs_3d_window)

        # Rolling max 7d: max within [t-7, t-1]
        t_minus_7_start = target_midnight - timedelta(days=7)
        obs_7d_window = [o for o in district_obs if t_minus_7_start <= o.observed_at_utc <= t_minus_1_end]
        if obs_7d_window:
            features["river_level_rolling_max_7d"] = max(o.water_level_m for o in obs_7d_window)

        # Upstream metrics
        upstream_obs = [o for o in valid_obs if o.is_upstream]
        unique_upstream_stations = {o.station_code for o in upstream_obs}
        features["upstream_station_count"] = float(len(unique_upstream_stations))
        if upstream_obs:
            features["upstream_max_level"] = max(o.water_level_m for o in upstream_obs)
            features["upstream_mean_level"] = float(np.mean([o.water_level_m for o in upstream_obs]))

        return features
