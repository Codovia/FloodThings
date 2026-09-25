# Phase 4.1: Historical ML Feature Matrix Audit & Temporal Alignment

**Project:** FloodPulse  
**Phase:** Phase 4.1 — Historical ML Feature Matrix Audit & Temporal Alignment  
**Date:** 2026-09-25  
**Status:** COMPLETE (Audited, Verified, Tested, and Provenance Tracked)

---

## 1. Executive Summary & Authoritative Asset State

Phase 4.1 establishes the leakage-safe, empirically audited foundation for the historical Machine Learning feature matrix. In strict adherence to project constraints (`CONSTRAINTS.md`, `DATA_CONTRACT.md`), this audit investigates the real physical artifacts across atmospheric reanalysis (ERA5), disaster ground truth (IFI v3.0), zonal terrain geomorphology (Copernicus DEM GLO-30), and hydrological topology (CWC Statutory Basins & HydroBASINS Level-7).

Zero models were trained. Zero synthetic values were fabricated. Zero negative labels were manufactured.

---

## 2. Authoritative ERA5 Scope Resolution: 858 vs. 827

### 2.1 The Historical Discrepancy
Project reports previously noted an apparent discrepancy between:
* Canonical design scope: **858 chunks** (26 years $\times$ 33 spatial batches).
* Intermediate progress reports: **826/827 chunks**.

### 2.2 Forensic Inspection Findings
An exhaustive inspection of `data/raw/era5_historical/extraction_manifest.json`, the canonical chunk generator `backend/app/ingestion/historical/grid.py`, and the raw file system resolved this discrepancy definitively:

1. **Canonical Scope Formulation**:
   * **Temporal Span**: 26 calendar years (1969 through 1994).
   * **Spatial Grid**: 324 authoritative Karnataka cells, partitioned into 33 spatial batches (32 batches of 10 cells, 1 batch of 4 cells; 318 extraction-eligible cells).
   * **Expected Total**:
     $$\text{Total Chunks} = 26 \text{ years} \times 33 \text{ batches} = 858 \text{ chunks}$$
   * **858 is the sole authoritative canonical scope.**

2. **Root Cause of the 827 Report**:
   * The "827" figure was an intermediate progress snapshot captured during the execution of the final calendar year (1994).
   * Prior to 1994, 25 years had completed: $25 \times 33 = 825$ chunks.
   * When batches 1 and 2 of 1994 completed, the counter stood at $825 + 2 = 827$.
   * The background extraction process continued autonomously and sequentially completed batches 3 through 33 of 1994, concluding with chunk `era5_1994_batch_033` on **2026-09-25 at 04:38:11 UTC**.

3. **Current Verified Disk & Manifest State**:
   * Manifest status: **858 / 858 SUCCEEDED (100.0%)**, 0 FAILED, 0 PENDING.
   * Physical files on disk matching `data/raw/era5_historical/year=*/batch_*.json.gz`: **exactly 858**.
   * Missing or corrupt chunks: **0**.
   * Raw extraction directory: **100% clean and untouched**.

---

## 3. Real Data Inventory & Feasibility Assessment

### 3.1 Candidate Feature Inventory

