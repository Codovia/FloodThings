# ML_SPEC.md

**Project:** FloodPulse
**Status:** Planning document only. No ML model, dataset, or pipeline has been implemented.

---

## Intended methodology

```
Real observations (weather, hydrology, flood events)
      ↓
Validated dataset
      ↓
Target definition (from legitimate historical flood records)
      ↓
Feature engineering (from real weather, hydrology, terrain, GIS data)
      ↓
Temporal/spatial split (time-based, no random split)
      ↓
Baseline model
      ↓
Candidate models
      ↓
Evaluation (held-out historical period)
      ↓
Calibration
      ↓
Model versioning
      ↓
Prediction service
```

---

## Target definition (planned)

**Spatial unit:** District polygon (Karnataka).

**Temporal unit:** Day (or multi-day prediction window — to be defined based on data availability).

**Positive label:** A documented flood event occurring in the defined spatial unit during the defined prediction window, sourced from legitimate historical flood-event records (e.g., India Flood Inventory).

**Negative label:** No documented flood event for that spatial unit and time window.

**Limitation:** "Negative" means "not documented in the inventory," not "confirmed no flooding." This limitation must be documented and considered in evaluation.

The final target definition has not been implemented. It will be designed during the data and ML phases.

---

## Feature categories (planned)

| Category | Examples | Source |
|---|---|---|
| Rainfall | Daily rainfall, rolling sums (3-day, 7-day), anomalies | IMD, KSNDMC |
| Hydrology | River water level, river discharge, reservoir storage | CWC, KSNDMC |
| Terrain | Elevation, slope, distance to river, distance to waterbody | SRTM DEM, river geometries |
| Temporal | Month, day of year, monsoon phase | Calendar |
| Spatial | District properties, basin membership | GIS boundaries |

All features must be derived from real data. No hardcoded per-district feature values.

---

## Train/test split

**Rule:** Time-based split only. Never random.

The training set contains observations before a temporal cutoff. The test set contains observations after the cutoff. This matches how the model will be used in production — trained on the past, predicting the future.

No spatial leakage: if spatial cross-validation is used, it must be documented.

---

## Evaluation metrics

The following metrics must be computed and reported:

- **Precision** — proportion of predicted floods that were real.
- **Recall** — proportion of real floods that were detected.
- **F1 score** — harmonic mean of precision and recall.
- **PR-AUC** — area under the precision-recall curve (important for imbalanced classes).
- **ROC-AUC** — area under the ROC curve (where meaningful).
- **Confusion matrix** — full breakdown of TP/FP/TN/FN.
- **Calibration** — are predicted probabilities meaningful?

Accuracy alone is not sufficient for an imbalanced flood prediction problem.

---

## Model versioning

Every trained model must record:

- Model version ID.
- Algorithm and hyperparameters.
- Training dataset version.
- Training date.
- Feature schema.
- Evaluation metrics on the holdout set.
- Artifact file path.

---

## Prohibitions

- No random synthetic environmental data used for training.
- No hardcoded district risk values presented as ML features.
- No leakage from future observations into training features.
- No unexplained heuristic risk scores presented as ML predictions.
- No formula-generated flood labels (e.g., `risk = rainfall * 0.3 + ...`) used as ML targets.
- No `np.random` values used as training data.
- No model declared "final" without documented evaluation on a temporal holdout.

---

## Training environment

Google Colab may be used for ML experimentation and training. Trained model artifacts and evaluation results must be versioned and transferred to the project repository or artifact store.
