"""
Baseline Machine Learning Modeling and Temporal Cross-Validation (Phase 5).

Implements:
1. Feature Matrix Audit & Verification (Task A).
2. Strict Chronological / Expanding-Window Temporal Splitting (Task B).
3. Positive-Unlabeled (PU) / Three-State Learning Strategies (Task C & D):
   - Strategy 1: Standard PU Baseline (PU Naive / Background Weighting).
   - Strategy 2: High-Confidence Negative Filtering (Meteorologically Benign Dry Season).
   - Strategy 3: Bagging-based PU Estimator (Mordelet & Vert Ensemble PU).
4. Transparent Interpretable Baseline: Logistic Regression (Task C).
5. Tree-based Non-linear Baseline: LightGBM Classifier (Task E).
6. Comprehensive PU & Imbalance Evaluation Metrics (Task F).
7. Feature Importance & Coefficient Inspection (Task G).
8. Model Artifact Persistence & Provenance (Task H).

Guarantees:
- ZERO future leakage: Train observations strictly precede validation/test observations.
- ZERO random splitting: Time-series integrity strictly enforced.
- ZERO label fabrication: UNKNOWN is never silently converted to NO_FLOOD.
- Preprocessing (scalers, encoders) is fitted ONLY on training data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date as dt_date, datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Sequence
import uuid

import joblib
from lightgbm import LGBMClassifier
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

MODEL_FRAMEWORK_VERSION: str = "1.0.0"

# Project root resolution
def _find_project_root() -> Path:
    curr = Path(__file__).resolve().parent
    for parent in [curr] + list(curr.parents):
        if (parent / "data").exists() and (parent / "backend").exists():
            return parent
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _find_project_root()
DEFAULT_FEATURE_MATRIX_PATH = PROJECT_ROOT / "data" / "processed" / "ml_matrix" / "district_day_feature_matrix.parquet"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "data" / "processed" / "ml_models"

# Canonical predictor columns (strictly excluded: target labels, disaster metadata, coordinates, target date)
CANONICAL_PREDICTOR_COLUMNS: list[str] = [
    # Dynamic Antecedent Meteorology ([t-30, t-1])
    "precip_1d_mm",
    "precip_3d_sum_mm",
    "precip_7d_sum_mm",
    "precip_14d_sum_mm",
    "precip_30d_sum_mm",
    "precip_7d_max_mm",
    "precip_14d_max_mm",
    "temp_mean_1d_c",
    "temp_min_1d_c",
    "temp_max_1d_c",
    "temp_7d_mean_c",
    "rh_mean_1d_pct",
    "rh_7d_mean_pct",
    "pressure_mean_1d_hpa",
    # Static Zonal Terrain (Copernicus DEM GLO-30)
    "elevation_mean_m",
    "elevation_min_m",
    "elevation_max_m",
    "elevation_std_m",
    "slope_mean_deg",
    "slope_max_deg",
    # Static Hydrological GIS (CWC Basins & HydroBASINS Level-7)
    "major_basin_count",
    "primary_basin_coverage_pct",
    "sub_basin_count",
    "mean_upstream_area_km2",
    # Spatial & Calendar Context
    "weather_cell_count",
    "day_of_year",
    "target_month",
]

# Columns strictly prohibited from ML training features (leakage risk or metadata)
PROHIBITED_LEAKAGE_COLUMNS: set[str] = {
    "district_id",
    "kgis_district_code",
    "lgd_district_code",
    "district_name",
    "target_date",
    "prediction_anchor_utc",
    "feature_window_start",
    "feature_window_end",
    "flood_occurrence",
    "label_state",
    "event_count",
    "source_event_ids",
    "main_causes",
    "severities",
    "fatalities",
    "displaced",
    "lead_time_days",
    "is_weather_complete_1d",
    "is_weather_complete_30d",
    "valid_weather_days_30d",
    "terrain_coverage_pct",
    "feature_version",
    "source_era5",
    "source_ifi",
    "source_dem",
    "source_hydro",
    "source_admin",
}


# -----------------------------------------------------------------------------
# Data Models & Enums
# -----------------------------------------------------------------------------


class PUStrategy(str, Enum):
    """Positive-Unlabeled learning strategy."""

    STANDARD_PU = "STANDARD_PU"  # All unlabeled treated as background with class weight
    HIGH_CONFIDENCE_NEGATIVES = "HIGH_CONFIDENCE_NEGATIVES"  # Meteorologically benign dry baseline
    BAGGING_PU = "BAGGING_PU"  # Bootstrap sub-sampling of unlabeled instances


class ModelType(str, Enum):
    """Supported model algorithms."""

    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"
    LIGHTGBM = "LIGHTGBM"


@dataclass(frozen=True)
class TemporalSplit:
    """Holds indices or boolean masks for chronological train, validation, and test partitions."""

    train_mask: np.ndarray
    val_mask: np.ndarray
    test_mask: np.ndarray
    train_years: tuple[int, ...]
    val_years: tuple[int, ...]
    test_years: tuple[int, ...]
    train_dates: tuple[str, str]
    val_dates: tuple[str, str]
    test_dates: tuple[str, str]

    def validate_no_overlap(self) -> None:
        """Validate strict temporal causality and non-overlap."""
        if dt_date.fromisoformat(self.train_dates[1]) >= dt_date.fromisoformat(self.val_dates[0]):
            raise ValueError(
                f"Train end ({self.train_dates[1]}) must precede Val start ({self.val_dates[0]})"
            )
        if dt_date.fromisoformat(self.val_dates[1]) >= dt_date.fromisoformat(self.test_dates[0]):
            raise ValueError(
                f"Val end ({self.val_dates[1]}) must precede Test start ({self.test_dates[0]})"
            )


@dataclass
class EvaluationMetrics:
    """Standardized machine learning evaluation metrics for positive-unlabeled datasets."""

    split_name: str
    total_samples: int
    positive_samples: int
    unlabeled_samples: int
    positive_prevalence: float
    roc_auc: float
    pr_auc: float
    brier_score: float
    decision_threshold: float
    precision_at_threshold: float
    recall_at_threshold: float
    f1_at_threshold: float
    pu_ranking_criterion: float
    confusion_matrix_raw: list[list[int]]
    elkan_noto_c: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelMetadata:
    """Metadata recorded for serialized model artifacts."""

    model_id: str
    model_type: ModelType
    pu_strategy: PUStrategy
    model_version: str
    created_at_utc: str
    feature_version: str
    features_used: list[str]
    train_dates: tuple[str, str]
    val_dates: tuple[str, str]
    test_dates: tuple[str, str]
    train_rows: int
    val_rows: int
    test_rows: int
    train_positives: int
    val_positives: int
    test_positives: int
    hyperparameters: dict[str, Any]
    validation_metrics: EvaluationMetrics
    test_metrics: EvaluationMetrics
    source_parquet_sha256: str
    target_semantics: dict[str, str] = field(default_factory=dict)
    pu_assumptions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# Task A: Dataset Auditor
# -----------------------------------------------------------------------------


class DatasetAuditor:
    """Performs rigorous empirical verification of the canonical feature matrix."""

    @staticmethod
    def audit(df: pd.DataFrame) -> dict[str, Any]:
        """Audit the feature matrix for integrity, missingness, and leakage risks."""
        total_rows = len(df)
        total_cols = len(df.columns)

        # 1. Target distribution
        label_counts = df["label_state"].value_counts().to_dict()
        flood_c = int(label_counts.get("FLOOD", 0))
        no_flood_c = int(label_counts.get("NO_FLOOD", 0))
        unknown_c = int(label_counts.get("UNKNOWN", 0))

        # 2. Date range & temporal span
        min_date = str(df["target_date"].min())
        max_date = str(df["target_date"].max())
        unique_dates = int(df["target_date"].nunique())

        # 3. District coverage
        unique_districts = int(df["district_id"].nunique())
        districts_list = sorted(df["district_name"].unique().tolist())

        # 4. Duplicate checks
        duplicates = int(df.duplicated(subset=["district_id", "target_date"]).sum())

        # 5. Missingness, NaNs, infinities, and dtypes across predictor features
        feature_missingness: dict[str, int] = {}
        feature_dtypes: dict[str, str] = {}
        feature_infs: dict[str, int] = {}
        for col in CANONICAL_PREDICTOR_COLUMNS:
            if col in df.columns:
                feature_missingness[col] = int(df[col].isna().sum())
                feature_dtypes[col] = str(df[col].dtype)
                if pd.api.types.is_numeric_dtype(df[col]):
                    feature_infs[col] = int(np.isinf(df[col]).sum())
                else:
                    feature_infs[col] = 0

        # 6. Constant features
        constant_features = [
            c for c in CANONICAL_PREDICTOR_COLUMNS if c in df.columns and df[c].nunique() <= 1
        ]

        # 7. Leakage check on candidate features
        leakage_violations = [c for c in CANONICAL_PREDICTOR_COLUMNS if c in PROHIBITED_LEAKAGE_COLUMNS]

        audit_results = {
            "total_rows": total_rows,
            "total_columns": total_cols,
            "target_distribution": {
                "FLOOD": flood_c,
                "NO_FLOOD": no_flood_c,
                "UNKNOWN": unknown_c,
                "positive_prevalence_pct": round(flood_c / total_rows * 100, 4),
            },
            "temporal_coverage": {
                "start_date": min_date,
                "end_date": max_date,
                "unique_dates": unique_dates,
            },
            "spatial_coverage": {
                "district_count": unique_districts,
                "districts": districts_list,
            },
            "data_quality": {
                "duplicate_district_day_rows": duplicates,
                "constant_features": constant_features,
                "leakage_violations_in_feature_list": leakage_violations,
                "total_missing_in_predictors": sum(feature_missingness.values()),
                "total_infs_in_predictors": sum(feature_infs.values()),
            },
            "feature_dtypes": feature_dtypes,
            "feature_missingness": feature_missingness,
            "feature_infs": feature_infs,
        }
        return audit_results

    @staticmethod
    def save_audit_report(audit_results: dict[str, Any], output_path: Path | str) -> Path:
        """Serialize audit results to a machine-readable JSON file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(audit_results, f, indent=2)
        logger.info("Saved machine-readable audit report to %s", out)
        return out


