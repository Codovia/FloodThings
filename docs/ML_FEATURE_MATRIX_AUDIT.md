# Historical ML Feature Matrix Quality Audit (Phase 4)

## 1. Executive Summary & Verification State

This audit document details the construction, validation, and quality assessment of the canonical **District × Day Historical Machine Learning Feature Matrix** for the FloodPrediction project (Phase 4).

### Key Dataset Metrics
| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Prediction Unit** | **DISTRICT × DAY** | Canonical spatial unit of analysis |
| **Total Observation Rows** | **73,222** | District × Day samples |
| **Temporal Span** | **1969-07-14 to 1975-12-31** | 2,362 calendar dates |
| **Administrative Districts** | **31** | 100% of KSR-SAC / KGIS districts |
| **Positive Labels (`FLOOD = 1`)** | **546** | Grounded in IFI v3.0 disaster observations |
| **Negative Labels (`NO_FLOOD = 0`)** | **0** | Strict 3-state contract (no unevidenced imputation) |
| **Unknown Labels (`UNKNOWN = NULL`)** | **72,676** | Unobserved non-event dates preserved as NULL |
| **Weather Feature Completeness (1d)** | **73,222 / 73,222 (100.0%)** | Zero missing 1-day antecedent weather |
| **Weather Feature Completeness (30d)** | **73,222 / 73,222 (100.0%)** | All 30-day lookback windows complete |
| **Terrain Statistics Coverage** | **73,222 / 73,222 (100.0%)** | Joined from `terrain_statistics` |
| **Hydrological GIS Coverage** | **73,222 / 73,222 (100.0%)** | Joined from `district_river_basins` & `sub_basins` |
| **Temporal Leakage Audit** | **PASSED (0 violations)** | Enforced 24h lead time ($t-1 \to t$) |
| **Analytical Output Artifact** | `data/processed/ml_matrix/district_day_feature_matrix.parquet` | 3.2 MB Snappy-compressed Parquet (Gitignored) |

---

## 2. Investigation and Resolution of ERA5 Scope Discrepancy

### 2.1 Context and Initial Report
The project was presented with a reported state of:
- **826 / 827 chunks SUCCEEDED**, 0 FAILED.
- Canonical project scope historically established as **858 chunks**.

### 2.2 Investigation Findings
An exhaustive inspection of `data/raw/era5_historical/extraction_manifest.json`, the canonical chunk generator `backend/app/ingestion/historical/grid.py`, and raw artifact directories on disk revealed:

1. **Canonical Scope Calculation**:
   - Temporal span: **26 calendar years** (1969 through 1994).
   - Spatial grid: **324 authoritative Karnataka cells**, partitioned into **33 fixed batches** (32 batches of 10 cells, 1 batch of 4 cells; 318 extraction-eligible cells).
   - Expected canonical chunk count:
     $$\text{Total Chunks} = 26 \text{ years} \times 33 \text{ batches} = 858 \text{ chunks}$$
   - **858 is the strictly correct canonical scope.**

2. **Root Cause of the 827 Report**:
   - The reported count of 827 was an intermediate snapshot captured during the execution of the final year (1994).
   - Prior to year 1994, 25 years (1969–1993) had completed:
     $$25 \text{ years} \times 33 \text{ batches} = 825 \text{ chunks}$$
   - When the snapshot was taken, batches 1 and 2 of 1994 had just completed:
     $$825 + 2 = 827 \text{ chunks}$$
   - The extraction process continued autonomously and sequentially processed batches 3 through 33 of 1994, completing the final batch (`era5_1994_batch_033`) on **2026-09-25 at 04:38:11 UTC**.

3. **Current Verified Disk & Manifest State**:
   - Manifest chunks: **858 / 858 SUCCEEDED (100.0%)**, 0 FAILED, 0 PENDING.
   - Files on disk matching `data/raw/era5_historical/year=*/batch_*.json.gz`: **exactly 858**.
   - Missing files referenced in manifest: **0**.
   - Unregistered chunk files on disk: **0**.
   - Raw directory git status: **Clean, untouched**.

---

## 3. Spatial Aggregation Architecture (Grid to District)

ERA5 reanalysis observations are provided on a regular 0.25° geographic grid ($\approx 27.75 \text{ km} \times 27.75 \text{ km}$ cells), whereas disaster flood events are cataloged by administrative district.

