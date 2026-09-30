# PHASE 5.4: BASELINE ML MODELING & VALIDATION REPORT

**Project:** FloodPulse — Karnataka AI Flood Intelligence & Emergency Response System  
**Phase:** Phase 5.4 — Baseline ML Training & Validation  
**Date:** 2026-09-30  
**Status:** COMPLETED — REPRODUCIBLE BASELINES ESTABLISHED (SCAR NOT VALIDATED; PROXY EVALUATION ONLY)  
**Artifact Directory:** `models/experiments/phase_5_4/`  

---

## 1. Objective

Phase 5.4 establishes the first reproducible baseline machine learning models for district-level flood occurrence prediction across Karnataka. Building directly on the Phase 5.3 scientific audit, this phase implements:
1. A modular, reproducible experiment harness (`backend/app/ml/experiment/`).
2. Rigorous Positive-Unlabeled (PU) target framing without synthetic negatives or label fabrication.
3. Strict chronological evaluation across Train (2011–2019), Validation (2020–2021), and Held-Out Test (2022–2023) partitions.
4. Two transparent, interpretable baselines: L2-penalized Logistic Regression and Random Forest.
5. Absolute prohibition on gradient boosting (LightGBM/XGBoost), deep learning, or hyperparameter sweeps in this phase.

---

## 2. Dataset Inventory & Integrity

The experiment was conducted on the audited supervised feature matrix:

| Property | Value | Verification |
| :--- | :--- | :---: |
| **Parquet Path** | `data/processed/ml_matrix/recent/district_day_matrix_2011_2023.parquet` | Verified |
| **SHA-256 Digest** | `d459e4461166842e194de8f8373f227585169f124cd620160a4aea74651e5dac` | **Exact Match** |
| **Total Raw Rows** | 142,228 (4,588 calendar days $\times$ 31 districts) | Verified |
| **Excluded Cold-Start Rows** | 930 rows (Jan 1–30, 2011; `is_weather_complete_30d == False`) | Excluded |
| **Active Dataset Rows** | 141,298 rows | Verified |
| **Total Columns** | 57 columns (27 predictors + 30 prohibited/metadata) | Verified |
| **Modification Policy** | Zero rows modified; zero columns renamed; source Parquet untouched | Preserved |

---

## 3. Canonical 27 Predictor Whitelist & Feature Audit

All candidate predictors were verified against the canonical 27-feature whitelist codified in `backend/app/ml/baseline_modeling.py` (lines 72–104) and documented in `docs/ML_BASELINE_MODELING_AUDIT.md` (lines 125–155):

### Dynamic Antecedent Meteorology ($[t-30, t-1]$ Lookback)
1. `precip_1d_mm`: Antecedent 1-day cumulative rainfall (mm).
2. `precip_3d_sum_mm`: Antecedent 3-day cumulative rainfall $[t-3, t-1]$ (mm).
3. `precip_7d_sum_mm`: Antecedent 7-day cumulative rainfall $[t-7, t-1]$ (mm).
4. `precip_14d_sum_mm`: Antecedent 14-day cumulative rainfall $[t-14, t-1]$ (mm).
5. `precip_30d_sum_mm`: Antecedent 30-day cumulative rainfall $[t-30, t-1]$ (mm).
6. `precip_7d_max_mm`: Maximum 1-day rainfall peak within $[t-7, t-1]$ (mm).
7. `precip_14d_max_mm`: Maximum 1-day rainfall peak within $[t-14, t-1]$ (mm).
8. `temp_mean_1d_c`: Antecedent 1-day mean 2m temperature (°C).
9. `temp_min_1d_c`: Antecedent 1-day minimum 2m temperature (°C).
10. `temp_max_1d_c`: Antecedent 1-day maximum 2m temperature (°C).
11. `temp_7d_mean_c`: Antecedent 7-day rolling mean temperature (°C).
12. `rh_mean_1d_pct`: Antecedent 1-day mean relative humidity (%).
13. `rh_7d_mean_pct`: Antecedent 7-day rolling mean relative humidity (%).
14. `pressure_mean_1d_hpa`: Antecedent 1-day mean surface barometric pressure (hPa).

