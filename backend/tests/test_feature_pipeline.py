"""
Comprehensive tests for the ML Historical Feature Pipeline.

Covers:
1. Rainfall rolling windows (1d, 3d, 7d, 14d, 30d) calculation and sums
2. Date ordering and chronologically sorted processing
3. No temporal leakage (future observations cannot enter past features)
4. Cell identity preservation (cell_id and coordinates)
5. Chunk provenance preservation (chunk_id, raw_chunk_id, SHA-256)
6. Missing-day behaviour (zero silent zero-filling; explicit NaN/None)
7. Partial-day behaviour (hour_count < 24 / INCOMPLETE handling)
8. Deterministic output (reproducibility across repeated runs)
9. Real ERA5 artifact processing (end-to-end with real DEM and PostGIS GIS layers)
10. Cross-year lookback continuity
"""

from __future__ import annotations

from datetime import date as dt_date, timedelta
import json
import math
from pathlib import Path
import numpy as np
import pytest
import pyarrow.parquet as pq

from app.ingestion.historical.daily_models import DailyQualityStatus, DailyRecord
from app.ml.feature_generator import FeatureGenerator
from app.ml.feature_pipeline import FeaturePipelineConfig, MLFeaturePipeline
from app.ml.feature_schema import ARROW_FEATURE_SCHEMA, FeatureQualityValidator, MLFeatureRecord
from app.ml.spatial_enrichment import CellSpatialAttributes, SpatialEnrichmentService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mock_spatial_service() -> SpatialEnrichmentService:
    """Provide a mock SpatialEnrichmentService with deterministic spatial attributes."""
    svc = SpatialEnrichmentService(auto_load=False)
    # Inject mock for sample cell
    cell_id = "ERA5_1425_07650"
    svc.set_mock_attributes(
        cell_id,
        CellSpatialAttributes(
            cell_id=cell_id,
            latitude=14.25,
            longitude=76.5,
            elevation_mean=650.0,
            slope_mean=3.5,
            basin_id="b1111111-1111-1111-1111-111111111111",
            basin_name="Krishna",
            sub_basin_id="s1111111-1111-1111-1111-111111111111",
            sub_basin_name="HYBAS_4071140001",
            hybas_id=4071140001,
            distance_to_river_m=1250.0,
            nearest_river_id="HYRIV_12345",
            district_id="d1111111-1111-1111-1111-111111111111",
            district_name="Chitradurga",
        ),
    )
    return svc


def make_daily_record(
    date_str: str,
    cell_id: str = "ERA5_1425_07650",
    lat: float = 14.25,
    lon: float = 76.5,
    precip: float = 1.0,
    temp_mean: float = 25.0,
    rh_mean: float = 60.0,
    pressure_mean: float = 950.0,
    hour_count: int = 24,
    quality_status: str = "COMPLETE",
    chunk_id: str = "era5_test_chunk_001",
    raw_sha: str = "a" * 64,
) -> DailyRecord:
    """Helper to construct a valid DailyRecord."""
    return DailyRecord(
        date=date_str,
        cell_id=cell_id,
        latitude=lat,
        longitude=lon,
        precipitation_total_mm=precip,
        temperature_mean_c=temp_mean,
        temperature_min_c=temp_mean - 5.0,
        temperature_max_c=temp_mean + 5.0,
        relative_humidity_mean_pct=rh_mean,
        surface_pressure_mean_hpa=pressure_mean,
        hour_count=hour_count,
        quality_status=quality_status,
        chunk_id=chunk_id,
        raw_chunk_id=chunk_id,
        raw_payload_sha256=raw_sha,
    )


# ==============================================================================
# 1. Rainfall Rolling Windows Calculation Tests
# ==============================================================================