| Feature Name | Source | Database / Artifact | Spatial Res. | Temporal Res. | Temporal Range | Units | Type | Usability | Leakage Risk & Mitigation | Missing Data Policy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `precip_1d_mm` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | Daily ($t-1$) | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | If $<95\%$ cell weight, $\to$ `NaN`. |
| `precip_3d_sum_mm` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 3-day sum $[t-3, t-1]$ | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-3, t-1]$). | Any missing day $\to$ `NaN`. |
| `precip_7d_sum_mm` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 7-day sum $[t-7, t-1]$ | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-7, t-1]$). | Any missing day $\to$ `NaN`. |
| `precip_14d_sum_mm`| ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 14-day sum $[t-14, t-1]$ | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-14, t-1]$). | Any missing day $\to$ `NaN`. |
| `precip_30d_sum_mm`| ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 30-day sum $[t-30, t-1]$ | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-30, t-1]$). | Any missing day $\to$ `NaN`. |
| `precip_7d_max_mm` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 7-day max $[t-7, t-1]$ | 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-7, t-1]$). | Any missing day $\to$ `NaN`. |
| `precip_14d_max_mm`| ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 14-day max $[t-14, t-1]$| 1969–1994 | mm | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-14, t-1]$). | Any missing day $\to$ `NaN`. |
| `temp_mean_1d_c` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | Daily mean ($t-1$) | 1969–1994 | °C | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | Any missing day $\to$ `NaN`. |
| `temp_min_1d_c` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | Daily min ($t-1$) | 1969–1994 | °C | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | Any missing day $\to$ `NaN`. |
| `temp_max_1d_c` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | Daily max ($t-1$) | 1969–1994 | °C | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | Any missing day $\to$ `NaN`. |
| `temp_7d_mean_c` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 7-day mean $[t-7, t-1]$ | 1969–1994 | °C | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-7, t-1]$). | Any missing day $\to$ `NaN`. |
| `rh_mean_1d_pct` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | Daily mean ($t-1$) | 1969–1994 | % | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | Any missing day $\to$ `NaN`. |
| `rh_7d_mean_pct` | ECMWF ERA5 | `data/processed/era5_daily/` | 0.25° grid $\to$ District | 7-day mean $[t-7, t-1]$ | 1969–1994 | % | DERIVED_FROM_REAL | **YES** | Zero (strictly $[t-7, t-1]$). | Any missing day $\to$ `NaN`. |
| `pressure_mean_1d_hpa`| ECMWF ERA5 | `data/processed/era5_daily/`| 0.25° grid $\to$ District | Daily mean ($t-1$) | 1969–1994 | hPa | DERIVED_FROM_REAL | **YES** | Zero (strictly $t-1$). | Any missing day $\to$ `NaN`. |
| `elevation_mean_m` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | m | DERIVED_FROM_REAL | **YES** | None (time-invariant geomorphology).| 100% complete. |
| `elevation_min_m` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | m | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `elevation_max_m` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | m | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `elevation_std_m` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | m | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `slope_mean_deg` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | deg | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `slope_max_deg` | Copernicus DEM | `terrain_statistics` | ~30m zonal $\to$ District | Static | N/A | deg | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `terrain_coverage_pct`| Copernicus DEM| `terrain_statistics` | District polygon | Static | N/A | % | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `major_basin_count`| CWC Statutory | `district_river_basins` | District polygon | Static | N/A | count | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `primary_basin_name`| CWC Statutory | `district_river_basins` | District polygon | Static | N/A | text | DERIVED_FROM_REAL | **YES** (Meta) | Categorical stratification. | 100% complete. |
| `primary_basin_coverage_pct`| CWC Statutory | `district_river_basins` | District polygon | Static | N/A | % | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `sub_basin_count` | HydroBASINS L7 | `district_sub_basins` | District polygon | Static | N/A | count | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `mean_upstream_area_km2`| HydroBASINS L7 | `district_sub_basins` | District polygon | Static | N/A | km² | DERIVED_FROM_REAL | **YES** | None (time-invariant). | 100% complete. |
| `day_of_year`, `target_month` | Calendar Date | Inherent to Target Date | State-wide | Daily | 1969–1975 | int | DERIVED_FROM_REAL | **YES** | Deterministic coordinate. | None missing. |
| `weather_observations` | IMD/Open-Meteo | `weather_observations` | Point stations | Near-realtime | 2024–2026 | Various | REAL | **BLOCKED** | Severe temporal mismatch (0% historical overlap). | Unavailable for 1969–1994. |
| `weather_forecasts` | Open-Meteo NWP | `weather_forecasts` | District | Near-realtime | 2026+ | Various | MODEL_OUTPUT | **BLOCKED** | Forecast issue archives do not exist historically. | Unavailable for 1969–1994. |
| `river_observations` | NWIC CWC | `river_observations` | Station (Akkihebbal)| Operational | 2024+ | m, m³/s| REAL | **BLOCKED** | Only 1 gauge point in Karnataka; no historical series. | Unavailable for 1969–1994. |

---

## 4. Canonical ML Unit of Analysis

* **Option A: District × Day**:
  * **Status**: **Selected & Authoritative**.
  * **Evidence**: Ground truth disaster observations (IFI v3.0) are recorded at calendar-day granularity (`event_date`) for Karnataka administrative districts (`district_id`). Atmospheric reanalysis (ERA5) is available hourly/daily across the entire state from 1969 to 1994.
* **Option B: District × Forecast Issue Time**:
  * **Status**: **Strictly Blocked & Unfeasible**.
  * **Evidence**: Numerical Weather Prediction (NWP) forecast issue cycles (e.g. 00Z/12Z runs) do not exist in historical databases for 1969–1994. The `weather_forecasts` table contains only recent operational forecasts (275 rows from September 2026). Constructing historical forecast issue times would fabricate ungrounded NWP runs.

---

## 5. Prediction Target & Temporal Alignment

### 5.1 Target Definition
* **Prediction Unit**: District $d$ on calendar day $t$.
* **Target Label ($Y_{d,t}$)**:
  $$Y_{d, t} = \begin{cases} 1 & \text{if a verified IFI flood disaster occurred in district } d \text{ on day } t \\ 0 & \text{if explicitly verified non-flood / dry baseline condition exists} \\ \text{NULL} & \text{if unevidenced (UNKNOWN state)} \end{cases}$$