### Static Zonal Terrain (Copernicus DEM GLO-30)
15. `elevation_mean_m`: District-wide area-weighted mean ground elevation (meters).
16. `elevation_min_m`: District minimum ground elevation (meters).
17. `elevation_max_m`: District maximum ground elevation (meters).
18. `elevation_std_m`: District topographic roughness / elevation standard deviation (meters).
19. `slope_mean_deg`: District mean terrain slope gradient (degrees).
20. `slope_max_deg`: District maximum terrain slope gradient (degrees).

### Static Hydrological GIS (CWC Basins & HydroBASINS Level-7)
21. `major_basin_count`: Count of CWC statutory major river basins intersecting district.
22. `primary_basin_coverage_pct`: Proportion of district drained by primary basin (%).
23. `sub_basin_count`: Count of HydroBASINS Level-7 sub-catchments.
24. `mean_upstream_area_km2`: Area-weighted upstream contributing drainage area ($km^2$).

### Spatial & Calendar Context
25. `weather_cell_count`: Count of 0.25° ERA5 grid cells intersecting district (district area proxy).
26. `day_of_year`: Calendar day of year (1–366) capturing seasonal monsoon cycle.
27. `target_month`: Calendar month index (1–12).

### Specific Audit of `target_month`
- **Origin**: `target_month` was introduced in Phase 4.1/4.2 feature matrix construction (`docs/ML_FEATURE_DATA_AUDIT.md`, line 81) as a calendar coordinate alongside `day_of_year`.
- **Inclusion Rationale**: Formally codified in `CANONICAL_PREDICTOR_COLUMNS` (`baseline_modeling.py`, line 103) as the 27th predictor to model monthly seasonal transitions.
- **Leakage Analysis**: Does NOT leak target outcome. The calendar month of date $t$ is fully known at forecast issue time (00:00 UTC of date $t$).
- **Methodological Caveat**: The `target_` prefix causes semantic ambiguity with target ground-truth variables (`flood_occurrence`, `target_date`, `target_year`, `target_day`). Furthermore, its seasonal information is largely colinear with `day_of_year`.
- **Audit Decision**: Maintained as part of the canonical 27-predictor whitelist for exact schema parity with historical baseline modeling (`ML_BASELINE_MODELING_AUDIT.md`).

---

## 4. Forbidden Column Rejection & Anti-Leakage Separation

All 30 non-predictor columns were strictly isolated:
- **Target Variables**: `flood_occurrence`, `label_state`
- **Disaster Event Impact Metadata (Target Leakage Hazard)**: `event_count`, `source_event_ids`, `main_causes`, `severities`, `fatalities`, `displaced`
- **Spatial & Temporal Identifiers**: `district_id`, `kgis_district_code`, `lgd_district_code`, `district_name`, `target_date`, `target_year`, `target_day`, `prediction_anchor_utc`
- **Window Boundaries**: `feature_window_start`, `feature_window_end`, `lead_time_days`
- **Quality & Provenance Flags**: `is_weather_complete_1d`, `is_weather_complete_30d`, `valid_weather_days_30d`, `terrain_coverage_pct`, `primary_basin_name`, `feature_version`, `source_era5`, `source_ifi`, `source_dem`, `source_hydro`, `source_admin`

---

## 5. Target Semantics & Positive-Unlabeled (PU) Methodology

### Three-State Semantics
```text
FLOOD      -> s = 1 (Verified positive flood occurrence in IFI v3.0, n = 13,156)
UNKNOWN    -> s = 0 (Unrecorded observation day, n = 128,142 active)
NO_FLOOD   -> n = 0 (Zero confirmed negative ground-truth logs exist statewide)
```

### Critical Scientific Correction: SCAR Assumption is NOT VALIDATED
In standard PU literature, Selected At Random (SCAR) posits that the labeling probability for positive events is independent of features:
$$P(S=1 \mid X, Y=1) = P(S=1 \mid Y=1) = c$$