class TestRainfallRollingWindows:
    """Test calculation of 1d, 3d, 7d, 14d, 30d backwards-looking rolling rainfall windows."""

    def test_constant_rainfall_rolling_sums(self, mock_spatial_service: SpatialEnrichmentService):
        """Constant 2.0 mm/day rainfall produces exact multiples for all rolling windows."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)
        records = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=2.0,
            )
            for i in range(40)
        ]

        features = generator.generate_features(records)
        assert len(features) == 40

        # Day 0 (Jan 1): only 1d is available
        assert features[0].rainfall_1d == pytest.approx(2.0)
        assert features[0].rainfall_3d is None
        assert features[0].rainfall_7d is None
        assert features[0].rainfall_14d is None
        assert features[0].rainfall_30d is None

        # Day 2 (Jan 3): 1d and 3d available
        assert features[2].rainfall_1d == pytest.approx(2.0)
        assert features[2].rainfall_3d == pytest.approx(6.0)  # 3 * 2.0
        assert features[2].rainfall_7d is None

        # Day 6 (Jan 7): 7d available
        assert features[6].rainfall_7d == pytest.approx(14.0)  # 7 * 2.0
        assert features[6].rainfall_14d is None

        # Day 13 (Jan 14): 14d available
        assert features[13].rainfall_14d == pytest.approx(28.0)  # 14 * 2.0
        assert features[13].rainfall_30d is None

        # Day 29 (Jan 30): 30d available
        assert features[29].rainfall_30d == pytest.approx(60.0)  # 30 * 2.0
        assert features[29].window_30d_valid_days == 30
        assert features[29].is_complete is True

    def test_variable_rainfall_sum_accuracy(self, mock_spatial_service: SpatialEnrichmentService):
        """Variable rainfall sequence sums match exact mathematical expectations."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)
        # Daily precip = day index + 1 (1.0, 2.0, 3.0, ..., 35.0)
        records = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=float(i + 1),
            )
            for i in range(35)
        ]

        features = generator.generate_features(records)

        # On day index 2 (day 3: values 1, 2, 3)
        assert features[2].rainfall_3d == pytest.approx(1.0 + 2.0 + 3.0)  # 6.0

        # On day index 6 (values 1..7)
        assert features[6].rainfall_7d == pytest.approx(sum(range(1, 8)))  # 28.0

        # On day index 29 (values 1..30)
        assert features[29].rainfall_30d == pytest.approx(sum(range(1, 31)))  # 465.0


# ==============================================================================
# 2. Date Ordering Tests
# ==============================================================================

class TestDateOrdering:
    """Test that records provided out-of-order are sorted chronologically and features computed correctly."""

    def test_shuffled_records_sorted_chronologically(self, mock_spatial_service: SpatialEnrichmentService):
        """Shuffled input daily records produce identical chronologically ordered output."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)
        ordered_records = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=float(i + 1),
            )
            for i in range(35)
        ]

        # Reverse records
        reversed_records = list(reversed(ordered_records))
        features_from_reversed = generator.generate_features(reversed_records)
        features_from_ordered = generator.generate_features(ordered_records)

        # Output must be strictly chronological
        for i in range(len(features_from_reversed) - 1):
            assert features_from_reversed[i].date < features_from_reversed[i + 1].date

        # Outputs must match exactly
        assert [f.rainfall_3d for f in features_from_reversed] == [f.rainfall_3d for f in features_from_ordered]
        assert [f.rainfall_30d for f in features_from_reversed] == [f.rainfall_30d for f in features_from_ordered]


# ==============================================================================
# 3. No Temporal Leakage Tests
# ==============================================================================

class TestNoTemporalLeakage:
    """Test strict prevention of future information entering past feature rows."""

    def test_future_observations_do_not_affect_past_features(self, mock_spatial_service: SpatialEnrichmentService):
        """Future observations (e.g. tomorrow's rain) have zero effect on today's feature values."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)

        # Scenario A: Normal 30 days of 1.0 mm
        records_a = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=1.0,
            )
            for i in range(30)
        ]
        features_a = generator.generate_features(records_a)

        # Scenario B: Days 0..14 identical (1.0 mm), but Day 15 has 500.0 mm catastrophic rain
        records_b = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=500.0 if i >= 15 else 1.0,
            )
            for i in range(30)
        ]
        features_b = generator.generate_features(records_b)

        # For days 0 to 14: Features MUST be 100% identical between Scenario A and B
        for day_idx in range(15):
            rec_a = features_a[day_idx]
            rec_b = features_b[day_idx]
            assert rec_a.date == rec_b.date
            assert rec_a.rainfall_1d == rec_b.rainfall_1d
            assert rec_a.rainfall_3d == rec_b.rainfall_3d
            assert rec_a.rainfall_7d == rec_b.rainfall_7d
            assert rec_a.rainfall_14d == rec_b.rainfall_14d

        # On Day 15: rainfall_1d reflects the 500mm event, but prior days did not leak
        assert features_b[15].rainfall_1d == 500.0
        assert features_a[15].rainfall_1d == 1.0


# ==============================================================================
# 4. Cell Identity and Provenance Preservation Tests
# ==============================================================================

