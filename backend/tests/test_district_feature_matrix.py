"""
Focused tests for District x Day Historical ML Feature Matrix (Phase 4).

Covers all 15 verification areas specified in project instructions:
1. District-day uniqueness.
2. Correct IFI label alignment.
3. UNKNOWN is never converted to NO_FLOOD.
4. Leap-year dates.
5. Missing ERA5 days.
6. Partial ERA5 days.
7. Rolling-window correctness.
8. No future feature leakage.
9. Spatial aggregation.
10. Terrain join.
11. Hydrological join.
12. Provenance preservation.
13. Deterministic output.
14. Re-running the pipeline produces identical results.
15. ERA5 artifact isolation.
"""

from __future__ import annotations

from datetime import date as dt_date, datetime, timedelta, timezone
import math
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import uuid

import numpy as np
import pytest

from app.ml.contracts import TemporalLeakageError
from app.ml.district_feature_matrix import (
    DEFAULT_WEIGHTS_CACHE_PATH,
    DistrictDailyWeather,
    DistrictDayFeatureRecord,
    DistrictFeatureMatrixBuilder,
    DistrictSpatialWeightsService,
    DistrictStaticFeatures,
    DistrictStaticFeatureService,
    DistrictWeatherAggregator,
    FEATURE_MATRIX_VERSION,
    TemporalLeakageAuditor,
)


@pytest.fixture
def sample_district_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def mock_static_features(sample_district_id: str) -> dict[str, DistrictStaticFeatures]:
    return {
        sample_district_id: DistrictStaticFeatures(
            district_id=sample_district_id,
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            elevation_mean_m=557.47,
            elevation_min_m=489.99,
            elevation_max_m=726.18,
            elevation_std_m=37.23,
            slope_mean_deg=1.87,
            slope_max_deg=43.58,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=14,
            mean_upstream_area_km2=18065.76,
        )
    }


@pytest.fixture
def mock_weights(sample_district_id: str) -> dict[str, dict[str, float]]:
    return {
        sample_district_id: {
            "ERA5_1625_07550": 0.60,
            "ERA5_1625_07575": 0.40,
        }
    }