**Formal Audit Finding:**
```text
SCAR ASSUMPTION: NOT VALIDATED
```
- The India Flood Inventory (IFI v3.0) is an administrative and meteorological disaster archive derived from IMD, SDMA, and news/satellite reporting.
- **Reporting Bias**: Major urban districts (e.g. Bengaluru, Dakshina Kannada) with dense sensor coverage, infrastructure, and media presence have a significantly higher probability of flood events being recorded than remote rural agricultural districts.
- **Severity Bias**: Catastrophic high-fatality or infrastructure-damaging floods have a near 100% recording rate, whereas moderate local inundations or agricultural waterlogging often go unrecorded.
- **Temporal Inconsistency**: Reporting completeness is non-stationary across 2011–2023 (denser reporting in 2018–2020 vs earlier years).
- **Conclusion**: $P(S=1 \mid X, Y=1)$ depends strongly on geography, population, and severity. **SCAR cannot be assumed.**

---

## 6. Chronological Experiment Partitions

To eliminate temporal and spatial event leakage, splits were strictly partitioned chronologically:

```
[2011-01-31 ────────── 2019-12-31] │ [2020-01-01 ── 2021-12-31] │ [2022-01-01 ── 2023-07-24] │ [2023-07-25 ── 2025-12-31]
           TRAIN SET               │      VALIDATION SET         │        TEST SET             │   FORWARD INFERENCE
        (100,967 rows)             │      (22,661 rows)          │     (17,670 rows)           │    (27,621 rows)
        4,628 floods (4.58%)       │     8,408 floods (37.10%)   │     120 floods (0.68%)      │      ZERO LABELS
```

- **Train**: Captures baseline monsoon dynamics, including 2018–2019 floods.
- **Validation**: High-prevalence stress regime (historic 2020 multi-basin floods). Used to discover the decision threshold.
- **Held-Out Test**: Low-prevalence, strictly unseen future test period (2022–2023). Evaluated using the validation-discovered threshold.
- **Forward Inference**: 2023-07-25 to 2025-12-31 contains complete weather features but zero labels; excluded from supervised evaluation.

---

## 7. Model Configurations

### Model 1: Logistic Regression Baseline
- Algorithm: L2-penalized Logistic Regression (`scikit-learn 1.9.1`).
- Preprocessing: `StandardScaler` fitted **strictly on Train partition**.
- Hyperparameters: $C=1.0$, `solver='lbfgs'`, `max_iter=1000`, `class_weight='balanced'`, `random_state=42`.
- Zero hyperparameter search.

### Model 2: Random Forest Baseline
- Algorithm: Non-linear tree ensemble (`scikit-learn 1.9.1`).
- Hyperparameters: `n_estimators=100`, `max_depth=10`, `min_samples_leaf=5`, `class_weight='balanced_subsample'`, `random_state=42`, `n_jobs=-1`.
- Zero hyperparameter search.

---

## 8. Empirical Performance Metrics (PU Proxy Evaluation)

### Critical Distinction: PU Proxy Evaluation vs True Binary Classification
Because verified $\text{NO\_FLOOD} = 0$, all metrics evaluated against $S \in \{0, 1\}$ (where $0 = \text{UNKNOWN}$) are **PU proxy metrics**:
- **Proxy PR-AUC / ROC-AUC**: Measures continuous ranking separation between cataloged flood events ($P$) and background district-days ($U$).
- **Observed-Positive Recall**: Measures recall strictly on **documented IFI catalog events**, NOT all real-world floods.
- **Empirical Precision Lower Bound**: $\frac{TP}{TP + FP_u}$ treats all unlabeled predictions as false positives, providing a conservative lower bound on precision under the assumption that some unlabeled days experienced unrecorded flooding.

### Validation Split (2020–2021, n = 22,661, 8,408 Documented Positives, Observed Prevalence = 37.10%)