class TestCellIdentityAndProvenance:
    """Test preservation of spatial identity and chunk provenance."""

    def test_cell_identity_and_provenance_preserved(self, mock_spatial_service: SpatialEnrichmentService):
        """cell_id, chunk_id, raw_chunk_id, and raw_payload_sha256 strictly preserved."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        expected_sha = "f" * 64
        expected_chunk = "era5_1975_batch_005"
        rec = make_daily_record(
            date_str="1975-06-15",
            cell_id="ERA5_1425_07650",
            chunk_id=expected_chunk,
            raw_sha=expected_sha,
        )

        features = generator.generate_features([rec])
        assert len(features) == 1
        f = features[0]

        assert f.cell_id == "ERA5_1425_07650"
        assert f.latitude == 14.25
        assert f.longitude == 76.5
        assert f.chunk_id == expected_chunk
        assert f.raw_chunk_id == expected_chunk
        assert f.raw_payload_sha256 == expected_sha
        assert f.basin_name == "Krishna"
        assert f.district_name == "Chitradurga"


# ==============================================================================
# 5. Missing-Day Behaviour Tests (Zero Silent Zero-Filling)
# ==============================================================================

class TestMissingDayBehaviour:
    """Test that missing calendar days explicitly cause affected rolling windows to evaluate to None/NaN."""

    def test_missing_day_invalidates_encompassing_rolling_windows(self, mock_spatial_service: SpatialEnrichmentService):
        """If Day 10 is missing, Day 11's 3d window is None and NOT silently computed as sum of 2 days."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)

        # Create 40 days, but completely omit day index 10 (Jan 11)
        records = []
        for i in range(40):
            if i == 10:
                continue  # Omit Day 10
            records.append(
                make_daily_record(
                    date_str=(start_date + timedelta(days=i)).isoformat(),
                    precip=2.0,
                )
            )

        features = generator.generate_features(records)
        feat_by_date = {f.date: f for f in features}

        # Day 9 (Jan 10): unaffected
        d9 = (start_date + timedelta(days=9)).isoformat()
        assert feat_by_date[d9].rainfall_1d == 2.0
        assert feat_by_date[d9].rainfall_3d == 6.0

        # Day 10 (Jan 11): was omitted, so no row exists for it
        d10 = (start_date + timedelta(days=10)).isoformat()
        assert d10 not in feat_by_date

        # Day 11 (Jan 12): 1d is valid (2.0), but 3d (needs Days 9, 10, 11) MUST BE None
        d11 = (start_date + timedelta(days=11)).isoformat()
        assert feat_by_date[d11].rainfall_1d == 2.0
        assert feat_by_date[d11].rainfall_3d is None  # CRITICAL: not 4.0!
        assert feat_by_date[d11].rainfall_7d is None
        assert feat_by_date[d11].rainfall_14d is None
        assert feat_by_date[d11].rainfall_30d is None

        # Day 12 (Jan 13): 3d (needs Days 10, 11, 12) still encompasses missing Day 10 -> None
        d12 = (start_date + timedelta(days=12)).isoformat()
        assert feat_by_date[d12].rainfall_3d is None

        # Day 13 (Jan 14): 3d (needs Days 11, 12, 13) has all 3 days present -> 6.0
        d13 = (start_date + timedelta(days=13)).isoformat()
        assert feat_by_date[d13].rainfall_3d == pytest.approx(6.0)
        # But 7d (needs Days 7..13, contains Day 10) is still None
        assert feat_by_date[d13].rainfall_7d is None

        # Day 40 (Feb 10, index 39): 30-day window covers [index 10..39], encompasses Day 10 -> None
        d39 = (start_date + timedelta(days=39)).isoformat()
        assert feat_by_date[d39].rainfall_30d is None
        assert feat_by_date[d39].window_30d_valid_days == 29  # Exactly 29 valid days


# ==============================================================================
# 6. Partial-Day Behaviour Tests (hour_count < 24 / INCOMPLETE)
# ==============================================================================