### 3.1 Geometric Area-Weighting Method
1. **Grid Cell Geometries**:
   For each cell center $(\lambda_c, \phi_c)$, its spatial envelope is:
   $$\text{Envelope}_c = [\lambda_c - 0.125^\circ, \phi_c - 0.125^\circ, \lambda_c + 0.125^\circ, \phi_c + 0.125^\circ]$$

2. **Intersection & Normalization**:
   For each district $d$ with boundary polygon $P_d$ from KSR-SAC:
   $$A_{d, c} = \text{Area}(P_d \cap \text{Envelope}_c)$$
   The normalized spatial weight $w_{d, c}$ is:
   $$w_{d, c} = \frac{A_{d, c}}{\sum_{c'} A_{d, c'}} \quad \text{such that} \quad \sum_{c} w_{d, c} = 1.000000$$

3. **Quality & Incompleteness Threshold**:
   For each day $s$, the available complete cell weight is evaluated:
   $$W_{\text{valid}}(d, s) = \sum_{c \in \text{Complete}} w_{d, c}$$
   - If $W_{\text{valid}}(d, s) \ge 0.95$, the district day is marked complete, and values are scaled by $1 / W_{\text{valid}}$.
   - If $W_{\text{valid}}(d, s) < 0.95$, the district day is marked **incomplete**, and all weather features evaluate to `NaN` (no silent imputation).

### 3.2 District Spatial Weights Statistics
- Number of districts: **31**
- Number of intersecting eligible ERA5 cells: **318**
- Maximum cells per district: **37 cells** (Belagavi, largest district)
- Minimum cells per district: **8 cells** (Bangalore Urban, smallest district)
- Precomputed weights cache: `data/processed/gis_cache/district_era5_weights.json`

---

## 4. Temporal Alignment and Causality Guarantees

### 4.1 Prediction Horizon
- **Target Unit**: Flood occurrence in district $d$ on calendar day $t$ (00:00 UTC to 23:59 UTC).
- **Prediction Anchor**: Day $t$ at 00:00 UTC.
- **Lead Time**: 24 hours ($L = 1 \text{ day}$).
- **Feature Window**: Weather observed strictly up to day $t-1$:
  $$\text{Feature Window} = [t - 30, t - 1]$$

### 4.2 Anti-Leakage Constraints
1. **Target-Day Weather Isolation**:
   Weather observations on day $t$ are strictly forbidden from entering predictor features for target day $t$.
2. **Backward-Looking Rolling Windows**:
   - 1-day: observation at $t-1$.
   - 3-day: sum over $[t-3, t-1]$.
   - 7-day: sum / max / mean over $[t-7, t-1]$.
   - 14-day: sum / max over $[t-14, t-1]$.
   - 30-day: sum over $[t-30, t-1]$.
3. **Missingness Propagation**:
   If any day in $[t-W, t-1]$ is incomplete or missing, the rolling aggregation evaluates strictly to `NaN` (zero silent zero-filling, zero interpolation).

---

## 5. Feature Schema & Column Definitions

The canonical matrix contains 54 columns organized into 6 semantic groups:

### Group 1: Spatiotemporal Coordinates & Anchors
- `district_id`: PostGIS UUID primary key.
- `kgis_district_code`: Authoritative KSR-SAC code ("01" to "31").
- `lgd_district_code`: MoPR Local Government Directory code ("524" to "738").
- `district_name`: Canonical district name (e.g. "Bagalkote", "Belagavi").
- `target_date`: Calendar date of prediction target (YYYY-MM-DD).
- `target_year`, `target_month`, `target_day`, `day_of_year`: Calendar decomposition.
- `prediction_anchor_utc`: Timestamp anchor (e.g. "1970-07-15T00:00:00Z").
- `lead_time_days`: Forecast lead time (1).
- `feature_window_start`, `feature_window_end`: Exact observation window ($t-30$ to $t-1$).

