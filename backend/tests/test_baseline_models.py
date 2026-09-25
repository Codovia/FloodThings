"""
Focused tests for Baseline ML Modeling and PU Evaluation (Phase 5).

Covers all verification areas required by project specifications:
1. Chronological splitting.
2. No train/validation/test temporal overlap.
3. UNKNOWN is never silently converted to NO_FLOOD.
4. Preprocessing is fitted ONLY on training data (zero future leakage).
5. Target leakage prevention (prohibited columns strictly excluded).
6. Deterministic feature ordering.
7. Model serialization and loading round-trip.
8. Prediction schema (probabilities in [0, 1], predictions in {0, 1}).
9. Evaluation metric calculations (PR-AUC, ROC-AUC, PU ranking score).
"""

from __future__ import annotations

from datetime import date as dt_date, timedelta
import math
from pathlib import Path
import tempfile
import uuid

import numpy as np
import pandas as pd
import pytest

from app.ml.baseline_modeling import (
    CANONICAL_PREDICTOR_COLUMNS,
    DatasetAuditor,
    EvaluationMetrics,
    LightGBMBaseline,
    LogisticRegressionBaseline,
    ModelArtifactManager,
    ModelMetadata,
    ModelType,
    PUDatasetPreparer,
    PUEvaluator,
    PUStrategy,
    TemporalDataSplitter,
    TemporalSplit,
)


@pytest.fixture
def synthetic_district_df() -> pd.DataFrame:
    """Generate a small synthetic District x Day dataset for testing unit invariants."""
    rows = []
    dates = [
        # 1972 (Train)
        ("1972-07-01", 1972, 7, 1, 183),
        ("1972-07-02", 1972, 7, 2, 184),
        ("1972-07-03", 1972, 7, 3, 185),
        ("1972-01-15", 1972, 1, 15, 15),  # dry day
        # 1974 (Validation)
        ("1974-08-10", 1974, 8, 10, 222),
        ("1974-08-11", 1974, 8, 11, 223),
        # 1975 (Test)
        ("1975-09-05", 1975, 9, 5, 248),
        ("1975-09-06", 1975, 9, 6, 249),
    ]

    for d_idx, dist_name in enumerate(["Bagalkote", "Belagavi"]):
        d_id = f"dist-{d_idx}"
        for t_date, yr, mo, da, doy in dates:
            # Positive flood only on 1972-07-02 and 1974-08-10
            is_flood = (t_date in ("1972-07-02", "1974-08-10", "1975-09-05"))
            rows.append({
                "district_id": d_id,
                "kgis_district_code": f"0{d_idx+1}",
                "lgd_district_code": f"52{d_idx+4}",
                "district_name": dist_name,
                "target_date": t_date,
                "target_year": yr,
                "target_month": mo,
                "target_day": da,
                "day_of_year": doy,
                "prediction_anchor_utc": f"{t_date}T00:00:00Z",
                "lead_time_days": 1,
                "feature_window_start": (dt_date.fromisoformat(t_date) - timedelta(days=30)).isoformat(),
                "feature_window_end": (dt_date.fromisoformat(t_date) - timedelta(days=1)).isoformat(),
                "flood_occurrence": 1 if is_flood else None,
                "label_state": "FLOOD" if is_flood else "UNKNOWN",
                "event_count": 1 if is_flood else None,
                "source_event_ids": ["UEI-TEST-001"] if is_flood else [],
                "main_causes": ["floods"] if is_flood else [],
                "severities": ["MODERATE"] if is_flood else [],
                "fatalities": None,
                "displaced": None,
                # Dynamic weather
                "precip_1d_mm": 50.0 if is_flood else (0.0 if mo == 1 else 5.0),
                "precip_3d_sum_mm": 100.0 if is_flood else (0.0 if mo == 1 else 10.0),
                "precip_7d_sum_mm": 150.0 if is_flood else (0.0 if mo == 1 else 20.0),
                "precip_14d_sum_mm": 200.0 if is_flood else (0.0 if mo == 1 else 30.0),
                "precip_30d_sum_mm": 300.0 if is_flood else (0.5 if mo == 1 else 50.0),
                "precip_7d_max_mm": 60.0 if is_flood else (0.0 if mo == 1 else 8.0),
                "precip_14d_max_mm": 70.0 if is_flood else (0.0 if mo == 1 else 10.0),
                "temp_mean_1d_c": 24.0,
                "temp_min_1d_c": 20.0,
                "temp_max_1d_c": 30.0,
                "temp_7d_mean_c": 24.5,
                "rh_mean_1d_pct": 85.0 if is_flood else (40.0 if mo == 1 else 60.0),
                "rh_7d_mean_pct": 82.0 if is_flood else (42.0 if mo == 1 else 62.0),
                "pressure_mean_1d_hpa": 940.0,
                "is_weather_complete_1d": True,
                "is_weather_complete_30d": True,
                "valid_weather_days_30d": 30,
                "weather_cell_count": 10,
                "elevation_mean_m": 550.0,
                "elevation_min_m": 480.0,
                "elevation_max_m": 700.0,
                "elevation_std_m": 35.0,
                "slope_mean_deg": 2.5,
                "slope_max_deg": 40.0,
                "terrain_coverage_pct": 100.0,
                "major_basin_count": 1,
                "primary_basin_coverage_pct": 100.0,
                "sub_basin_count": 8,
                "mean_upstream_area_km2": 15000.0,
            })
    return pd.DataFrame(rows)