class TestPartialDayBehaviour:
    """Test that incomplete days (hour_count < 24) are not silently treated as complete or zero."""

    def test_incomplete_day_invalidates_rolling_windows_and_weather(self, mock_spatial_service: SpatialEnrichmentService):
        """Incomplete day has rainfall_1d=None and invalidates rolling windows."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)

        records = []
        for i in range(35):
            if i == 5:
                # Incomplete day (e.g. only 18 hours recorded)
                records.append(
                    make_daily_record(
                        date_str=(start_date + timedelta(days=i)).isoformat(),
                        precip=1.5,
                        hour_count=18,
                        quality_status=DailyQualityStatus.INCOMPLETE.value,
                    )
                )
            else:
                records.append(
                    make_daily_record(
                        date_str=(start_date + timedelta(days=i)).isoformat(),
                        precip=2.0,
                    )
                )

        features = generator.generate_features(records)
        feat_by_date = {f.date: f for f in features}

        d5 = (start_date + timedelta(days=5)).isoformat()
        f5 = feat_by_date[d5]

        # Day 5 itself is incomplete
        assert f5.hour_count == 18
        assert f5.quality_status == DailyQualityStatus.INCOMPLETE.value
        assert f5.rainfall_1d is None
        assert f5.rainfall_3d is None
        assert f5.temperature_mean_c is None
        assert f5.relative_humidity_mean_pct is None
        assert f5.is_complete is False

        # Day 6 (index 6): 3d window encompasses incomplete Day 5 -> None
        d6 = (start_date + timedelta(days=6)).isoformat()
        assert feat_by_date[d6].rainfall_1d == 2.0
        assert feat_by_date[d6].rainfall_3d is None


# ==============================================================================
# 7. Deterministic Output Tests
# ==============================================================================

class TestDeterministicOutput:
    """Test byte-level and semantic reproducibility of feature generation."""

    def test_reproducible_feature_generation(self, mock_spatial_service: SpatialEnrichmentService):
        """Running feature generation twice on identical input yields identical output."""
        generator = FeatureGenerator(spatial_service=mock_spatial_service)
        start_date = dt_date(1970, 1, 1)
        records = [
            make_daily_record(
                date_str=(start_date + timedelta(days=i)).isoformat(),
                precip=float(i % 5),
            )
            for i in range(35)
        ]

        run1 = generator.generate_features(records)
        run2 = generator.generate_features(records)

        assert len(run1) == len(run2)
        assert [r.to_dict() for r in run1] == [r.to_dict() for r in run2]


# ==============================================================================
# 8. Real ERA5 Artifact Processing (End-to-End)
# ==============================================================================

class TestRealERA5ArtifactProcessing:
    """End-to-end integration tests using real extracted ERA5 Parquet chunks and real GIS layers."""

    def test_real_1969_batch_1_feature_generation(self):
        """Process real 1969 batch 1 daily records into validated ML features."""
        pipeline = MLFeaturePipeline()
        res = pipeline.process_chunk(year=1969, batch_id=1)

        assert res.is_valid is True
        assert res.record_count == 3650
        assert res.complete_samples_count == 3360  # 365 - 29 = 336 days * 10 cells
        assert res.missing_30d_rainfall_count == 290  # 29 days * 10 cells
        assert res.errors == []

        # Verify Parquet file was written
        out_path = Path(res.output_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 0

        # Read back written Parquet
        table = pq.read_table(str(out_path))
        assert table.num_rows == 3650
        assert table.schema.names == ARROW_FEATURE_SCHEMA.names

        # Validate that real terrain and hydrological attributes are populated
        df = table.to_pandas()
        assert df["elevation"].notna().all()
        assert (df["elevation"] > 0).all()
        assert df["slope"].notna().all()
        assert (df["slope"] >= 0).all()
        assert df["basin_name"].notna().all()
        assert df["distance_to_river_m"].notna().all()
        assert (df["distance_to_river_m"] >= 0).all()

    def test_idempotent_cached_skip(self):
        """Second execution of already processed chunk skips instantly with cached result."""
        pipeline = MLFeaturePipeline()
        res = pipeline.process_chunk(year=1969, batch_id=1)
        assert res.is_valid is True
        assert len(res.warnings) > 0
        assert "cached" in res.warnings[0].lower()

    def test_cross_year_lookback_continuity(self):
        """Year 1970 batch 1 loads lookback records from 1969 batch 1, achieving 100% complete samples."""
        pipeline = MLFeaturePipeline()
        res = pipeline.process_chunk(year=1970, batch_id=1)

        assert res.is_valid is True
        assert res.record_count == 3650
        assert res.complete_samples_count == 3650  # 100% complete due to lookback!
        assert res.missing_30d_rainfall_count == 0


# ==============================================================================
# 9. Schema Invariants and Quality Validation Tests
# ==============================================================================

class TestFeatureQualityValidator:
    """Test validation of physical constraints and integrity checks."""

    def test_physical_validation_rejections(self, mock_spatial_service: SpatialEnrichmentService):
        """Reject unphysical or inconsistent feature records."""
        rec = MLFeatureRecord(
            date="1970-01-01",
            cell_id="ERA5_1425_07650",
            chunk_id="test",
            latitude=14.25,
            longitude=76.5,
            rainfall_1d=10.0,
            rainfall_3d=5.0,  # INCONSISTENT: 1d > 3d
            rainfall_7d=15.0,
            rainfall_14d=20.0,
            rainfall_30d=25.0,
            temperature_mean_c=25.0,
            temperature_min_c=30.0,  # INCONSISTENT: min > mean
            temperature_max_c=35.0,
            relative_humidity_mean_pct=150.0,  # OUT OF BOUNDS: > 100
            surface_pressure_mean_hpa=950.0,
            elevation=650.0,
            slope=3.5,
            raw_chunk_id="test",
            raw_payload_sha256="bad_sha",  # NOT 64 chars
        )

        errors = FeatureQualityValidator.validate_record(rec)
        assert any("1d rainfall (10.0) exceeds 3d rainfall (5.0)" in e for e in errors)
        assert any("Inconsistent temperature hierarchy" in e for e in errors)
        assert any("relative_humidity_mean_pct (150.0) out of [0, 100]" in e for e in errors)
        assert any("raw_payload_sha256 must be a 64-character" in e for e in errors)


# ==============================================================================
# 10. Real Data Mathematical Precision and Spatial Audit Tests
# ==============================================================================

class TestRealDataMathematicalPrecisionAndIntegrity:
    """Rigorous mathematical and structural audits on real generated ML feature Parquet files."""

    def test_real_data_rolling_sum_exactness(self):
        """Verify that rolling windows on real data match exact arithmetic sums across time."""
        file_path = Path("data/processed/ml_features/year=1972/batch_018.parquet")
        if not file_path.exists():
            file_path = Path("../data/processed/ml_features/year=1972/batch_018.parquet")
        assert file_path.exists(), f"Target real parquet missing: {file_path}"

        table = pq.read_table(str(file_path))
        df = table.to_pandas()

        # Test first cell across all 366 days of 1972
        sample_cell = df["cell_id"].iloc[0]
        cell_df = df[df["cell_id"] == sample_cell].sort_values("date").reset_index(drop=True)
        assert len(cell_df) == 366

        precip_series = cell_df["rainfall_1d"].to_numpy()
        r3_series = cell_df["rainfall_3d"].to_numpy()
        r7_series = cell_df["rainfall_7d"].to_numpy()
        r14_series = cell_df["rainfall_14d"].to_numpy()
        r30_series = cell_df["rainfall_30d"].to_numpy()

        for idx in range(30, 366):
            expected_3d = np.sum(precip_series[idx - 2 : idx + 1])
            expected_7d = np.sum(precip_series[idx - 6 : idx + 1])
            expected_14d = np.sum(precip_series[idx - 13 : idx + 1])
            expected_30d = np.sum(precip_series[idx - 29 : idx + 1])

            assert r3_series[idx] == pytest.approx(expected_3d, abs=1e-3)
            assert r7_series[idx] == pytest.approx(expected_7d, abs=1e-3)
            assert r14_series[idx] == pytest.approx(expected_14d, abs=1e-3)
            assert r30_series[idx] == pytest.approx(expected_30d, abs=1e-3)

    def test_real_spatial_cache_completeness(self):
        """Verify that all 318 cells in spatial cache have non-null terrain and hydrological attributes."""
        cache_path = Path("data/processed/gis_cache/cell_spatial_features.json")
        if not cache_path.exists():
            cache_path = Path("../data/processed/gis_cache/cell_spatial_features.json")
        assert cache_path.exists(), f"Spatial cache missing: {cache_path}"

        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 318, f"Expected 318 grid cells, got {len(data)}"

        for cell_id, attrs in data.items():
            assert attrs["elevation_mean"] is not None and attrs["elevation_mean"] > 0
            assert attrs["slope_mean"] is not None and attrs["slope_mean"] >= 0
            assert attrs["basin_name"] is not None and len(attrs["basin_name"]) > 0
            assert attrs["district_name"] is not None and len(attrs["district_name"]) > 0
            assert attrs["distance_to_river_m"] is not None and attrs["distance_to_river_m"] >= 0
            assert attrs["nearest_river_id"] is not None and len(attrs["nearest_river_id"]) > 0

    def test_parquet_metadata_contracts(self):
        """Verify that output Parquet metadata encodes scientific provenance flags."""
        file_path = Path("data/processed/ml_features/year=1972/batch_018.parquet")
        if not file_path.exists():
            file_path = Path("../data/processed/ml_features/year=1972/batch_018.parquet")
        assert file_path.exists(), f"Target real parquet missing: {file_path}"

        schema = pq.read_schema(str(file_path))
        meta = schema.metadata
        assert b"zero_synthetic_data" in meta
        assert meta[b"zero_synthetic_data"] == b"true"
        assert b"temporal_leakage_prevented" in meta
        assert meta[b"temporal_leakage_prevented"] == b"true"