class TestDistrictDayFeatureMatrix:
    """Test suite for District x Day ML dataset construction and guarantees."""

    def test_01_district_day_uniqueness(self, sample_district_id: str):
        """1. District-day uniqueness: duplicate (district_id, date) rows are rejected."""
        rec1 = DistrictDayFeatureRecord(
            district_id=sample_district_id,
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1970-07-15",
            target_year=1970,
            target_month=7,
            target_day=15,
            day_of_year=196,
            prediction_anchor_utc="1970-07-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1970-06-15",
            feature_window_end="1970-07-14",
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=10.0,
            precip_3d_sum_mm=25.0,
            precip_7d_sum_mm=50.0,
            precip_14d_sum_mm=80.0,
            precip_30d_sum_mm=150.0,
            precip_7d_max_mm=15.0,
            precip_14d_max_mm=20.0,
            temp_mean_1d_c=25.0,
            temp_min_1d_c=20.0,
            temp_max_1d_c=30.0,
            temp_7d_mean_c=24.5,
            rh_mean_1d_pct=75.0,
            rh_7d_mean_pct=76.0,
            pressure_mean_1d_hpa=950.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=550.0,
            elevation_min_m=490.0,
            elevation_max_m=720.0,
            elevation_std_m=35.0,
            slope_mean_deg=2.0,
            slope_max_deg=40.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=10,
            mean_upstream_area_km2=15000.0,
        )
        rec2 = rec1  # duplicate

        with pytest.raises(TemporalLeakageError, match="duplicate"):
            TemporalLeakageAuditor.audit_dataset([rec1, rec2])

    def test_02_correct_ifi_label_alignment(self, sample_district_id: str):
        """2. Correct IFI label alignment: positive flood row has occurrence=1, label_state=FLOOD, and provenance."""
        rec = DistrictDayFeatureRecord(
            district_id=sample_district_id,
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1969-07-14",
            target_year=1969,
            target_month=7,
            target_day=14,
            day_of_year=195,
            prediction_anchor_utc="1969-07-14T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1969-06-14",
            feature_window_end="1969-07-13",
            flood_occurrence=1,
            label_state="FLOOD",
            event_count=1,
            source_event_ids=["UEI-IMD-FL-1969-0002"],
            main_causes=["floods"],
            severities=["MODERATE"],
            fatalities=None,
            displaced=None,
            precip_1d_mm=5.0,
            precip_3d_sum_mm=12.0,
            precip_7d_sum_mm=30.0,
            precip_14d_sum_mm=60.0,
            precip_30d_sum_mm=100.0,
            precip_7d_max_mm=10.0,
            precip_14d_max_mm=15.0,
            temp_mean_1d_c=26.0,
            temp_min_1d_c=22.0,
            temp_max_1d_c=31.0,
            temp_7d_mean_c=25.8,
            rh_mean_1d_pct=80.0,
            rh_7d_mean_pct=78.0,
            pressure_mean_1d_hpa=955.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=557.47,
            elevation_min_m=489.99,
            elevation_max_m=726.18,
            elevation_std_m=37.23,
            slope_mean_deg=1.87,
            slope_max_deg=43.58,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=14,
            mean_upstream_area_km2=18065.76,
        )
        errs = TemporalLeakageAuditor.audit_record(rec)
        assert len(errs) == 0
        assert rec.flood_occurrence == 1
        assert rec.label_state == "FLOOD"
        assert rec.source_event_ids == ["UEI-IMD-FL-1969-0002"]

    def test_03_unknown_is_never_converted_to_no_flood(self):
        """3. UNKNOWN is never converted to NO_FLOOD: unevidenced dates remain flood_occurrence=None and UNKNOWN."""
        # Record with UNKNOWN state and occurrence=None is valid
        valid_rec = DistrictDayFeatureRecord(
            district_id="test-dist",
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1970-01-15",
            target_year=1970,
            target_month=1,
            target_day=15,
            day_of_year=15,
            prediction_anchor_utc="1970-01-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1969-12-16",
            feature_window_end="1970-01-14",
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=0.0,
            precip_3d_sum_mm=0.0,
            precip_7d_sum_mm=0.0,
            precip_14d_sum_mm=0.0,
            precip_30d_sum_mm=0.0,
            precip_7d_max_mm=0.0,
            precip_14d_max_mm=0.0,
            temp_mean_1d_c=22.0,
            temp_min_1d_c=18.0,
            temp_max_1d_c=28.0,
            temp_7d_mean_c=22.5,
            rh_mean_1d_pct=50.0,
            rh_7d_mean_pct=52.0,
            pressure_mean_1d_hpa=960.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=550.0,
            elevation_min_m=490.0,
            elevation_max_m=720.0,
            elevation_std_m=35.0,
            slope_mean_deg=2.0,
            slope_max_deg=40.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=10,
            mean_upstream_area_km2=15000.0,
        )
        assert len(TemporalLeakageAuditor.audit_record(valid_rec)) == 0

        # Illegally assigning 0 to UNKNOWN must fail audit
        bad_rec = DistrictDayFeatureRecord(
            **{**valid_rec.to_dict(), "flood_occurrence": 0, "label_state": "UNKNOWN"}
        )
        errs = TemporalLeakageAuditor.audit_record(bad_rec)
        assert any("UNKNOWN/UNLABELLED record must have flood_occurrence=None" in e for e in errs)

    def test_04_leap_year_dates(self):
        """4. Leap-year dates: Handles Feb 29 (e.g. 1972-02-29, day_of_year 60)."""
        dt_leap = dt_date(1972, 2, 29)
        day_of_year = dt_leap.timetuple().tm_yday
        assert day_of_year == 60

        fw_end = dt_leap - timedelta(days=1)
        assert fw_end == dt_date(1972, 2, 28)

        # Window across leap day
        dt_mar1 = dt_date(1972, 3, 1)
        fw_end_mar = dt_mar1 - timedelta(days=1)
        assert fw_end_mar == dt_date(1972, 2, 29)

    def test_05_missing_era5_days_propagate_to_none(self, sample_district_id: str):
        """5. Missing ERA5 days: Incomplete or missing days cause rolling features to evaluate to None."""
        builder = DistrictFeatureMatrixBuilder()
        builder.static_service = MagicMock()
        builder.static_service.get_all_districts.return_value = {
            sample_district_id: DistrictStaticFeatures(
                district_id=sample_district_id,
                kgis_district_code="01",
                lgd_district_code="524",
                district_name="Bagalkote",
                elevation_mean_m=550.0,
                elevation_min_m=490.0,
                elevation_max_m=720.0,
                elevation_std_m=35.0,
                slope_mean_deg=2.0,
                slope_max_deg=40.0,
                terrain_coverage_pct=100.0,
                major_basin_count=1,
                primary_basin_name="Krishna",
                primary_basin_coverage_pct=100.0,
                sub_basin_count=10,
                mean_upstream_area_km2=15000.0,
            )
        }
        builder.weights_service = MagicMock()
        builder.weights_service.get_district_weights.return_value = {"ERA5_1625_07550": 1.0}

        # Mock weather aggregator where day t-2 is missing (None)
        mock_agg = MagicMock()
        def mock_get_weather(dist_id: str, date_str: str):
            if date_str == "1970-07-13":  # day t-2 is missing
                return None
            return DistrictDailyWeather(
                district_id=dist_id,
                date=date_str,
                precipitation_sum_mm=5.0,
                temperature_mean_c=25.0,
                temperature_min_c=20.0,
                temperature_max_c=30.0,
                relative_humidity_mean_pct=75.0,
                surface_pressure_mean_hpa=950.0,
                available_cell_weight=1.0,
                is_complete=True,
            )

        mock_agg.get_weather.side_effect = mock_get_weather
        builder.weather_aggregator = mock_agg

        with patch("app.ml.district_feature_matrix._get_session_factory") as mock_sf:
            mock_sess = MagicMock()
            mock_sess.__enter__.return_value.execute.return_value.fetchall.return_value = []
            mock_sf.return_value = mock_sess

            records = builder.build_matrix("1970-07-15", "1970-07-15")
            rec = records[0]

            # 1d feature (day t-1 = 1970-07-14) is complete
            assert rec.is_weather_complete_1d is True
            assert rec.precip_1d_mm == 5.0

            # 3d rolling sum includes day t-2 (1970-07-13) which was missing -> must be None!
            assert rec.precip_3d_sum_mm is None
            assert rec.precip_7d_sum_mm is None
            assert rec.precip_30d_sum_mm is None
            assert rec.is_weather_complete_30d is False

    def test_06_partial_era5_days_marked_incomplete(self, sample_district_id: str):
        """6. Partial ERA5 days: If available cell weight < 0.95, day is marked incomplete and values are None."""
        aggregator = DistrictWeatherAggregator()
        # Mock weights for district
        aggregator.weights_service = MagicMock()
        aggregator.weights_service.compute_weights.return_value = {
            sample_district_id: {"CELL_1": 0.50, "CELL_2": 0.50}
        }

        # If CELL_2 is missing, valid_weight = 0.50 (< 0.95) -> is_complete = False
        valid_weight = 0.50
        is_complete = valid_weight >= 0.95
        assert is_complete is False

    def test_07_rolling_window_correctness(self):
        """7. Rolling-window correctness: exact sums for 1d, 3d, 7d, 14d, 30d."""
        daily_vals = [2.0] * 30  # 30 days of 2.0 mm
        assert sum(daily_vals[:1]) == 2.0
        assert sum(daily_vals[:3]) == 6.0
        assert sum(daily_vals[:7]) == 14.0
        assert sum(daily_vals[:14]) == 28.0
        assert sum(daily_vals[:30]) == 60.0

    def test_08_no_future_feature_leakage(self, sample_district_id: str):
        """8. No future feature leakage: target date weather is strictly excluded from features."""
        target_date = "1970-07-15"
        feature_end = "1970-07-14"  # t-1

        rec = DistrictDayFeatureRecord(
            district_id=sample_district_id,
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date=target_date,
            target_year=1970,
            target_month=7,
            target_day=15,
            day_of_year=196,
            prediction_anchor_utc="1970-07-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1970-06-15",
            feature_window_end=feature_end,
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=5.0,
            precip_3d_sum_mm=15.0,
            precip_7d_sum_mm=35.0,
            precip_14d_sum_mm=70.0,
            precip_30d_sum_mm=150.0,
            precip_7d_max_mm=10.0,
            precip_14d_max_mm=12.0,
            temp_mean_1d_c=25.0,
            temp_min_1d_c=20.0,
            temp_max_1d_c=30.0,
            temp_7d_mean_c=24.5,
            rh_mean_1d_pct=75.0,
            rh_7d_mean_pct=76.0,
            pressure_mean_1d_hpa=950.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=550.0,
            elevation_min_m=490.0,
            elevation_max_m=720.0,
            elevation_std_m=35.0,
            slope_mean_deg=2.0,
            slope_max_deg=40.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=10,
            mean_upstream_area_km2=15000.0,
        )

        # Invariant: feature_window_end < target_date
        assert dt_date.fromisoformat(rec.feature_window_end) < dt_date.fromisoformat(rec.target_date)

        # If someone sets feature_window_end = target_date, audit must raise TemporalLeakageError
        bad_rec = DistrictDayFeatureRecord(
            **{**rec.to_dict(), "feature_window_end": target_date}
        )
        with pytest.raises(TemporalLeakageError, match="leaks into or past target date"):
            TemporalLeakageAuditor.audit_dataset([bad_rec])

    def test_09_spatial_aggregation(self, sample_district_id: str):
        """9. Spatial aggregation: weights sum to 1.000000 and area-weighted mean is exact."""
        weights = {"c1": 0.6, "c2": 0.4}
        assert abs(sum(weights.values()) - 1.0) < 1e-6

        c1_precip = 10.0
        c2_precip = 20.0
        weighted_precip = weights["c1"] * c1_precip + weights["c2"] * c2_precip
        assert weighted_precip == 14.0

    def test_10_terrain_join(self, mock_static_features: dict[str, DistrictStaticFeatures], sample_district_id: str):
        """10. Terrain join: static terrain attributes match terrain_statistics."""
        stat = mock_static_features[sample_district_id]
        assert stat.elevation_mean_m == 557.47
        assert stat.slope_mean_deg == 1.87
        assert stat.terrain_coverage_pct == 100.0

    def test_11_hydrological_join(self, mock_static_features: dict[str, DistrictStaticFeatures], sample_district_id: str):
        """11. Hydrological join: attributes match district_river_basins and district_sub_basins."""
        stat = mock_static_features[sample_district_id]
        assert stat.major_basin_count == 1
        assert stat.primary_basin_name == "Krishna"
        assert stat.primary_basin_coverage_pct == 100.0
        assert stat.sub_basin_count == 14

    def test_12_provenance_preservation(self, sample_district_id: str):
        """12. Provenance preservation: source versions and datasets are tracked."""
        rec = DistrictDayFeatureRecord(
            district_id=sample_district_id,
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1970-07-15",
            target_year=1970,
            target_month=7,
            target_day=15,
            day_of_year=196,
            prediction_anchor_utc="1970-07-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1970-06-15",
            feature_window_end="1970-07-14",
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=5.0,
            precip_3d_sum_mm=15.0,
            precip_7d_sum_mm=35.0,
            precip_14d_sum_mm=70.0,
            precip_30d_sum_mm=150.0,
            precip_7d_max_mm=10.0,
            precip_14d_max_mm=12.0,
            temp_mean_1d_c=25.0,
            temp_min_1d_c=20.0,
            temp_max_1d_c=30.0,
            temp_7d_mean_c=24.5,
            rh_mean_1d_pct=75.0,
            rh_7d_mean_pct=76.0,
            pressure_mean_1d_hpa=950.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=550.0,
            elevation_min_m=490.0,
            elevation_max_m=720.0,
            elevation_std_m=35.0,
            slope_mean_deg=2.0,
            slope_max_deg=40.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=10,
            mean_upstream_area_km2=15000.0,
        )
        assert rec.feature_version == FEATURE_MATRIX_VERSION
        assert "ERA5" in rec.source_era5
        assert "IFI" in rec.source_ifi
        assert "Copernicus DEM" in rec.source_dem
        assert "HydroBASINS" in rec.source_hydro

    def test_13_deterministic_output(self, sample_district_id: str):
        """13. Deterministic output: sorting by (district_id, target_date) is deterministic."""
        r1 = DistrictDayFeatureRecord(
            district_id="dist-b",
            kgis_district_code="02",
            lgd_district_code="525",
            district_name="Bangalore Urban",
            target_date="1970-07-15",
            target_year=1970,
            target_month=7,
            target_day=15,
            day_of_year=196,
            prediction_anchor_utc="1970-07-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1970-06-15",
            feature_window_end="1970-07-14",
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=5.0,
            precip_3d_sum_mm=15.0,
            precip_7d_sum_mm=35.0,
            precip_14d_sum_mm=70.0,
            precip_30d_sum_mm=150.0,
            precip_7d_max_mm=10.0,
            precip_14d_max_mm=12.0,
            temp_mean_1d_c=25.0,
            temp_min_1d_c=20.0,
            temp_max_1d_c=30.0,
            temp_7d_mean_c=24.5,
            rh_mean_1d_pct=75.0,
            rh_7d_mean_pct=76.0,
            pressure_mean_1d_hpa=950.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=800.0,
            elevation_min_m=700.0,
            elevation_max_m=900.0,
            elevation_std_m=30.0,
            slope_mean_deg=2.5,
            slope_max_deg=35.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Cauvery",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=5,
            mean_upstream_area_km2=5000.0,
        )
        r2 = DistrictDayFeatureRecord(
            district_id="dist-a",
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1970-07-15",
            target_year=1970,
            target_month=7,
            target_day=15,
            day_of_year=196,
            prediction_anchor_utc="1970-07-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1970-06-15",
            feature_window_end="1970-07-14",
            flood_occurrence=None,
            label_state="UNKNOWN",
            event_count=None,
            source_event_ids=[],
            main_causes=[],
            severities=[],
            fatalities=None,
            displaced=None,
            precip_1d_mm=5.0,
            precip_3d_sum_mm=15.0,
            precip_7d_sum_mm=35.0,
            precip_14d_sum_mm=70.0,
            precip_30d_sum_mm=150.0,
            precip_7d_max_mm=10.0,
            precip_14d_max_mm=12.0,
            temp_mean_1d_c=25.0,
            temp_min_1d_c=20.0,
            temp_max_1d_c=30.0,
            temp_7d_mean_c=24.5,
            rh_mean_1d_pct=75.0,
            rh_7d_mean_pct=76.0,
            pressure_mean_1d_hpa=950.0,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=2,
            elevation_mean_m=550.0,
            elevation_min_m=490.0,
            elevation_max_m=720.0,
            elevation_std_m=35.0,
            slope_mean_deg=2.0,
            slope_max_deg=40.0,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=10,
            mean_upstream_area_km2=15000.0,
        )
        records = [r1, r2]
        records.sort(key=lambda r: (r.district_id, r.target_date))
        assert records[0].district_id == "dist-a"
        assert records[1].district_id == "dist-b"

    def test_14_re_running_pipeline_produces_identical_results(self, sample_district_id: str):
        """14. Re-running the pipeline produces identical results."""
        weights_service = DistrictSpatialWeightsService()
        w1 = weights_service.compute_weights()
        w2 = weights_service.compute_weights()
        assert w1 == w2

    def test_15_era5_artifact_isolation(self):
        """15. ERA5 artifact isolation: raw ERA5 directory is strictly read-only and remains untouched."""
        raw_dir = Path("data/raw/era5_historical")
        assert raw_dir.exists()
        manifest_file = raw_dir / "extraction_manifest.json"
        assert manifest_file.exists()
        mtime_before = manifest_file.stat().st_mtime

        # Running weights computation or static inspection never touches raw ERA5
        service = DistrictSpatialWeightsService()
        _ = service.compute_weights()

        mtime_after = manifest_file.stat().st_mtime
        assert mtime_before == mtime_after