| Metric | Logistic Regression | Random Forest | Mathematical Definition & Scientific Interpretation |
| :--- | :---: | :---: | :--- |
| **PU Proxy PR-AUC** | 0.4320 | **0.4513** | Average precision against $S$. Exceeds observed prevalence baseline (0.3710). |
| **PU Proxy ROC-AUC** | **0.6041** | 0.5926 | Probability that a documented flood day receives a higher score than a random UNKNOWN day. |
| **Proxy Brier Score** | **0.2484** | 0.2768 | Mean squared error against proxy indicator $S$. |
| **Decision Threshold** | 0.2154 | 0.0251 | Discovered by optimizing empirical F1 on validation observed positives. |
| **Observed-Positive Recall** | **95.03%** (7,990 / 8,408) | 89.85% (7,555 / 8,408) | Fraction of documented IFI flood events detected in validation period. |
| **Empirical Precision (Lower Bound)** | **41.43%** | 39.55% | Conservative lower bound: $\frac{TP}{TP + FP_u}$. |
| **Empirical F1 Score** | **0.5770** | 0.5493 | Harmonic mean of observed recall and empirical precision lower bound. |
| **Empirical F2 Score** | **0.7550** | 0.7164 | Prioritizes observed flood recall over proxy false alarms ($\beta=2$). |
| **Lee-Liu PU Criterion** | **1.0611** | 0.9579 | PU heuristic: $\frac{\text{Recall}^2}{P(\hat{Y}=1)}$. Evaluates models without true negatives. |
| **Elkan-Noto $\hat{c}$ (Heuristic)** | 0.4786 | 0.2958 | Average model confidence on observed positives ($\frac{1}{|P|} \sum_{i \in P} \hat{p}_i$). |
| **Accuracy** | *NOT APPLICABLE* | *NOT APPLICABLE* | Invalid: treats all UNKNOWN observations as true negatives. |
| **Specificity** | *NOT APPLICABLE* | *NOT APPLICABLE* | Invalid: zero verified negative labels exist. |

### Held-Out Test Split (2022–2023, n = 17,670, 120 Documented Positives, Observed Prevalence = 0.68%)

| Metric | Logistic Regression | Random Forest | Mathematical Definition & Scientific Interpretation |
| :--- | :---: | :---: | :--- |
| **PU Proxy PR-AUC** | **0.0531** | 0.0154 | Substantially exceeds random background prevalence (0.0068 = 0.68%). |
| **PU Proxy ROC-AUC** | **0.7906** | 0.7013 | Strong continuous ranking signal on unseen future years. |
| **Proxy Brier Score** | 0.2181 | **0.1310** | Lower proxy Brier error on low-prevalence test window. |
| **Applied Threshold** | 0.2154 (from Val) | 0.0251 (from Val) | Strict zero-leakage threshold application from Validation. |
| **Observed-Positive Recall** | **100.0%** (120 / 120) | 98.33% (118 / 120) | Detected 120/120 (LR) and 118/120 (RF) documented IFI events. |
| **Empirical Precision (Lower Bound)** | 0.82% | 0.81% | Bounded by catalog sparsity in 2022–2023 and high-sensitivity threshold. |
| **Empirical F1 Score** | **0.0163** | 0.0160 | Bounded by sparse catalog reporting in test period. |
| **Empirical F2 Score** | **0.0398** | 0.0391 | Reflects near-complete recall on documented events. |
| **Lee-Liu PU Criterion** | **1.2104** | 1.1699 | Ranking performance on test partition. |
| **Elkan-Noto $\hat{c}$ (Heuristic)** | 0.6502 | 0.4246 | Average model score on documented test flood events. |

---

## 9. Threshold Selection Audit