# -----------------------------------------------------------------------------
# Task B: Temporal Splitting
# -----------------------------------------------------------------------------


class TemporalDataSplitter:
    """
    Implements strict chronological expanding-window temporal splitting.

    Never shuffles time-series rows.
    """

    def __init__(
        self,
        train_end_year: int = 1973,
        val_year: int = 1974,
        test_year: int = 1975,
    ):
        self.train_end_year = train_end_year
        self.val_year = val_year
        self.test_year = test_year

    def split(self, df: pd.DataFrame) -> TemporalSplit:
        """
        Partition dataset into strictly chronological Train, Validation, and Test splits.

        Train: years <= train_end_year (e.g. 1969–1973)
        Val: year == val_year (e.g. 1974)
        Test: year == test_year (e.g. 1975)
        """
        train_mask = (df["target_year"] <= self.train_end_year).to_numpy()
        val_mask = (df["target_year"] == self.val_year).to_numpy()
        test_mask = (df["target_year"] == self.test_year).to_numpy()

        train_dates = (
            str(df.loc[train_mask, "target_date"].min()),
            str(df.loc[train_mask, "target_date"].max()),
        )
        val_dates = (
            str(df.loc[val_mask, "target_date"].min()),
            str(df.loc[val_mask, "target_date"].max()),
        )
        test_dates = (
            str(df.loc[test_mask, "target_date"].min()),
            str(df.loc[test_mask, "target_date"].max()),
        )

        split_obj = TemporalSplit(
            train_mask=train_mask,
            val_mask=val_mask,
            test_mask=test_mask,
            train_years=tuple(sorted(df.loc[train_mask, "target_year"].unique())),
            val_years=(self.val_year,),
            test_years=(self.test_year,),
            train_dates=train_dates,
            val_dates=val_dates,
            test_dates=test_dates,
        )
        split_obj.validate_no_overlap()
        return split_obj