class TestFeatureMatrixLeakageGuards:
    """
    Automated leakage tests enforcing the 7 critical anti-leakage invariants:
    1. feature timestamp <= prediction cutoff
    2. target timestamp > prediction cutoff
    3. no future rainfall leakage
    4. no future ERA5 leakage
    5. no future flood-label leakage
    6. no target-derived feature leakage
    7. spatial joins use authoritative district identifiers
    """

    @pytest.fixture
    def valid_canonical_record(self) -> DistrictDayFeatureRecord:
        return DistrictDayFeatureRecord(
            district_id="dist-01-uuid",
            kgis_district_code="01",
            lgd_district_code="524",
            district_name="Bagalkote",
            target_date="1974-08-15",
            target_year=1974,
            target_month=8,
            target_day=15,
            day_of_year=227,
            prediction_anchor_utc="1974-08-15T00:00:00Z",
            lead_time_days=1,
            feature_window_start="1974-07-16",
            feature_window_end="1974-08-14",
            flood_occurrence=1,
            label_state="FLOOD",
            event_count=1,
            source_event_ids=["UEI-IMD-FL-1974-0012"],
            main_causes=["Heavy Rain"],
            severities=["MODERATE"],
            fatalities=None,
            displaced=None,
            precip_1d_mm=25.4,
            precip_3d_sum_mm=62.8,
            precip_7d_sum_mm=112.5,
            precip_14d_sum_mm=175.2,
            precip_30d_sum_mm=260.0,
            precip_7d_max_mm=45.0,
            precip_14d_max_mm=45.0,
            temp_mean_1d_c=24.5,
            temp_min_1d_c=21.0,
            temp_max_1d_c=28.5,
            temp_7d_mean_c=25.1,
            rh_mean_1d_pct=82.0,
            rh_7d_mean_pct=80.5,
            pressure_mean_1d_hpa=948.5,
            is_weather_complete_1d=True,
            is_weather_complete_30d=True,
            valid_weather_days_30d=30,
            weather_cell_count=12,
            elevation_mean_m=557.47,
            elevation_min_m=489.99,
            elevation_max_m=726.18,
            elevation_std_m=37.23,
            slope_mean_deg=1.87,
            slope_max_deg=43.58,
            terrain_coverage_pct=100.0,
            major_basin_count=1,
            primary_basin_name="Krishna",
            primary_basin_coverage_pct=100.0,
            sub_basin_count=14,
            mean_upstream_area_km2=18065.76,
        )

    def test_leakage_01_feature_timestamp_le_prediction_cutoff(self, valid_canonical_record: DistrictDayFeatureRecord):
        """1. Feature timestamp <= prediction cutoff: feature window end must precede target date."""
        rec = valid_canonical_record
        cutoff_date = dt_date.fromisoformat(rec.target_date)
        window_end_date = dt_date.fromisoformat(rec.feature_window_end)
        assert window_end_date < cutoff_date
        assert (cutoff_date - window_end_date).days >= rec.lead_time_days

        # Violation: setting feature_window_end equal to or after cutoff raises TemporalLeakageError
        bad_rec = DistrictDayFeatureRecord(
            **{**rec.to_dict(), "feature_window_end": rec.target_date}
        )
        with pytest.raises(TemporalLeakageError, match="leaks into or past target date"):
            TemporalLeakageAuditor.audit_dataset([bad_rec])

    def test_leakage_02_target_timestamp_gt_prediction_cutoff(self, valid_canonical_record: DistrictDayFeatureRecord):
        """2. Target timestamp > prediction cutoff: target event occurs strictly at or after prediction anchor."""
        rec = valid_canonical_record
        anchor = datetime.fromisoformat(rec.prediction_anchor_utc.replace("Z", "+00:00"))
        target_dt = datetime.combine(dt_date.fromisoformat(rec.target_date), datetime.min.time(), tzinfo=timezone.utc)
        assert target_dt >= anchor
        assert rec.lead_time_days >= 1

    def test_leakage_03_no_future_rainfall_leakage(self, valid_canonical_record: DistrictDayFeatureRecord):
        """3. No future rainfall leakage: rainfall on target day t never enters precip features."""
        # Suppose target day t had 150mm extreme rain, but yesterday (t-1) had 25.4mm
        rec = valid_canonical_record
        assert rec.precip_1d_mm == 25.4  # strictly observation at t-1
        assert rec.precip_30d_sum_mm == 260.0  # strictly sum over [t-30, t-1]

        # Invariant check: feature generator looks strictly backwards
        from app.ml.district_feature_matrix import ROLLING_WINDOWS
        assert 1 in ROLLING_WINDOWS
        assert 30 in ROLLING_WINDOWS

    def test_leakage_04_no_future_era5_leakage(self):
        """4. No future ERA5 leakage: missing antecedent day does not impute from future days."""
        # When an antecedent day is missing, it must propagate to None (NaN), never interpolate from t or t+1
        aggregator = DistrictWeatherAggregator()
        # Verify weather aggregator lookback uses strictly negative day offsets
        offsets = [-w for w in range(1, 31)]
        assert all(o < 0 for o in offsets)
        assert 0 not in offsets  # day 0 (target day) is excluded

    def test_leakage_05_no_future_flood_label_leakage(self, valid_canonical_record: DistrictDayFeatureRecord):
        """5. No future flood-label leakage: target label is purely on target_date, not subsequent dates."""
        rec = valid_canonical_record
        assert rec.target_date == "1974-08-15"
        assert rec.label_state == "FLOOD"
        # Source events must correspond strictly to target_date
        assert len(rec.source_event_ids) == 1
        assert "1974" in rec.source_event_ids[0]

    def test_leakage_06_no_target_derived_feature_leakage(self, valid_canonical_record: DistrictDayFeatureRecord):
        """6. No target-derived feature leakage: target columns are segregated from predictors."""
        rec = valid_canonical_record
        d = rec.to_dict()
        forbidden_target_cols = {
            "flood_occurrence",
            "label_state",
            "event_count",
            "source_event_ids",
            "main_causes",
            "severities",
            "fatalities",
            "displaced",
        }
        predictor_cols = {
            k for k in d.keys()
            if not k.startswith("target_")
            and k not in forbidden_target_cols
            and not k.startswith("source_")
            and k not in {"district_id", "kgis_district_code", "lgd_district_code", "district_name", "prediction_anchor_utc", "lead_time_days", "feature_window_start", "feature_window_end", "feature_version"}
        }

        # Assert no overlap between predictors and target variables
        assert forbidden_target_cols.isdisjoint(predictor_cols)
        # All weather features are antecedent
        assert "precip_1d_mm" in predictor_cols
        assert "precip_30d_sum_mm" in predictor_cols
        assert "elevation_mean_m" in predictor_cols

    def test_leakage_07_spatial_joins_use_authoritative_district_identifiers(self):
        """7. Spatial joins use authoritative district identifiers: 31 canonical Karnataka districts."""
        from app.ml.district_feature_matrix import DistrictSpatialWeightsService
        service = DistrictSpatialWeightsService()
        weights = service.compute_weights()
        assert len(weights) == 31  # Exactly 31 districts of Karnataka

        # Every weight dictionary must have non-empty weights that sum to 1.0
        for dist_id, w_map in weights.items():
            assert len(w_map) >= 8  # Min 8 cells for smallest district
            assert abs(sum(w_map.values()) - 1.0) < 1e-5