### How Thresholds Were Selected
- **Validation-Only Discovery**: Decision thresholds ($0.2154$ for Logistic Regression, $0.0251$ for Random Forest) were selected by scanning the precision-recall curve on the **Validation set only** to maximize empirical F1 on observed positives.
- **Zero Test Influence**: Test set features, labels, and outcomes had **zero influence** on threshold selection (verified by unit test `test_13_test_labels_cannot_influence_threshold_selection`).
- **Critical Limitation of PU-Derived Threshold**:
  - The threshold was optimized against $S_{\text{val}}$ (where UNKNOWN is proxy 0).
  - Because UNKNOWN contains many high-rainfall days that were not cataloged in IFI v3.0, the optimizer chose an extremely low threshold ($0.0251$ for RF, $0.2154$ for balanced LR) to avoid missing any cataloged events.
  - Applying this low threshold to the test period produces high observed recall ($100\%$ and $98.33\%$), but labels $14,478$ (LR) and $14,486$ (RF) UNKNOWN days as predicted floods.
  - **The threshold must NOT be interpreted as a calibrated probability of real-world flooding.**

---

## 10. Feature Importance & Coefficient Interpretability

### Logistic Regression: Standardized Coefficients ($\beta_j$)

Standardized coefficients indicate change in log-odds of a flood observation per 1 standard deviation increase:

| Rank | Feature Name | Category | Coefficient ($\beta_j$) | Direction | Physical / Associative Interpretation |
| :---: | :--- | :---: | :---: | :---: | :--- |
| 1 | `day_of_year` | Calendar | **-1.0754** | NEGATIVE | Cyclical timing relative to onset/retreat of Southwest monsoon |
| 2 | `target_month` | Calendar | **+0.6025** | POSITIVE | Seasonal concentration in summer monsoon months (June–October) |
| 3 | `pressure_mean_1d_hpa` | Weather | **-0.5338** | NEGATIVE | Low atmospheric surface pressure indicates cyclonic depressions & heavy rain |
| 4 | `rh_7d_mean_pct` | Weather | **+0.5139** | POSITIVE | High antecedent moisture saturation creates soil runoff conditions |
| 5 | `rh_mean_1d_pct` | Weather | **+0.4861** | POSITIVE | Immediate high humidity precedes active precipitation |
| 6 | `elevation_mean_m` | Terrain | **-0.4200** | NEGATIVE | Lower elevation districts (coastal plains, river valleys) accumulate floodwaters |
| 7 | `temp_mean_1d_c` | Weather | **+0.3985** | POSITIVE | Warm tropical airmass temperature |
| 8 | `temp_min_1d_c` | Weather | **-0.3831** | NEGATIVE | Cooler nighttime temperatures associated with persistent cloud cover |
| 9 | `major_basin_count` | Hydro | **+0.3657** | POSITIVE | Multiple intersecting basins increase riverine flood convergence |
| 10 | `precip_14d_sum_mm` | Weather | **+0.2883** | POSITIVE | Medium-term antecedent rainfall builds watershed saturation |
| 11 | `mean_upstream_area_km2`| Hydro | **+0.2819** | POSITIVE | Large upstream catchment area routes heavy discharge downstream |
| 12 | `temp_7d_mean_c` | Weather | **+0.2269** | POSITIVE | Persistent monsoon airmass temperature |
| 13 | `elevation_min_m` | Terrain | **-0.2054** | NEGATIVE | Low minimum terrain level increases depression inundation risk |
| 14 | `slope_mean_deg` | Terrain | **+0.2021** | POSITIVE | Steep slopes in Western Ghats headwaters generate rapid runoff |
| 15 | `precip_1d_mm` | Weather | **+0.1506** | POSITIVE | 1-day antecedent storm rainfall directly triggers local inundation |
| 16 | `precip_30d_sum_mm` | Weather | **+0.1006** | POSITIVE | Long-term soil saturation index |

*Correlation vs Causation*: These coefficients represent observational statistical associations in the ERA5/IFI record. They do not demonstrate direct hydrodynamic causality without hydraulic flood routing.

### Random Forest: Feature Importances (Gini Impurity)