### Group 2: Target & Disaster Labels (Three-State Semantics)
- `flood_occurrence`: Target binary label (`1` for FLOOD, `0` for verified NO_FLOOD, `NULL` for UNKNOWN).
- `label_state`: Categorical label state (`FLOOD`, `NO_FLOOD`, `UNKNOWN`).
- `event_count`: Number of overlapping IFI disaster events on day $t$.
- `source_event_ids`: JSON array of source IFI UEI identifiers.
- `main_causes`: JSON array of reported disaster causes.
- `severities`: JSON array of reported disaster severities.
- `fatalities`, `displaced`: Recorded impact numbers.

### Group 3: ERA5 Dynamic Meteorological Features ($[t-W, t-1]$)
- `precip_1d_mm`: Precipitation on day $t-1$ (mm).
- `precip_3d_sum_mm`: 3-day antecedent rainfall $[t-3, t-1]$ (mm).
- `precip_7d_sum_mm`: 7-day antecedent rainfall $[t-7, t-1]$ (mm).
- `precip_14d_sum_mm`: 14-day antecedent rainfall $[t-14, t-1]$ (mm).
- `precip_30d_sum_mm`: 30-day antecedent rainfall $[t-30, t-1]$ (mm).
- `precip_7d_max_mm`: Maximum 1-day rainfall within prior 7 days (mm).
- `precip_14d_max_mm`: Maximum 1-day rainfall within prior 14 days (mm).
- `temp_mean_1d_c`: Mean 2m temperature on day $t-1$ (°C).
- `temp_min_1d_c`: Minimum 2m temperature on day $t-1$ (°C).
- `temp_max_1d_c`: Maximum 2m temperature on day $t-1$ (°C).
- `temp_7d_mean_c`: Mean 2m temperature over prior 7 days (°C).
- `rh_mean_1d_pct`: Mean relative humidity on day $t-1$ (%).
- `rh_7d_mean_pct`: Mean relative humidity over prior 7 days (%).
- `pressure_mean_1d_hpa`: Mean surface pressure on day $t-1$ (hPa).

### Group 4: Quality & Missingness Indicators
- `is_weather_complete_1d`: Boolean indicator of day $t-1$ weather validity.
- `is_weather_complete_30d`: Boolean indicator of complete 30-day antecedent sequence.
- `valid_weather_days_30d`: Integer count of valid days in $[t-30, t-1]$ (max 30).
- `weather_cell_count`: Number of grid cells intersecting this district.

### Group 5: Static Terrain & Hydrological GIS Features
- `elevation_mean_m`, `elevation_min_m`, `elevation_max_m`, `elevation_std_m`: Zonal elevation statistics from Copernicus DEM GLO-30.
- `slope_mean_deg`, `slope_max_deg`: Horn (1981) metric slope statistics.
- `terrain_coverage_pct`: DEM valid pixel coverage (100.0%).
- `major_basin_count`: Count of CWC statutory major basins.
- `primary_basin_name`: Name of largest intersecting river basin.
- `primary_basin_coverage_pct`: District area percentage in primary river basin.
- `sub_basin_count`: Count of HydroBASINS Level-7 sub-catchments.
- `mean_upstream_area_km2`: Area-weighted upstream drainage area (km²).

### Group 6: Provenance & Versioning
- `feature_version`: Pipeline version ("1.0.0").
- `source_era5`, `source_ifi`, `source_dem`, `source_hydro`, `source_admin`: Authoritative lineage strings.

---

## 6. Three-State Label Semantics & Observation Window Audit

### 6.1 Three-State Semantics
- **FLOOD (`1`)**: Positive, evidenced disaster event recorded in IFI v3.0.
- **NO_FLOOD (`0`)**: Explicitly confirmed absence of flood during an active, exhaustive monitoring period.
- **UNKNOWN (`NULL`)**: Unevidenced date where no observation is confirmed.

> [!IMPORTANT]
> **Zero Negative Label Fabrication**:
> Unrecorded dates in IFI do NOT automatically become `flood_occurrence = 0`. Converting unrecorded dates to negative labels creates severe label noise because IFI is an event catalog, not an exhaustive daily gauge monitoring system. All 72,676 unrecorded dates in the canonical dataset remain strictly `UNKNOWN` (`NULL`).

### 6.2 Label Distribution (1969-07-14 to 1975-12-31)
- `FLOOD`: **546 rows (0.75%)**
- `NO_FLOOD`: **0 rows (0.00%)**
- `UNKNOWN`: **72,676 rows (99.25%)**
- Total: **73,222 rows (100.0%)**

