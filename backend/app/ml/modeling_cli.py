"""
Command-line interface for Baseline ML Modeling and PU Evaluation (Phase 5).

Usage:
  python -m app.ml.modeling_cli audit
  python -m app.ml.modeling_cli train --model-type LOGISTIC_REGRESSION --pu-strategy HIGH_CONFIDENCE_NEGATIVES
  python -m app.ml.modeling_cli train --model-type LIGHTGBM --pu-strategy STANDARD_PU
  python -m app.ml.modeling_cli compare
  python -m app.ml.modeling_cli explain --model-id <MODEL_ID_OR_PREFIX>
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

import pyarrow.parquet as pq

from app.ml.baseline_modeling import (
    DEFAULT_FEATURE_MATRIX_PATH,
    DEFAULT_MODELS_DIR,
    DatasetAuditor,
    ModelArtifactManager,
    ModelType,
    ModelingOrchestrator,
    PUStrategy,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("modeling_cli")


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit the canonical feature matrix dataset and produce machine-readable report."""
    p_path = Path(args.matrix_path)
    if not p_path.exists():
        logger.error("Feature matrix not found: %s", p_path)
        return 1

    df = pq.read_table(p_path).to_pandas()
    audit_results = DatasetAuditor.audit(df)

    export_path = Path(args.export_path) if args.export_path else DEFAULT_MODELS_DIR / "feature_matrix_audit.json"
    DatasetAuditor.save_audit_report(audit_results, export_path)

    print("\n" + "=" * 65)
    print("CANONICAL FEATURE MATRIX EMPIRICAL AUDIT (PHASE 5)")
    print("=" * 65)
    print(json.dumps(audit_results, indent=2))
    print("=" * 65)
    print(f"Machine-readable audit saved to: {export_path}")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """Train a baseline model using chronological splitting and a PU strategy."""
    m_type = ModelType(args.model_type)
    pu_strat = PUStrategy(args.pu_strategy)

    orchestrator = ModelingOrchestrator(
        feature_matrix_path=args.matrix_path,
        models_dir=args.models_dir,
        train_end_year=args.train_end_year,
        val_year=args.val_year,
        test_year=args.test_year,
    )

    logger.info("Starting training experiment: Model=%s, Strategy=%s", m_type.value, pu_strat.value)
    model, metadata = orchestrator.run_training_experiment(
        model_type=m_type,
        pu_strategy=pu_strat,
    )

    print("\n" + "=" * 65)
    print(f"TRAINING COMPLETE: {m_type.value} [{pu_strat.value}]")
    print("=" * 65)
    print(f"Model ID:            {metadata.model_id}")
    print(f"Train Period:        {metadata.train_dates[0]} to {metadata.train_dates[1]} ({metadata.train_rows} rows, {metadata.train_positives} FLOOD)")
    print(f"Validation Period:   {metadata.val_dates[0]} to {metadata.val_dates[1]} ({metadata.val_rows} rows, {metadata.val_positives} FLOOD)")
    print(f"Test Period:         {metadata.test_dates[0]} to {metadata.test_dates[1]} ({metadata.test_rows} rows, {metadata.test_positives} FLOOD)")
    print("-" * 65)
    print("VALIDATION METRICS (1974):")
    print(f"  PR-AUC:            {metadata.validation_metrics.pr_auc:.4f} (prevalence = {metadata.validation_metrics.positive_prevalence:.4f})")
    print(f"  ROC-AUC:           {metadata.validation_metrics.roc_auc:.4f}")
    print(f"  Decision Threshold:{metadata.validation_metrics.decision_threshold:.4f}")
    print(f"  Precision:         {metadata.validation_metrics.precision_at_threshold:.4f}")
    print(f"  Recall:            {metadata.validation_metrics.recall_at_threshold:.4f}")
    print(f"  F1 Score:          {metadata.validation_metrics.f1_at_threshold:.4f}")
    print(f"  Brier Score:       {metadata.validation_metrics.brier_score:.4f}")
    print(f"  PU Ranking Score:  {metadata.validation_metrics.pu_ranking_criterion:.4f}")
    print("-" * 65)
    print("HELD-OUT TEST METRICS (1975):")
    print(f"  PR-AUC:            {metadata.test_metrics.pr_auc:.4f} (prevalence = {metadata.test_metrics.positive_prevalence:.4f})")
    print(f"  ROC-AUC:           {metadata.test_metrics.roc_auc:.4f}")
    print(f"  Precision:         {metadata.test_metrics.precision_at_threshold:.4f}")
    print(f"  Recall:            {metadata.test_metrics.recall_at_threshold:.4f}")
    print(f"  F1 Score:          {metadata.test_metrics.f1_at_threshold:.4f}")
    print(f"  Brier Score:       {metadata.test_metrics.brier_score:.4f}")
    print("=" * 65)

    # Feature Importance / Coefficients
    importances = model.get_feature_importances()
    print("\nTOP 10 FEATURE INFLUENCES:")
    sorted_imp = sorted(importances.items(), key=lambda x: abs(x[1]), reverse=True)
    for feat, val in sorted_imp[:10]:
        print(f"  {feat:30s}: {val:+.4f}" if m_type == ModelType.LOGISTIC_REGRESSION else f"  {feat:30s}: {val:6.1f}")
    print("=" * 65)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Run full comparative suite across all models and PU strategies."""
    orchestrator = ModelingOrchestrator(
        feature_matrix_path=args.matrix_path,
        models_dir=args.models_dir,
    )

    experiments = [
        (ModelType.LOGISTIC_REGRESSION, PUStrategy.STANDARD_PU),
        (ModelType.LOGISTIC_REGRESSION, PUStrategy.HIGH_CONFIDENCE_NEGATIVES),
        (ModelType.LOGISTIC_REGRESSION, PUStrategy.BAGGING_PU),
        (ModelType.LIGHTGBM, PUStrategy.STANDARD_PU),
        (ModelType.LIGHTGBM, PUStrategy.HIGH_CONFIDENCE_NEGATIVES),
        (ModelType.LIGHTGBM, PUStrategy.BAGGING_PU),
    ]

    results = []
    print("\n" + "=" * 80)
    print("RUNNING PU STRATEGY & MODEL COMPARISON EXPERIMENTS")
    print("=" * 80)

    for m_type, pu_strat in experiments:
        logger.info("Evaluating: %s + %s", m_type.value, pu_strat.value)
        _, meta = orchestrator.run_training_experiment(model_type=m_type, pu_strategy=pu_strat)
        results.append({
            "model": m_type.value,
            "strategy": pu_strat.value,
            "val_pr_auc": meta.validation_metrics.pr_auc,
            "val_roc_auc": meta.validation_metrics.roc_auc,
            "test_pr_auc": meta.test_metrics.pr_auc,
            "test_roc_auc": meta.test_metrics.roc_auc,
            "test_f1": meta.test_metrics.f1_at_threshold,
            "test_recall": meta.test_metrics.recall_at_threshold,
            "elkan_noto_c": meta.test_metrics.elkan_noto_c,
        })

    # Save machine-readable comparison report
    export_path = Path(args.export_path) if args.export_path else Path(args.models_dir) / "comparison_results.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved comparison results to %s", export_path)

    print("\n" + "=" * 80)
    print(f"{'Model':<22} | {'PU Strategy':<26} | {'Val PR-AUC':<10} | {'Test PR-AUC':<11} | {'Test ROC-AUC':<12} | {'Test Recall':<11}")
    print("-" * 80)
    for r in results:
        print(f"{r['model']:<22} | {r['strategy']:<26} | {r['val_pr_auc']:<10.4f} | {r['test_pr_auc']:<11.4f} | {r['test_roc_auc']:<12.4f} | {r['test_recall']:<11.4f}")
    print("=" * 80)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline ML Modeling CLI (Phase 5)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit canonical feature matrix")
    p_audit.add_argument("--matrix-path", type=str, default=str(DEFAULT_FEATURE_MATRIX_PATH))
    p_audit.add_argument("--export-path", type=str, default=str(DEFAULT_MODELS_DIR / "feature_matrix_audit.json"))
    p_audit.set_defaults(func=cmd_audit)

    # train
    p_train = subparsers.add_parser("train", help="Train baseline model")
    p_train.add_argument("--matrix-path", type=str, default=str(DEFAULT_FEATURE_MATRIX_PATH))
    p_train.add_argument("--models-dir", type=str, default=str(DEFAULT_MODELS_DIR))
    p_train.add_argument("--model-type", type=str, default=ModelType.LOGISTIC_REGRESSION.value, choices=[m.value for m in ModelType])
    p_train.add_argument("--pu-strategy", type=str, default=PUStrategy.STANDARD_PU.value, choices=[s.value for s in PUStrategy])
    p_train.add_argument("--train-end-year", type=int, default=1973)
    p_train.add_argument("--val-year", type=int, default=1974)
    p_train.add_argument("--test-year", type=int, default=1975)
    p_train.set_defaults(func=cmd_train)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare all models and PU strategies")
    p_compare.add_argument("--matrix-path", type=str, default=str(DEFAULT_FEATURE_MATRIX_PATH))
    p_compare.add_argument("--models-dir", type=str, default=str(DEFAULT_MODELS_DIR))
    p_compare.add_argument("--export-path", type=str, default=str(DEFAULT_MODELS_DIR / "comparison_results.json"))
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