Top 10 most influential features in Random Forest tree splits:
1. `slope_max_deg` (10.02%): Maximum terrain slope in the district.
2. `elevation_min_m` (8.61%): Minimum district elevation (sea-level coastal lowlands).
3. `day_of_year` (7.98%): Annual seasonal cycle.
4. `slope_mean_deg` (5.88%): Average terrain gradient.
5. `precip_30d_sum_mm` (5.74%): 30-day cumulative antecedent rainfall.
6. `mean_upstream_area_km2` (4.77%): Upstream catchment area.
7. `target_month` (4.68%): Calendar month.
8. `pressure_mean_1d_hpa` (3.95%): Surface barometric pressure.
9. `precip_14d_max_mm` (3.77%): Peak rainfall event in antecedent 14 days.
10. `elevation_std_m` (3.75%): Topographic roughness across the district.

---

## 11. Scientific Validity of Phase 5.4 Evaluation

This dedicated scientific validity audit formally governs the interpretation of all Phase 5.4 results:

1. **Zero Verified Negative Labels**:
   - The dataset contains exactly 0 confirmed negative (`NO_FLOOD`) ground truth labels.
   - No government agency publishes daily verified "no-flood" logs for every district in Karnataka.
2. **IFI Reporting Bias (SCAR is NOT Established)**:
   - The India Flood Inventory is an administrative disaster event archive, not a continuous scientific flood sensor.
   - It is not a uniform or random sample of all flood occurrences across Karnataka.
   - Selected At Random (SCAR) does not hold.
3. **UNKNOWN ≠ NO_FLOOD**:
   - Unrecorded days (`UNKNOWN`) represent unlabeled observations, NOT verified dry days.
   - Treating UNKNOWN as true negative introduces severe label noise.
4. **Proxy Evaluation Nature of Metrics**:
   - Reported PR-AUC, ROC-AUC, and Brier scores measure separation between cataloged disaster events ($P$) and unrecorded background days ($U$).
   - They must NOT be cited as standard binary classification performance against real-world truth.
5. **Catalogue-Conditioned Recall Interpretation**:
   - The 100% test recall achieved by Logistic Regression (120/120) and 98.33% by Random Forest (118/120) refers strictly to **documented IFI catalog events**.
   - It is **NOT evidence of 100% real-world flood detection**.
6. **Calibration and Probability Limitations**:
   - Model outputs are continuous PU scoring indices $g(X)$, NOT calibrated physical probabilities of inundation.
   - Calibration cannot be validated without an independent verified negative baseline.
7. **No Claims of Production Readiness**:
   - These models establish transparent empirical baselines. They are NOT ready for emergency operational deployment.

---

## 12. Reproducibility & Model Verification

1. **Exact Reproducibility**: Running `runner.py` with identical source data produces identical predictions, thresholds, and metrics down to floating-point precision (verified by automated test `test_09`).
2. **Serialized Model Artifacts**:
   - `models/experiments/phase_5_4/logistic_regression/model_pipeline.joblib`
   - `models/experiments/phase_5_4/logistic_regression/experiment_metadata.json`
   - `models/experiments/phase_5_4/random_forest/model_pipeline.joblib`
   - `models/experiments/phase_5_4/random_forest/experiment_metadata.json`
3. **Automated Test Coverage**: 15 unit tests in `backend/tests/test_experiment_baseline.py` guarantee feature whitelist compliance, temporal causality, threshold isolation, and metric classification.

---

## 13. What Should Happen Next (Phase 5.5 Recommendation)

Before training advanced models:
1. **Explore Non-SCAR PU Formulations**:
   - Investigate SarPU (Selected at Random with Feature Dependency) or Positive-Unlabeled bagging to handle reporting bias.
2. **High-Confidence Negative Conditioning (Meteorological Dry Baselines)**:
   - Identify verifiable negative periods (e.g. statewide peak dry season Jan–March, 30-day rain $< 1.0\text{ mm}$, zero river alerts) to benchmark true binary specificity.
3. **Domain-Constrained Tree Baselines**:
   - Benchmark LightGBM / XGBoost with monotonic constraints on cumulative rainfall features.