* **Prediction Anchor ($T$)**: 00:00:00 UTC on day $t$.
* **Lead Time ($H$)**: Strictly **24 hours** ($H = 24 \text{ hours}$, 1 day ahead).
* **Feature Window ($X$)**: Antecedent observation window $[t - 30 \text{ days}, t - 1 \text{ day}]$.
* **Anti-Leakage Invariant**:
  $$\max(\text{feature\_window\_end}) < \text{target\_date} = t$$
  Weather occurring during target day $t$ lies strictly in the future relative to the prediction anchor and is **100% excluded** from predictor features.

### 5.2 Temporal Alignment Table

| Feature | Source | Native Time | Aggregated Time | Availability Rule | Leakage Risk & Control |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `precip_1d_mm` | ERA5 | Hourly (00:00–23:59 UTC) | Day $t-1$ total | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $t-1$). Target day excluded. |
| `precip_3d_sum_mm` | ERA5 | Daily totals | Sum $[t-3, t-1]$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $[t-3, t-1]$). |
| `precip_7d_sum_mm` | ERA5 | Daily totals | Sum $[t-7, t-1]$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $[t-7, t-1]$). |
| `precip_14d_sum_mm`| ERA5 | Daily totals | Sum $[t-14, t-1]$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $[t-14, t-1]$). |
| `precip_30d_sum_mm`| ERA5 | Daily totals | Sum $[t-30, t-1]$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $[t-30, t-1]$). |
| `temp_mean_1d_c` | ERA5 | Hourly means | Mean at $t-1$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $t-1$). |
| `temp_7d_mean_c` | ERA5 | Daily means | Mean $[t-7, t-1]$ | Available at $T = t\text{ 00:00 UTC}$ | Controlled (strictly $[t-7, t-1]$). |
| `elevation_mean_m` | Copernicus DEM | Static raster | District zonal mean | Static invariant | Zero temporal risk (geomorphic). |
| `mean_upstream_area_km2` | HydroBASINS | Static vector | District area-weighted | Static invariant | Zero temporal risk (topological). |
| `flood_occurrence` | IFI v3.0 | Event calendar date | Day $t$ target | Target label | Segregated from predictors. Never in $X$. |

---

## 6. Spatial Aggregation Architecture (Grid to District)

ERA5 observations are provided on a regular 0.25° geographic grid ($\approx 27.75 \text{ km} \times 27.75 \text{ km}$ cells), whereas disaster events are cataloged by administrative district.

### 6.1 Geometric Area-Weighting Formulation
1. **Cell Envelopes**:
   For each cell center $(\lambda_c, \phi_c)$, its spatial envelope is:
   $$\text{Envelope}_c = [\lambda_c - 0.125^\circ, \phi_c - 0.125^\circ, \lambda_c + 0.125^\circ, \phi_c + 0.125^\circ]$$

2. **Intersection Weights**:
   For each district $d$ with authoritative boundary polygon $P_d$ from KSR-SAC:
   $$A_{d, c} = \text{Area}(P_d \cap \text{Envelope}_c)$$
   The normalized spatial weight $w_{d, c}$ is:
   $$w_{d, c} = \frac{A_{d, c}}{\sum_{c'} A_{d, c'}} \quad \text{such that} \quad \sum_{c} w_{d, c} = 1.000000$$

3. **Incompleteness & Quality Threshold**:
   For each day $s$, the available valid cell weight is evaluated:
   $$W_{\text{valid}}(d, s) = \sum_{c \in \text{Complete}} w_{d, c}$$
   * If $W_{\text{valid}}(d, s) \ge 0.95$, the district day is marked complete, and values are scaled by $1 / W_{\text{valid}}$.
   * If $W_{\text{valid}}(d, s) < 0.95$, the district day is marked **incomplete**, and all weather features evaluate strictly to `NaN` (no silent zero-filling, no interpolation).

---

## 7. Label Join & Target Statistics

### 7.1 Historical Label Join (Database Table: `district_day_flood_labels`)
* Evaluates exact composite key: `(district_id, target_date == event_date)`.
* `FLOOD = 1`: Real documented flood disaster from IFI v3.0.
* `NO_FLOOD = 0`: Only when supported by an explicit verified non-flood observation window.
* `UNKNOWN = NULL`: Unevidenced dates remain strictly unlabelled.