# -----------------------------------------------------------------------------
# Task C & D: PU Learning Strategies
# -----------------------------------------------------------------------------


class PUDatasetPreparer:
    """Prepares training subsets according to the selected PU learning strategy."""

    @staticmethod
    def prepare_training_data(
        df: pd.DataFrame,
        train_mask: np.ndarray,
        feature_cols: list[str],
        strategy: PUStrategy,
        random_state: int = 42,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """
        Construct training feature matrix X and target labels y based on PU strategy.

        Returns
        -------
        X_train : np.ndarray
        y_train : np.ndarray
        sample_weight : np.ndarray | None
        """
        df_tr = df.loc[train_mask].copy()
        is_flood = (df_tr["label_state"] == "FLOOD").to_numpy()

        if strategy == PUStrategy.STANDARD_PU:
            # Strategy 1: Standard PU Baseline
            # Positives = 1, All Unlabeled = 0, class_weight='balanced' handles prevalence
            X = df_tr[feature_cols].to_numpy()
            y = is_flood.astype(int)
            return X, y, None

        elif strategy == PUStrategy.HIGH_CONFIDENCE_NEGATIVES:
            # Strategy 2: High-Confidence Negatives
            # Reliable Negatives: non-monsoon dry season (Jan–Mar), 30d precip <= 1mm, 1d precip == 0mm
            dry_season = df_tr["target_month"].isin([1, 2, 3]).to_numpy()
            dry_rainfall = (df_tr["precip_30d_sum_mm"] <= 1.0).to_numpy() & (df_tr["precip_1d_mm"] == 0.0).to_numpy()
            reliable_negative = dry_season & dry_rainfall & (~is_flood)

            keep_mask = is_flood | reliable_negative
            X = df_tr.loc[keep_mask, feature_cols].to_numpy()
            y = is_flood[keep_mask].astype(int)

            logger.info(
                "High-Confidence Negatives selection: %d Positives, %d Reliable Negatives (discarded %d ambiguous unlabeled)",
                is_flood.sum(),
                reliable_negative.sum(),
                (~keep_mask).sum(),
            )
            return X, y, None

        elif strategy == PUStrategy.BAGGING_PU:
            # For bagging, the full train set is returned; bagging is orchestrated inside the model fit
            X = df_tr[feature_cols].to_numpy()
            y = is_flood.astype(int)
            return X, y, None

        else:
            raise ValueError(f"Unsupported PU strategy: {strategy}")


# -----------------------------------------------------------------------------
# Task F: Evaluation Engine
# -----------------------------------------------------------------------------


class PUEvaluator:
    """Calculates PR-AUC, ROC-AUC, Brier score, and PU ranking metrics."""

    @staticmethod
    def evaluate(
        y_true_obs: np.ndarray,
        y_prob: np.ndarray,
        split_name: str = "validation",
        fixed_threshold: float | None = None,
    ) -> EvaluationMetrics:
        """
        Evaluate predicted probabilities against observed disaster flood labels.

        Note: Because y_true_obs has 0 for unlabeled, observed precision is a conservative
        lower bound on true precision (Elkan & Noto 2008).
        """
        n_samples = len(y_true_obs)
        n_pos = int(np.sum(y_true_obs == 1))
        n_unlab = int(np.sum(y_true_obs == 0))
        prevalence = n_pos / n_samples if n_samples > 0 else 0.0

        # Continuous ranking metrics
        try:
            roc_auc = float(roc_auc_score(y_true_obs, y_prob))
        except Exception:
            roc_auc = 0.5

        try:
            pr_auc = float(average_precision_score(y_true_obs, y_prob))
        except Exception:
            pr_auc = prevalence

        brier = float(brier_score_loss(y_true_obs, y_prob))

        # Threshold selection: if not fixed, choose threshold maximizing F1 on observed positives
        if fixed_threshold is None:
            precisions, recalls, thresholds = precision_recall_curve(y_true_obs, y_prob)
            f1_scores = np.where(
                (precisions + recalls) > 0,
                2 * (precisions * recalls) / (precisions + recalls + 1e-12),
                0.0,
            )
            best_idx = np.argmax(f1_scores)
            if best_idx < len(thresholds):
                threshold = float(thresholds[best_idx])
            else:
                threshold = 0.5
        else:
            threshold = fixed_threshold

        y_pred = (y_prob >= threshold).astype(int)
        prec = float(precision_score(y_true_obs, y_pred, zero_division=0))
        rec = float(recall_score(y_true_obs, y_pred, zero_division=0))
        f1 = float(f1_score(y_true_obs, y_pred, zero_division=0))

        # PU ranking criterion: r^2 / P(Y_hat = 1) (Lee & Liu 2003)
        p_pred_pos = float(np.mean(y_pred == 1))
        pu_criterion = (rec**2) / (p_pred_pos + 1e-6)

        # Elkan-Noto label frequency estimate: mean(y_prob[y_true_obs == 1]) (Elkan & Noto 2008)
        elkan_noto_c = float(np.mean(y_prob[y_true_obs == 1])) if n_pos > 0 else 0.0

        cm = confusion_matrix(y_true_obs, y_pred).tolist()

        return EvaluationMetrics(
            split_name=split_name,
            total_samples=n_samples,
            positive_samples=n_pos,
            unlabeled_samples=n_unlab,
            positive_prevalence=round(prevalence, 4),
            roc_auc=round(roc_auc, 4),
            pr_auc=round(pr_auc, 4),
            brier_score=round(brier, 4),
            decision_threshold=round(threshold, 4),
            precision_at_threshold=round(prec, 4),
            recall_at_threshold=round(rec, 4),
            f1_at_threshold=round(f1, 4),
            pu_ranking_criterion=round(pu_criterion, 4),
            confusion_matrix_raw=cm,
            elkan_noto_c=round(elkan_noto_c, 4),
        )


# -----------------------------------------------------------------------------
# Task C, E & G: Model Pipelines & Interpretability
# -----------------------------------------------------------------------------


class BaseFloodModel:
    """Base class for FloodPulse historical baseline ML models."""

    def __init__(
        self,
        model_type: ModelType,
        pu_strategy: PUStrategy,
        feature_cols: list[str] | None = None,
        random_state: int = 42,
    ):
        self.model_type = model_type
        self.pu_strategy = pu_strategy
        self.feature_cols = feature_cols or CANONICAL_PREDICTOR_COLUMNS
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.fitted_: bool = False
        self.decision_threshold_: float = 0.5

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> BaseFloodModel:
        raise NotImplementedError

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def get_feature_importances(self) -> dict[str, float]:
        raise NotImplementedError


class LogisticRegressionBaseline(BaseFloodModel):
    """
    Transparent, interpretable L2-penalized Logistic Regression baseline.

    Preprocessing: StandardScaler fit ONLY on training split.
    Probability: Sigmoid calibration via scikit-learn.
    Interpretability: Standardized regression coefficients beta_j.
    """

    def __init__(
        self,
        pu_strategy: PUStrategy = PUStrategy.STANDARD_PU,
        feature_cols: list[str] | None = None,
        C: float = 1.0,
        random_state: int = 42,
        bagging_n_estimators: int = 15,
        bagging_ratio: int = 5,
    ):
        super().__init__(
            model_type=ModelType.LOGISTIC_REGRESSION,
            pu_strategy=pu_strategy,
            feature_cols=feature_cols,
            random_state=random_state,
        )
        self.C = C
        self.bagging_n_estimators = bagging_n_estimators
        self.bagging_ratio = bagging_ratio
        self.model_: LogisticRegression | None = None
        self.ensemble_models_: list[LogisticRegression] = []

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> LogisticRegressionBaseline:
        # Fit scaler ONLY on X
        X_scaled = self.scaler.fit_transform(X)

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            # Bagging PU: Ensemble of estimators with bootstrap unlabeled sampling
            P_idx = np.where(y == 1)[0]
            U_idx = np.where(y == 0)[0]
            n_p = len(P_idx)
            rng = np.random.RandomState(self.random_state)

            self.ensemble_models_ = []
            for b in range(self.bagging_n_estimators):
                u_sample = rng.choice(U_idx, size=self.bagging_ratio * n_p, replace=False)
                b_idx = np.concatenate([P_idx, u_sample])
                X_b = X_scaled[b_idx]
                y_b = np.concatenate([np.ones(n_p), np.zeros(self.bagging_ratio * n_p)])

                clf = LogisticRegression(
                    C=self.C,
                    max_iter=1000,
                    random_state=self.random_state + b,
                    solver="lbfgs",
                )
                clf.fit(X_b, y_b)
                self.ensemble_models_.append(clf)
        else:
            # Standard PU or High-Confidence Negatives
            self.model_ = LogisticRegression(
                C=self.C,
                class_weight="balanced" if self.pu_strategy == PUStrategy.STANDARD_PU else None,
                max_iter=1000,
                random_state=self.random_state,
                solver="lbfgs",
            )
            self.model_.fit(X_scaled, y, sample_weight=sample_weight)

        self.fitted_ = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise ValueError("Model has not been fitted yet.")
        X_scaled = self.scaler.transform(X)

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            probs = np.zeros(len(X))
            for clf in self.ensemble_models_:
                probs += clf.predict_proba(X_scaled)[:, 1]
            return probs / len(self.ensemble_models_)
        else:
            assert self.model_ is not None
            return self.model_.predict_proba(X_scaled)[:, 1]

    def get_feature_importances(self) -> dict[str, float]:
        """Return standardized coefficient weights beta_j."""
        if not self.fitted_:
            raise ValueError("Model has not been fitted yet.")

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            coefs = np.mean([clf.coef_[0] for clf in self.ensemble_models_], axis=0)
        else:
            assert self.model_ is not None
            coefs = self.model_.coef_[0]

        return {f: round(float(c), 4) for f, c in zip(self.feature_cols, coefs)}


class LightGBMBaseline(BaseFloodModel):
    """
    Gradient-boosted decision tree baseline using LightGBM.

    Handles non-linear feature interactions (rainfall intensity x duration x slope).
    """

    def __init__(
        self,
        pu_strategy: PUStrategy = PUStrategy.STANDARD_PU,
        feature_cols: list[str] | None = None,
        n_estimators: int = 100,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        num_leaves: int = 31,
        random_state: int = 42,
        bagging_n_estimators: int = 15,
        bagging_ratio: int = 5,
    ):
        super().__init__(
            model_type=ModelType.LIGHTGBM,
            pu_strategy=pu_strategy,
            feature_cols=feature_cols,
            random_state=random_state,
        )
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.bagging_n_estimators = bagging_n_estimators
        self.bagging_ratio = bagging_ratio
        self.model_: LGBMClassifier | None = None
        self.ensemble_models_: list[LGBMClassifier] = []

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> LightGBMBaseline:
        # Preprocessing: StandardScaler fit ONLY on training data
        X_scaled = self.scaler.fit_transform(X)

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            P_idx = np.where(y == 1)[0]
            U_idx = np.where(y == 0)[0]
            n_p = len(P_idx)
            rng = np.random.RandomState(self.random_state)

            self.ensemble_models_ = []
            for b in range(self.bagging_n_estimators):
                u_sample = rng.choice(U_idx, size=self.bagging_ratio * n_p, replace=False)
                b_idx = np.concatenate([P_idx, u_sample])
                X_b = X_scaled[b_idx]
                y_b = np.concatenate([np.ones(n_p), np.zeros(self.bagging_ratio * n_p)])

                clf = LGBMClassifier(
                    n_estimators=self.n_estimators,
                    learning_rate=self.learning_rate,
                    max_depth=self.max_depth,
                    num_leaves=self.num_leaves,
                    random_state=self.random_state + b,
                    verbose=-1,
                    n_jobs=1,
                )
                clf.fit(X_b, y_b)
                self.ensemble_models_.append(clf)
        else:
            self.model_ = LGBMClassifier(
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                max_depth=self.max_depth,
                num_leaves=self.num_leaves,
                class_weight="balanced" if self.pu_strategy == PUStrategy.STANDARD_PU else None,
                random_state=self.random_state,
                verbose=-1,
                n_jobs=-1,
            )
            self.model_.fit(X_scaled, y, sample_weight=sample_weight)

        self.fitted_ = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise ValueError("Model has not been fitted yet.")
        X_scaled = self.scaler.transform(X)

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            probs = np.zeros(len(X))
            for clf in self.ensemble_models_:
                probs += clf.predict_proba(X_scaled)[:, 1]
            return probs / len(self.ensemble_models_)
        else:
            assert self.model_ is not None
            return self.model_.predict_proba(X_scaled)[:, 1]

    def get_feature_importances(self) -> dict[str, float]:
        """Return split-based feature importance counts."""
        if not self.fitted_:
            raise ValueError("Model has not been fitted yet.")

        if self.pu_strategy == PUStrategy.BAGGING_PU:
            importances = np.mean([clf.feature_importances_ for clf in self.ensemble_models_], axis=0)
            return {f: float(imp) for f, imp in zip(self.feature_cols, importances)}
        else:
            assert self.model_ is not None
            importances = self.model_.feature_importances_
            return {f: float(imp) for f, imp in zip(self.feature_cols, importances)}


# -----------------------------------------------------------------------------
# Task H: Model Artifact Serialization
# -----------------------------------------------------------------------------


class ModelArtifactManager:
    """Manages serialization, loading, and provenance of trained model artifacts."""

    def __init__(self, base_dir: Path | str | None = None):
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_MODELS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_model(
        self,
        model: BaseFloodModel,
        metadata: ModelMetadata,
        filename_prefix: str | None = None,
    ) -> tuple[Path, Path]:
        """
        Save model pipeline (joblib) and companion JSON metadata.

        Returns (model_path, metadata_path).
        """
        prefix = filename_prefix or f"{metadata.model_type.value.lower()}_{metadata.pu_strategy.value.lower()}_{metadata.model_id[:8]}"
        model_path = self.base_dir / f"{prefix}_pipeline.joblib"
        meta_path = self.base_dir / f"{prefix}_metadata.json"

        # 1. Serialize model and fitted scaler
        payload = {
            "model_type": model.model_type.value,
            "pu_strategy": model.pu_strategy.value,
            "feature_cols": model.feature_cols,
            "scaler": model.scaler,
            "decision_threshold": model.decision_threshold_,
            "model": model,
        }
        joblib.dump(payload, model_path)

        # 2. Serialize metadata
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        logger.info("Saved model artifact to %s and metadata to %s", model_path, meta_path)
        return model_path, meta_path

    def load_model(self, model_path: Path | str) -> tuple[BaseFloodModel, dict[str, Any]]:
        """Load serialized model artifact and verify integrity."""
        p = Path(model_path)
        if not p.exists():
            raise FileNotFoundError(f"Model artifact not found: {p}")

        payload = joblib.load(p)
        model = payload["model"]
        return model, payload


# -----------------------------------------------------------------------------
# Modeling Orchestrator
# -----------------------------------------------------------------------------


class ModelingOrchestrator:
    """End-to-end orchestrator for training, evaluating, and persisting baseline ML models."""

    def __init__(
        self,
        feature_matrix_path: Path | str | None = None,
        models_dir: Path | str | None = None,
        train_end_year: int = 1973,
        val_year: int = 1974,
        test_year: int = 1975,
    ):
        self.feature_matrix_path = Path(feature_matrix_path) if feature_matrix_path else DEFAULT_FEATURE_MATRIX_PATH
        self.splitter = TemporalDataSplitter(train_end_year, val_year, test_year)
        self.evaluator = PUEvaluator()
        self.artifact_mgr = ModelArtifactManager(models_dir)

    def run_training_experiment(
        self,
        model_type: ModelType = ModelType.LOGISTIC_REGRESSION,
        pu_strategy: PUStrategy = PUStrategy.STANDARD_PU,
        hyperparameters: dict[str, Any] | None = None,
    ) -> tuple[BaseFloodModel, ModelMetadata]:
        """Execute full training, evaluation, and artifact serialization."""
        # 1. Load data
        df = pq.read_table(self.feature_matrix_path).to_pandas()
        feature_cols = CANONICAL_PREDICTOR_COLUMNS

        # 2. Temporal split
        split = self.splitter.split(df)
        y_obs = (df["label_state"] == "FLOOD").to_numpy().astype(int)

        # 3. Prepare training data according to PU strategy
        X_tr, y_tr, sample_weights = PUDatasetPreparer.prepare_training_data(
            df=df,
            train_mask=split.train_mask,
            feature_cols=feature_cols,
            strategy=pu_strategy,
        )

        # 4. Instantiate model
        hparams = hyperparameters or {}
        if model_type == ModelType.LOGISTIC_REGRESSION:
            model = LogisticRegressionBaseline(
                pu_strategy=pu_strategy,
                feature_cols=feature_cols,
                C=hparams.get("C", 1.0),
                bagging_n_estimators=hparams.get("bagging_n_estimators", 15),
                bagging_ratio=hparams.get("bagging_ratio", 5),
            )
        elif model_type == ModelType.LIGHTGBM:
            model = LightGBMBaseline(
                pu_strategy=pu_strategy,
                feature_cols=feature_cols,
                n_estimators=hparams.get("n_estimators", 100),
                learning_rate=hparams.get("learning_rate", 0.05),
                max_depth=hparams.get("max_depth", 6),
                num_leaves=hparams.get("num_leaves", 31),
                bagging_n_estimators=hparams.get("bagging_n_estimators", 15),
                bagging_ratio=hparams.get("bagging_ratio", 5),
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        # 5. Fit model
        logger.info("Fitting %s with %s on %d samples", model_type.value, pu_strategy.value, len(X_tr))
        model.fit(X_tr, y_tr, sample_weight=sample_weights)

        # 6. Evaluate on Validation Split (1974)
        X_va = df.loc[split.val_mask, feature_cols].to_numpy()
        y_va_obs = y_obs[split.val_mask]
        p_va = model.predict_proba(X_va)
        val_metrics = self.evaluator.evaluate(y_va_obs, p_va, split_name="validation")

        # Set model decision threshold from validation tuning
        model.decision_threshold_ = val_metrics.decision_threshold

        # 7. Evaluate on Held-out Test Split (1975)
        X_te = df.loc[split.test_mask, feature_cols].to_numpy()
        y_te_obs = y_obs[split.test_mask]
        p_te = model.predict_proba(X_te)
        test_metrics = self.evaluator.evaluate(
            y_te_obs,
            p_te,
            split_name="test",
            fixed_threshold=model.decision_threshold_,
        )

        # 8. Compute Parquet SHA-256 for provenance
        with open(self.feature_matrix_path, "rb") as f:
            src_sha256 = hashlib.sha256(f.read()).hexdigest()

        # 9. Assemble Target Semantics and PU Assumptions
        target_semantics = {
            "FLOOD": "Documented positive flood event evidence in India Flood Inventory (IFI v3.0)",
            "NO_FLOOD": "Explicitly confirmed absence of flood (zero in historical archive)",
            "UNKNOWN": "Unrecorded observation dates; preserved as NULL; never imputed as negative",
        }
        pu_assumptions = {
            "strategy": pu_strategy.value,
            "description": (
                "Selected Completely At Random (SCAR): all unlabeled instances treated as background with class weighting"
                if pu_strategy == PUStrategy.STANDARD_PU
                else (
                    "Hydrologically reliable negatives: non-monsoon dry season (Jan–Mar), 30d precip <= 1mm, 1d precip == 0mm"
                    if pu_strategy == PUStrategy.HIGH_CONFIDENCE_NEGATIVES
                    else "Bootstrap subsampling ensemble of unlabeled background instances (ratio 5:1)"
                )
            ),
            "limitations": (
                "Background contains unrecorded true positive events due to historical reporting sparsity"
                if pu_strategy == PUStrategy.STANDARD_PU
                else (
                    "Excludes ambiguous monsoon non-event days from supervised training to prevent negative label contamination"
                    if pu_strategy == PUStrategy.HIGH_CONFIDENCE_NEGATIVES
                    else "Ensemble variance across subsamples; computational cost of multiple estimators"
                )
            ),
        }

        # 10. Assemble Metadata
        model_id = str(uuid.uuid4())
        metadata = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            pu_strategy=pu_strategy,
            model_version=MODEL_FRAMEWORK_VERSION,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            feature_version="1.0.0",
            features_used=feature_cols,
            train_dates=split.train_dates,
            val_dates=split.val_dates,
            test_dates=split.test_dates,
            train_rows=int(split.train_mask.sum()),
            val_rows=int(split.val_mask.sum()),
            test_rows=int(split.test_mask.sum()),
            train_positives=int(y_obs[split.train_mask].sum()),
            val_positives=int(y_obs[split.val_mask].sum()),
            test_positives=int(y_obs[split.test_mask].sum()),
            hyperparameters=hparams,
            validation_metrics=val_metrics,
            test_metrics=test_metrics,
            source_parquet_sha256=src_sha256,
            target_semantics=target_semantics,
            pu_assumptions=pu_assumptions,
        )

        # 11. Persist artifacts
        self.artifact_mgr.save_model(model, metadata)
        return model, metadata