class TestBaselineModels:
    """Test suite for Phase 5 ML modeling, temporal splits, and PU learning."""

    def test_01_chronological_splitting(self, synthetic_district_df: pd.DataFrame):
        """1. Chronological splitting: Train, validation, and test splits follow strict temporal boundaries."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        assert split.train_years == (1972,)
        assert split.val_years == (1974,)
        assert split.test_years == (1975,)

        # Invariant: train dates strictly before validation dates
        assert split.train_dates[1] < split.val_dates[0]
        # Invariant: validation dates strictly before test dates
        assert split.val_dates[1] < split.test_dates[0]

    def test_02_no_train_val_temporal_overlap(self):
        """2. No temporal overlap: Overlapping split configurations raise ValueError."""
        # Train ends 1974, but val also 1974 -> overlapping dates
        mock_df = pd.DataFrame({
            "target_year": [1974, 1974, 1975],
            "target_date": ["1974-06-01", "1974-08-01", "1975-01-01"],
        })
        splitter = TemporalDataSplitter(train_end_year=1974, val_year=1974, test_year=1975)
        with pytest.raises(ValueError, match="must precede Val start"):
            splitter.split(mock_df)

    def test_03_unknown_is_never_converted_to_no_flood(self, synthetic_district_df: pd.DataFrame):
        """3. UNKNOWN is never silently converted to NO_FLOOD in the raw dataset."""
        unknown_rows = synthetic_district_df[synthetic_district_df["label_state"] == "UNKNOWN"]
        assert len(unknown_rows) > 0
        # In the source dataset, unknown rows must have flood_occurrence is None
        assert unknown_rows["flood_occurrence"].isna().all()

    def test_04_preprocessing_fitted_only_on_training_data(self, synthetic_district_df: pd.DataFrame):
        """4. Preprocessing is fitted ONLY on training data: Scaler means match X_train, never test data."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm"]
        X_tr = synthetic_district_df.loc[split.train_mask, feature_cols].to_numpy()
        y_tr = (synthetic_district_df.loc[split.train_mask, "label_state"] == "FLOOD").to_numpy().astype(int)

        model = LogisticRegressionBaseline(feature_cols=feature_cols)
        model.fit(X_tr, y_tr)

        expected_mean = np.mean(X_tr, axis=0)
        assert np.allclose(model.scaler.mean_, expected_mean)

    def test_05_target_leakage_prevention(self):
        """5. Target leakage prevention: prohibited disaster impact columns are not in CANONICAL_PREDICTOR_COLUMNS."""
        for col in [
            "flood_occurrence",
            "label_state",
            "event_count",
            "source_event_ids",
            "fatalities",
            "displaced",
            "target_date",
            "prediction_anchor_utc",
        ]:
            assert col not in CANONICAL_PREDICTOR_COLUMNS

    def test_06_deterministic_feature_ordering(self):
        """6. Deterministic feature ordering: predictor list is fixed, immutable order."""
        cols1 = list(CANONICAL_PREDICTOR_COLUMNS)
        cols2 = list(CANONICAL_PREDICTOR_COLUMNS)
        assert cols1 == cols2
        assert len(cols1) == 27

    def test_07_model_serialization_round_trip(self, synthetic_district_df: pd.DataFrame):
        """7. Model serialization: Saved model loads cleanly and produces identical predictions."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm", "temp_mean_1d_c"]
        X_tr = synthetic_district_df.loc[split.train_mask, feature_cols].to_numpy()
        y_tr = (synthetic_district_df.loc[split.train_mask, "label_state"] == "FLOOD").to_numpy().astype(int)

        model = LogisticRegressionBaseline(feature_cols=feature_cols)
        model.fit(X_tr, y_tr)

        X_test = synthetic_district_df.loc[split.test_mask, feature_cols].to_numpy()
        preds_orig = model.predict_proba(X_test)

        with tempfile.TemporaryDirectory() as tmp_dir:
            mgr = ModelArtifactManager(base_dir=tmp_dir)
            meta = ModelMetadata(
                model_id=str(uuid.uuid4()),
                model_type=ModelType.LOGISTIC_REGRESSION,
                pu_strategy=PUStrategy.STANDARD_PU,
                model_version="1.0.0",
                created_at_utc="2026-09-25T00:00:00Z",
                feature_version="1.0.0",
                features_used=feature_cols,
                train_dates=split.train_dates,
                val_dates=split.val_dates,
                test_dates=split.test_dates,
                train_rows=len(X_tr),
                val_rows=0,
                test_rows=len(X_test),
                train_positives=int(y_tr.sum()),
                val_positives=0,
                test_positives=0,
                hyperparameters={"C": 1.0},
                validation_metrics=EvaluationMetrics(
                    split_name="validation", total_samples=0, positive_samples=0,
                    unlabeled_samples=0, positive_prevalence=0.0, roc_auc=0.5,
                    pr_auc=0.0, brier_score=0.0, decision_threshold=0.5,
                    precision_at_threshold=0.0, recall_at_threshold=0.0,
                    f1_at_threshold=0.0, pu_ranking_criterion=0.0, confusion_matrix_raw=[[0]]
                ),
                test_metrics=EvaluationMetrics(
                    split_name="test", total_samples=len(X_test), positive_samples=0,
                    unlabeled_samples=len(X_test), positive_prevalence=0.0, roc_auc=0.5,
                    pr_auc=0.0, brier_score=0.0, decision_threshold=0.5,
                    precision_at_threshold=0.0, recall_at_threshold=0.0,
                    f1_at_threshold=0.0, pu_ranking_criterion=0.0, confusion_matrix_raw=[[0]]
                ),
                source_parquet_sha256="dummy_sha256",
            )
            m_path, _ = mgr.save_model(model, meta)
            loaded_model, _ = mgr.load_model(m_path)

            preds_loaded = loaded_model.predict_proba(X_test)
            assert np.allclose(preds_orig, preds_loaded)

    def test_08_prediction_schema(self, synthetic_district_df: pd.DataFrame):
        """8. Prediction schema: predict_proba returns floats in [0, 1]."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm", "elevation_mean_m"]
        X_tr = synthetic_district_df.loc[split.train_mask, feature_cols].to_numpy()
        y_tr = (synthetic_district_df.loc[split.train_mask, "label_state"] == "FLOOD").to_numpy().astype(int)

        model = LogisticRegressionBaseline(feature_cols=feature_cols)
        model.fit(X_tr, y_tr)

        X_val = synthetic_district_df.loc[split.val_mask, feature_cols].to_numpy()
        probs = model.predict_proba(X_val)

        assert isinstance(probs, np.ndarray)
        assert len(probs) == len(X_val)
        assert np.all(probs >= 0.0)
        assert np.all(probs <= 1.0)

    def test_09_evaluation_metric_calculations(self):
        """9. Evaluation metrics: PR-AUC, ROC-AUC, Brier score, and PU ranking metric calculations."""
        y_true = np.array([1, 1, 0, 0, 0])
        y_prob = np.array([0.9, 0.8, 0.2, 0.1, 0.3])

        metrics = PUEvaluator.evaluate(y_true, y_prob, split_name="test", fixed_threshold=0.5)

        assert metrics.total_samples == 5
        assert metrics.positive_samples == 2
        assert metrics.unlabeled_samples == 3
        assert metrics.roc_auc == 1.0  # Perfect ranking
        assert metrics.pr_auc == 1.0
        assert metrics.precision_at_threshold == 1.0
        assert metrics.recall_at_threshold == 1.0
        assert metrics.f1_at_threshold == 1.0
        assert metrics.brier_score < 0.1
        # PU criterion = recall^2 / P(Y_hat=1) = 1.0 / (2/5) = 2.5
        assert abs(metrics.pu_ranking_criterion - 2.5) < 0.1

    def test_10_high_confidence_negatives_selection(self, synthetic_district_df: pd.DataFrame):
        """10. High-confidence negatives selection: filters dry season zero-rainfall background samples."""
        train_mask = (synthetic_district_df["target_year"] <= 1972).to_numpy()
        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm"]

        X, y, _ = PUDatasetPreparer.prepare_training_data(
            df=synthetic_district_df,
            train_mask=train_mask,
            feature_cols=feature_cols,
            strategy=PUStrategy.HIGH_CONFIDENCE_NEGATIVES,
        )

        assert len(X) > 0
        assert len(y) == len(X)
        # Positives must be in y
        assert (y == 1).sum() > 0
        # Negatives must be in y
        assert (y == 0).sum() > 0

    def test_11_lightgbm_baseline_training(self, synthetic_district_df: pd.DataFrame):
        """11. LightGBM baseline: fits successfully and provides feature importances."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm", "temp_mean_1d_c"]
        X_tr = synthetic_district_df.loc[split.train_mask, feature_cols].to_numpy()
        y_tr = (synthetic_district_df.loc[split.train_mask, "label_state"] == "FLOOD").to_numpy().astype(int)

        lgb = LightGBMBaseline(feature_cols=feature_cols, n_estimators=10)
        lgb.fit(X_tr, y_tr)

        X_val = synthetic_district_df.loc[split.val_mask, feature_cols].to_numpy()
        probs = lgb.predict_proba(X_val)
        assert len(probs) == len(X_val)

        importances = lgb.get_feature_importances()
        assert set(importances.keys()) == set(feature_cols)

    def test_12_dataset_auditor_machine_readable_output(self, synthetic_district_df: pd.DataFrame):
        """12. Dataset auditor: verifies dtypes, missingness, inf counts, and machine-readable JSON export."""
        audit = DatasetAuditor.audit(synthetic_district_df)
        assert audit["total_rows"] == len(synthetic_district_df)
        assert "feature_dtypes" in audit
        assert "feature_infs" in audit
        assert audit["data_quality"]["total_infs_in_predictors"] == 0
        assert audit["data_quality"]["total_missing_in_predictors"] == 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "audit_test.json"
            saved_path = DatasetAuditor.save_audit_report(audit, out_file)
            assert saved_path.exists()
            assert saved_path.stat().st_size > 0

    def test_13_lightgbm_bagging_pu(self, synthetic_district_df: pd.DataFrame):
        """13. LightGBM with Bagging PU: fits ensemble across bootstrap subsamples."""
        splitter = TemporalDataSplitter(train_end_year=1972, val_year=1974, test_year=1975)
        split = splitter.split(synthetic_district_df)

        feature_cols = ["precip_1d_mm", "precip_3d_sum_mm"]
        X_tr = synthetic_district_df.loc[split.train_mask, feature_cols].to_numpy()
        y_tr = (synthetic_district_df.loc[split.train_mask, "label_state"] == "FLOOD").to_numpy().astype(int)

        lgb = LightGBMBaseline(
            pu_strategy=PUStrategy.BAGGING_PU,
            feature_cols=feature_cols,
            n_estimators=5,
            bagging_n_estimators=3,
            bagging_ratio=2,
        )
        lgb.fit(X_tr, y_tr)
        assert len(lgb.ensemble_models_) == 3

        X_val = synthetic_district_df.loc[split.val_mask, feature_cols].to_numpy()
        probs = lgb.predict_proba(X_val)
        assert len(probs) == len(X_val)
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)

        importances = lgb.get_feature_importances()
        assert set(importances.keys()) == set(feature_cols)

    def test_14_metadata_pu_assumptions_and_semantics(self, synthetic_district_df: pd.DataFrame):
        """14. ModelMetadata: records target semantics, PU assumptions, and version lineage."""
        meta = ModelMetadata(
            model_id=str(uuid.uuid4()),
            model_type=ModelType.LOGISTIC_REGRESSION,
            pu_strategy=PUStrategy.HIGH_CONFIDENCE_NEGATIVES,
            model_version="1.0.0",
            created_at_utc="2026-09-25T00:00:00Z",
            feature_version="1.0.0",
            features_used=["precip_1d_mm"],
            train_dates=("1972-01-15", "1972-07-03"),
            val_dates=("1974-08-10", "1974-08-11"),
            test_dates=("1975-09-05", "1975-09-06"),
            train_rows=8,
            val_rows=4,
            test_rows=4,
            train_positives=2,
            val_positives=2,
            test_positives=2,
            hyperparameters={"C": 1.0},
            validation_metrics=EvaluationMetrics(
                split_name="validation", total_samples=4, positive_samples=2,
                unlabeled_samples=2, positive_prevalence=0.5, roc_auc=1.0,
                pr_auc=1.0, brier_score=0.1, decision_threshold=0.5,
                precision_at_threshold=1.0, recall_at_threshold=1.0,
                f1_at_threshold=1.0, pu_ranking_criterion=2.0, confusion_matrix_raw=[[2, 0], [0, 2]],
                elkan_noto_c=0.85,
            ),
            test_metrics=EvaluationMetrics(
                split_name="test", total_samples=4, positive_samples=2,
                unlabeled_samples=2, positive_prevalence=0.5, roc_auc=1.0,
                pr_auc=1.0, brier_score=0.1, decision_threshold=0.5,
                precision_at_threshold=1.0, recall_at_threshold=1.0,
                f1_at_threshold=1.0, pu_ranking_criterion=2.0, confusion_matrix_raw=[[2, 0], [0, 2]],
                elkan_noto_c=0.82,
            ),
            source_parquet_sha256="dummy_hash",
            target_semantics={"FLOOD": "Positive", "NO_FLOOD": "Negative", "UNKNOWN": "Unlabeled"},
            pu_assumptions={"strategy": "HIGH_CONFIDENCE_NEGATIVES", "description": "Dry baseline"},
        )
        meta_dict = meta.to_dict()
        assert meta_dict["target_semantics"]["FLOOD"] == "Positive"
        assert meta_dict["pu_assumptions"]["strategy"] == "HIGH_CONFIDENCE_NEGATIVES"
        assert meta_dict["validation_metrics"]["elkan_noto_c"] == 0.85

    def test_15_elkan_noto_c_calculation(self):
        """15. Elkan-Noto c parameter: verifies mean probability on positive observations."""
        y_true = np.array([1, 1, 0, 0])
        y_prob = np.array([0.8, 0.6, 0.1, 0.2])
        metrics = PUEvaluator.evaluate(y_true, y_prob, split_name="test")
        # c = mean(0.8, 0.6) = 0.7
        assert abs(metrics.elkan_noto_c - 0.7) < 1e-4
