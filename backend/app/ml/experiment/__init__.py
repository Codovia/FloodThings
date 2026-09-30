"""
Reproducible Baseline ML Experiment Package (Phase 5.4).

Provides:
- Dataset loader with canonical 27-feature filtering and 930-row cold-start exclusion
- Chronological train/validation/test temporal splitter
- PU-framed evaluation metrics (PR-AUC, ROC-AUC, Elkan-Noto c, Lee-Liu criterion)
- Baseline models: Logistic Regression (L2, standardized) and Random Forest
- Reproducible experiment runner and provenance metadata serializer
"""

from app.ml.experiment.dataset import ExperimentDataset, load_supervised_dataset
from app.ml.experiment.splits import ChronologicalSplit, create_chronological_split
from app.ml.experiment.metrics import PUEvaluationMetrics, evaluate_pu_predictions
from app.ml.experiment.baseline import LogisticRegressionBaseline, RandomForestBaseline
from app.ml.experiment.runner import ExperimentRunner, run_phase_5_4_experiments

__all__ = [
    "ExperimentDataset",
    "load_supervised_dataset",
    "ChronologicalSplit",
    "create_chronological_split",
    "PUEvaluationMetrics",
    "evaluate_pu_predictions",
    "LogisticRegressionBaseline",
    "RandomForestBaseline",
    "ExperimentRunner",
    "run_phase_5_4_experiments",
]