### 6.3 Spatial Distribution of Positive Events (Top Districts)
1. **Dakshina Kannada**: 67 flood days
2. **Uttara Kannada**: 65 flood days
3. **Udupi**: 58 flood days
4. **Shivamogga**: 52 flood days
5. **Kodagu**: 48 flood days
6. **Belagavi**: 35 flood days
*(Reflects known Western Ghats and coastal monsoon hydrology).*

---

## 7. Automated Temporal Leakage Audit Results

The feature matrix was subjected to the `TemporalLeakageAuditor` automated validation suite before disk serialization.

| Check | Requirement | Result | Status |
| :--- | :--- | :--- | :--- |
| **Window Boundary Check** | $\text{feature\_window\_end} < \text{target\_date}$ | $\text{target\_date} - \text{feature\_window\_end} = 1 \text{ day}$ | **PASSED** |
| **Lead Time Check** | $\text{lead\_time\_days} = 1$ | Exactly 1 day across all 73,222 rows | **PASSED** |
| **Window Start Check** | $\text{feature\_window\_start} \le \text{feature\_window\_end}$ | $\Delta = 29 \text{ days}$ (30-day window) | **PASSED** |
| **Same-Day Isolation Check** | Target day weather not in features | Feature window strictly terminates at $t-1$ | **PASSED** |
| **Uniqueness Check** | Unique `(district_id, target_date)` | 73,222 unique pairs, 0 duplicates | **PASSED** |
| **Label Timing Check** | Target label matches target day $t$ | Grounded strictly at date $t$ | **PASSED** |
| **Three-State Compliance** | UNKNOWN has `target_value=None` | 72,676 UNKNOWN rows have `flood_occurrence=None` | **PASSED** |

---

## 8. Verification & Test Suite Summary

The feature matrix pipeline is verified by a dedicated test suite in [`backend/tests/test_district_feature_matrix.py`](file:///home/pioneer/Projects/FloodPrediction/backend/tests/test_district_feature_matrix.py):

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_01_district_day_uniqueness` | Duplicate rows raise `TemporalLeakageError` | **PASSED** |
| `test_02_correct_ifi_label_alignment` | Positive flood rows preserve event counts, causes, severities | **PASSED** |
| `test_03_unknown_is_never_converted_to_no_flood` | Arbitrary zero-filling of UNKNOWN is rejected | **PASSED** |
| `test_04_leap_year_dates` | Leap day (Feb 29) handled correctly across windows | **PASSED** |
| `test_05_missing_era5_days_propagate_to_none` | Missing days propagate to `None` in rolling sums | **PASSED** |
| `test_06_partial_era5_days_marked_incomplete` | Coverage $<95\%$ marks weather incomplete | **PASSED** |
| `test_07_rolling_window_correctness` | Mathematical precision of 1d, 3d, 7d, 14d, 30d windows | **PASSED** |
| `test_08_no_future_feature_leakage` | Features leaking into target day raise `TemporalLeakageError` | **PASSED** |
| `test_09_spatial_aggregation` | District weights sum to 1.000000; area-weighted mean exact | **PASSED** |
| `test_10_terrain_join` | Zonal statistics joined accurately from `terrain_statistics` | **PASSED** |
| `test_11_hydrological_join` | Basin and sub-basin attributes joined accurately | **PASSED** |
| `test_12_provenance_preservation` | Version and source dataset metadata retained | **PASSED** |
| `test_13_deterministic_output` | Deterministic sorting by `(district_id, target_date)` | **PASSED** |
| `test_14_re_running_pipeline_produces_identical_results` | Pipeline execution is idempotent and reproducible | **PASSED** |
| `test_15_era5_artifact_isolation` | Raw ERA5 files and manifests are strictly untouched | **PASSED** |

---

## 9. Readiness Assessment for ML Training (Phase 5)

The historical feature matrix is **structurally complete, temporally leak-free, and validated**.

> [!CAUTION]
> **STOP: DO NOT TRAIN YET**
> Per Phase 4 instructions, machine learning model training (Random Forest, XGBoost, Neural Networks, hyperparameter tuning) has **NOT** been performed. The dataset is staged in Parquet format ready for Phase 5 (Baseline Modeling & Cross-Validation Strategy).