### 7.2 Empirical Target Distribution Across Aligned Historical Scope (1969–1975)
* Total possible District × Day rows: **73,222 rows** (2,362 calendar dates $\times$ 31 districts).
* Positive flood rows (`FLOOD = 1`): **546 rows** (0.7457% positive prevalence).
* Verified negative rows (`NO_FLOOD = 0`): **0 rows** (no raw negative archive in IFI).
* Unevidenced rows (`UNKNOWN = NULL`): **72,676 rows** (99.2543%).
* Rows lost due to missing features: **0 rows** (100% weather, terrain, and hydro coverage).

---

## 8. Real-Data Deterministic Validation Slice

A small deterministic validation slice was extracted from real data for manual inspection:
* **Command**:
  ```bash
  python -m app.ml.matrix_cli sample --source-parquet data/processed/ml_matrix/district_day_feature_matrix.parquet --year 1974 --districts Belagavi Kodagu Raichur
  ```
* **Output Artifacts**:
  * `data/processed/ml_matrix/validation_sample_district_day.parquet`
  * `data/processed/ml_matrix/validation_sample_district_day.json`
* **Inspection Metrics**:
  * Total rows: **1,095** ($3 \text{ districts} \times 365 \text{ days}$).
  * Date range: **1974-01-01 to 1974-12-31**.
  * `FLOOD` positive observations: **21 rows** (e.g. Belagavi July 1974 floods, source disaster event `UEI-IMD-FL-1974-0005`, antecedent 1d precip 2.11mm–4.63mm, 7d sum 14.78mm–19.30mm, zonal elevation 643.78m).
  * `UNKNOWN` unobserved observations: **1,074 rows** (flood_occurrence = `None`).
  * Feature completeness: 100% complete weather lookbacks, 100% terrain coverage, 100% hydrological coverage.

---

## 9. Automated Leakage Guards & Test Results

Seven automated leakage tests were implemented under `TestFeatureMatrixLeakageGuards` in [`backend/tests/test_district_feature_matrix.py`](file:///home/pioneer/Projects/FloodPrediction/backend/tests/test_district_feature_matrix.py):
1. `test_leakage_01_feature_timestamp_le_prediction_cutoff`: Asserts $\text{feature\_window\_end} < \text{target\_date}$, raising `TemporalLeakageError` if end date $\ge$ cutoff.
2. `test_leakage_02_target_timestamp_gt_prediction_cutoff`: Asserts target event interval occurs strictly after the 00:00:00 UTC prediction anchor.
3. `test_leakage_03_no_future_rainfall_leakage`: Confirms that target-day rainfall cannot enter antecedent precipitation features ($1\text{d}, 3\text{d}, 7\text{d}, 14\text{d}, 30\text{d}$).
4. `test_leakage_04_no_future_era5_leakage`: Confirms that rolling window offsets are strictly negative ($\text{offset} < 0$) and missing antecedent days evaluate to `None`.
5. `test_leakage_05_no_future_flood_label_leakage`: Confirms disaster event IDs and labels belong strictly to target date $t$, not subsequent dates.
6. `test_leakage_06_no_target_derived_feature_leakage`: Confirms target columns have zero intersection with predictor features.
7. `test_leakage_07_spatial_joins_use_authoritative_district_identifiers`: Asserts spatial aggregation uses only the 31 authoritative Karnataka districts with non-empty area weights summing to $1.000000 \pm 10^{-5}$.

### Test Execution Summary
* `backend/tests/test_district_feature_matrix.py`: **22 passed, 0 failed in 1.27s**.
* Full backend test suite: **410 passed, 0 failed in 226.51s** (`backend/tests`).
* Database migrations: Clean at `4b8c3d2e1f0a (head)`.
* Formatting: `git diff --check` passed with 0 errors.

---

## 10. Available Now vs. Requires Completion of ERA5 Extraction

### AVAILABLE NOW
1. **Raw ERA5 Extraction**: 858 / 858 chunks (100.0%) verified intact on disk across 1969–1994.
2. **Daily ERA5 Processed**: 250 chunks processed to daily Parquet across 12 years (`1969, 1970, 1971, 1972, 1973, 1974, 1975, 1976, 1977, 1979, 1980, 1994`).
3. **Contiguous Historical Matrix**: 1969-07-14 to 1975-12-31 (**73,222 District × Day rows**), with complete 30-day antecedent weather, 100% terrain coverage, and 100% hydro GIS coverage.
4. **Deterministic Validation Sample**: 1,095 rows (1974, Belagavi, Kodagu, Raichur).
5. **Anti-Leakage Pipeline & Tests**: Enforced 24-hour lead time and 410 passing backend tests.

### REQUIRES COMPLETION OF ERA5 DAILY PROCESSING (Not Blocked on Extraction)
* Expanding the daily Parquet processed tranche from 12 years to all 26 years (years 1978 and 1981–1993 are already downloaded in raw format and only require batch daily aggregation via `DailyProcessor`).
