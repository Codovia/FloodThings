# Phase 5.7 — Historical ERA5 Completion & Feature-Readiness Audit Report

**Project:** FloodPulse  
**Phase:** 5.7 — Historical ERA5 Completion & Feature-Readiness Audit  
**Date:** 2026-10-01  
**Status:** COMPLETE (All audits verified; 10/10 test categories passed)  

---

## Executive Summary

Phase 5.7 conducted an exhaustive audit of the historical meteorological and hydrological foundation for machine learning in the Karnataka AI Flood Intelligence system. 

### Critical Discovery on Historical ERA5 Extraction
The prompt's preliminary note indicated that historical ERA5 extraction was paused at 325/858 chunks due to Open-Meteo HTTP 429 quota exhaustion. 
**Verification Finding:** An exhaustive audit of `data/raw/era5_historical/extraction_manifest.json` and the physical filesystem reveals that extraction and daily processing are **100% COMPLETE**:
- **Canonical Chunks:** 858
- **SUCCEEDED Chunks:** **858 (100.0%)**
- **RETRYABLE Chunks:** **0**
- **PENDING Chunks:** **0**
- **RUNNING Chunks:** **0**
- **Raw Files on Disk:** Exactly 858 `.json.gz` (356.1 MB compressed) and 858 `.meta.json` files spanning all 26 canonical years (1969–1994, 33 chunks per year).
- **Daily Parquets on Disk:** Exactly 858 historical daily parquets (`data/processed/era5_daily/historical/`), plus 528 recent parquets (1,386 total).
- **Processing Manifest:** `data/processed/era5_daily/processing_manifest.json` confirms 858/858 chunks processed with 0 errors.
- **Historical Supervised Matrix:** `data/processed/ml_matrix/district_day_feature_matrix.parquet` (294,376 rows $\times$ 57 cols; SHA-256 `849f722b4f5f6a9ee85882abf787ae3d6ea5e0abdb563f499567ede738e06d55`) is intact and verified.

---

## 1. Audit Methodology & Scope

In accordance with strict project constraints:
1. **Zero Data Fabrication:** No missing data was converted to zero, interpolated, or synthesized.
2. **Zero Label Invention:** No `UNKNOWN` labels were converted to `NO_FLOOD`. The dataset contains exactly 0 verified negative labels.
3. **PU Framework Rigor:** The SCAR (Selected At Random) assumption remains **NOT VALIDATED**. All historical ML baselines remain catalogue-conditioned PU proxy experiments.
4. **Hydrological Telemetry Isolation:** Real CWC/NWIC river observations exist exclusively for calendar year 2026. Because historical coverage (1969–1994 and 2011–2023) is 0.000%, in-situ hydrological telemetry remains **BLOCKED FOR HISTORICAL TRAINING**.
5. **Parquet Immutability:** Existing ML matrices were audited in read-only mode via PyArrow without altering disk contents or modifying SHA-256 digests.

---

## 2. Historical ERA5 Physical Inventory & Integrity

### Grid & Spatial Fingerprint
- **Total Bounding Box Grid Cells:** 324 cells ($0.25^\circ \times 0.25^\circ$ spacing, lat $11.5^\circ\text{N}$ to $18.5^\circ\text{N}$, lon $74.0^\circ\text{E}$ to $78.5^\circ\text{E}$).
- **Eligible Land/Inland Cells:** **318 cells** (intersecting Karnataka district boundaries).
- **Source-Excluded Offshore Cells:** **6 cells** (Arabian Sea open water: `CELL_1175_0740`, `CELL_1200_0740`, `CELL_1225_0740`, `CELL_1400_0740`, `CELL_1425_0740`, `CELL_1450_0740`).
- **Spatial Batches:** 33 batches per year (batches 001–033, each containing 9 or 10 cells).
- **Temporal Span:** 1969-01-01 to 1994-12-31 (26 calendar years).

### Extraction & Processing Inventory

| Artifact Category | Path | Expected Count | Disk Actual Count | Status |
|---|---|---|---|---|
| Raw Compressed Hourly | `data/raw/era5_historical/year=YYYY/` | 858 `.json.gz` | **858** | **VERIFIED** |
| Raw Metadata JSON | `data/raw/era5_historical/year=YYYY/` | 858 `.meta.json` | **858** | **VERIFIED** |
| Extraction Manifest | `data/raw/era5_historical/extraction_manifest.json` | 858 entries | **858 SUCCEEDED** | **VERIFIED** |
| Daily Aggregated Parquets | `data/processed/era5_daily/historical/year=YYYY/` | 858 `.parquet` | **858** | **VERIFIED** |
| Daily Processing Manifest | `data/processed/era5_daily/processing_manifest.json` | 858 entries | **858 SUCCEEDED** | **VERIFIED** |
| Spatial Weights Cache | `data/processed/gis_cache/district_era5_weights.json` | 31 districts | **31 districts** | **VERIFIED** |
| Baseline Feature Matrix | `data/processed/ml_matrix/district_day_feature_matrix.parquet` | 294,376 rows | **294,376 rows** | **VERIFIED** |

---

## 3. Spatial Aggregation & Weight Normalization Audit

The spatial mapping from 318 eligible ERA5 grid cells to the 31 official KSR-SAC Karnataka districts was audited from `data/processed/gis_cache/district_era5_weights.json`:
1. **District Coverage:** Exactly 31 districts are defined.
2. **Cell Reference Integrity:** Exactly 318 unique ERA5 grid cells appear in district weighting dictionaries.
3. **Exclusion Invariant:** Zero instances of the 6 source-excluded offshore cells appear in the weighting matrix.
4. **Weight Normalization:** For every district $d$, the sum of fractional cell weights satisfies:
   $$\sum_{c \in \mathcal{C}_d} w_{d, c} = 1.000000 \pm 10^{-6}$$
   - Minimum district weight sum: `1.000000`
   - Maximum district weight sum: `1.000000`
   - Zero districts assigned zero or NaN weight.
5. **Geometry Version:** KSR-SAC / Survey of India 31-district administrative boundary shapefile (EPSG:4326).

---

## 4. Meteorological Feature Audit & Aggregation Specifications

The raw ERA5 archive contains four fundamental meteorological variables recorded at 1-hour temporal resolution:
- `precipitation` (total liquid and ice precipitation, mm)
- `temperature_2m` (air temperature at 2 metres above ground, $^\circ\text{C}$)
- `relative_humidity_2m` (relative humidity at 2 metres above ground, %)
- `surface_pressure` (atmospheric pressure at ground level, hPa)

### Scientific Evaluation of Candidate Meteorological Predictors

| Variable | Candidate Feature | Aggregation Method | Unit | Lookback Window | Leakage Status | Missing Policy | Feature Status |
|---|---|---|---|---|---|---|---|
| Precipitation | `precip_1d_mm` | 24h daily sum | mm | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_3d_sum_mm` | 3-day rolling sum | mm | $[t-3, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_7d_sum_mm` | 7-day rolling sum | mm | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_14d_sum_mm` | 14-day rolling sum | mm | $[t-14, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_30d_sum_mm` | 30-day rolling sum | mm | $[t-30, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_7d_max_mm` | 7-day rolling daily max | mm | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_14d_max_mm` | 14-day rolling daily max | mm | $[t-14, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Precipitation | `precip_lag_2d_mm` | 1-day lag of daily sum | mm | $[t-2, t-2]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Precipitation | `precip_lag_3d_mm` | 1-day lag of daily sum | mm | $[t-3, t-3]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Precipitation | `precip_3d_max_mm` | 3-day rolling daily max | mm | $[t-3, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Precipitation | `precip_30d_max_mm` | 30-day rolling daily max | mm | $[t-30, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Temperature | `temp_mean_1d_c` | 24h daily mean | $^\circ\text{C}$ | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Temperature | `temp_min_1d_c` | 24h daily minimum | $^\circ\text{C}$ | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Temperature | `temp_max_1d_c` | 24h daily maximum | $^\circ\text{C}$ | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Temperature | `temp_7d_mean_c` | 7-day rolling mean | $^\circ\text{C}$ | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Temperature | `temp_7d_min_c` | 7-day rolling minimum | $^\circ\text{C}$ | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Temperature | `temp_7d_max_c` | 7-day rolling maximum | $^\circ\text{C}$ | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |
| Humidity | `rh_mean_1d_pct` | 24h daily mean | % | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Humidity | `rh_7d_mean_pct` | 7-day rolling mean | % | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Pressure | `pressure_mean_1d_hpa`| 24h daily mean | hPa | $[t-1, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Canonical) |
| Pressure | `pressure_7d_mean_hpa`| 7-day rolling mean | hPa | $[t-7, t-1]$ | NO LEAKAGE | Fail/NaN | **READY** (Derivable) |

*Note:* All features strictly adhere to UTC timezone alignment, where day $t$ boundaries span `[00:00:00 UTC, 23:59:59 UTC]`.

---

## 5. Temporal Anti-Leakage Audit

The ML prediction contract establishes:
- **Prediction Anchor:** Target calendar date $t$ (evaluating flood occurrence on day $t$).
- **Prediction Lead Time:** $\ge 1$ day.
- **Allowed Feature Observation Window:** Strictly $\tau \in [t-30, t-1]$.
- **Leakage Invariant:** **Zero observations from day $t$ or future dates ($t + k, k \ge 0$) may enter any predictor.**

### Verification in Feature Generation Code
Both `backend/app/features/district_feature_matrix.py` (historical) and `backend/app/features/recent_matrix_builder.py` (recent) were audited line-by-line:
1. When computing features for target date $t$, the daily slice is filtered to `date < t` (specifically `end_date = t - timedelta(days=1)`).
2. The lookback slice is extracted as:
   ```python
   window_df = district_df[(district_df["date"] >= start_date) & (district_df["date"] <= end_date)]
   ```
   where `start_date = t - timedelta(days=30)` and `end_date = t - timedelta(days=1)`.
3. Day $t$ weather is completely absent from the aggregation slice.
4. Unit test `backend/tests/test_historical_feature_readiness.py::test_04_no_same_day_leakage` passed with 0 violations.

---

## 6. Cold-Start Initialization Boundary Audit

Because antecedent features require up to 30 days of lookback, the first 30 days of any continuous meteorological sequence cannot compute valid 30-day rolling sums:
- **Historical Matrix (1969–1994):** 1969-01-01 through 1969-01-30 ($30\text{ days} \times 31\text{ districts} = 930\text{ rows}$) have incomplete lookback.
- **Recent Matrix (2011–2023):** 2011-01-01 through 2011-01-30 ($30\text{ days} \times 31\text{ districts} = 930\text{ rows}$) have incomplete lookback.

### Handling Policy (Policy A - Exclude Incomplete Windows)
1. **Explicit Identification:** Every row carries boolean flag `is_weather_complete_30d`. Incomplete rows are strictly flagged `False`.
2. **Zero Synthetic Imputation:** Missing lookback values are **NEVER imputed** with zero, district means, or synthetic rainfall.
3. **Supervised Isolation:** `load_supervised_dataset(exclude_cold_start=True)` systematically filters out these 930 rows prior to training.
4. **Verified Result:** In `district_day_matrix_2011_2023.parquet`, 930 cold-start rows exist with `precip_30d_sum_mm == NaN`. After cold-start filtering, exactly 141,298 rows remain with 0 nulls across all 27 predictors.

---

## 7. Terrain & Static Hydrological GIS Feature Audit

Static GIS features represent time-invariant physiographic characteristics of each district:

### Valid Static Features for Historical ML
- **Elevation Zonal Statistics:** `elevation_mean_m`, `elevation_min_m`, `elevation_max_m`, `elevation_std_m` (derived from SRTM 30m DEM).
- **Slope Zonal Statistics:** `slope_mean_deg`, `slope_max_deg` (derived from SRTM 30m DEM).
- **Basin Structure:** `major_basin_count`, `primary_basin_coverage_pct` (derived from CWC Major Basin polygons).
- **Sub-Basin Topography:** `sub_basin_count` (derived from HydroBASINS Level-7).
- **Hydrographic Network Scale:** `mean_upstream_area_km2` (derived from HydroRIVERS flow accumulation).
- **Grid Density:** `weather_cell_count` (number of eligible ERA5 cells intersecting district).

### Blocked Hydrological Features (2026 Operational Telemetry Only)
The 10 in-situ river telemetry features formulated in Phase 5.6:
1. `river_level_current`
2. `river_level_lag_1d`
3. `river_level_lag_3d`
4. `river_level_change_1d`
5. `river_level_change_3d`
6. `river_level_rolling_max_3d`
7. `river_level_rolling_max_7d`
8. `upstream_station_count`
9. `upstream_max_level`
10. `upstream_mean_level`

**Audit Finding:** In-situ CWC telemetry exists exclusively for Jan–Aug 2026 in the Cauvery basin. Coverage across historical (1969–1994) and recent (2011–2023) supervised sets is **0.000%**. In accordance with the zero-fabrication constraint, these 10 features remain **BLOCKED FOR HISTORICAL TRAINING**.

---

## 8. Authoritative Feature Contract

The complete, authoritative predictor contract for the Karnataka district-day flood risk model:

| Field | Feature Name | Source | Source Type | Unit | Aggregation | Temporal Window | Spatial Aggregation | Leakage Status | Missing Policy | Provenance | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `precip_1d_mm` | ERA5 | Dynamic Weather | mm | 24h sum | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 2 | `precip_3d_sum_mm` | ERA5 | Dynamic Weather | mm | 3d rolling sum | $[t-3, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 3 | `precip_7d_sum_mm` | ERA5 | Dynamic Weather | mm | 7d rolling sum | $[t-7, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 4 | `precip_14d_sum_mm` | ERA5 | Dynamic Weather | mm | 14d rolling sum | $[t-14, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 5 | `precip_30d_sum_mm` | ERA5 | Dynamic Weather | mm | 30d rolling sum | $[t-30, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 6 | `precip_7d_max_mm` | ERA5 | Dynamic Weather | mm | 7d daily max | $[t-7, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 7 | `precip_14d_max_mm` | ERA5 | Dynamic Weather | mm | 14d daily max | $[t-14, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 8 | `temp_mean_1d_c` | ERA5 | Dynamic Weather | $^\circ\text{C}$ | 24h mean | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 9 | `temp_min_1d_c` | ERA5 | Dynamic Weather | $^\circ\text{C}$ | 24h min | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 10 | `temp_max_1d_c` | ERA5 | Dynamic Weather | $^\circ\text{C}$ | 24h max | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 11 | `temp_7d_mean_c` | ERA5 | Dynamic Weather | $^\circ\text{C}$ | 7d rolling mean | $[t-7, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 12 | `rh_mean_1d_pct` | ERA5 | Dynamic Weather | % | 24h mean | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 13 | `rh_7d_mean_pct` | ERA5 | Dynamic Weather | % | 7d rolling mean | $[t-7, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 14 | `pressure_mean_1d_hpa` | ERA5 | Dynamic Weather | hPa | 24h mean | $[t-1, t-1]$ | Area-weighted mean | NO LEAKAGE | Fail/NaN | ECMWF ERA5 Reanalysis | **READY** |
| 15 | `elevation_mean_m` | SRTM | Static Terrain | m | Zonal mean | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 16 | `elevation_min_m` | SRTM | Static Terrain | m | Zonal min | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 17 | `elevation_max_m` | SRTM | Static Terrain | m | Zonal max | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 18 | `elevation_std_m` | SRTM | Static Terrain | m | Zonal std | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 19 | `slope_mean_deg` | SRTM | Static Terrain | degrees | Zonal mean | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 20 | `slope_max_deg` | SRTM | Static Terrain | degrees | Zonal max | Static | District polygon | NO LEAKAGE | Fail/NaN | NASA SRTM 30m DEM | **READY** |
| 21 | `major_basin_count` | CWC | Static Hydrology | count | Spatial intersection | Static | District polygon | NO LEAKAGE | Fail/NaN | CWC River Basins | **READY** |
| 22 | `primary_basin_coverage_pct` | CWC | Static Hydrology | % | Max area fraction | Static | District polygon | NO LEAKAGE | Fail/NaN | CWC River Basins | **READY** |
| 23 | `sub_basin_count` | HydroBASINS | Static Hydrology | count | Spatial intersection | Static | District polygon | NO LEAKAGE | Fail/NaN | HydroBASINS Level-7 | **READY** |
| 24 | `mean_upstream_area_km2` | HydroRIVERS | Static Hydrology | $\text{km}^2$| Reach mean | Static | District polygon | NO LEAKAGE | Fail/NaN | HydroRIVERS Flow Network | **READY** |
| 25 | `weather_cell_count` | Grid Cache | Spatial Index | count | Intersection count | Static | District polygon | NO LEAKAGE | Fail/NaN | KSR-SAC / ERA5 Grid | **READY** |
| 26 | `day_of_year` | Calendar | Temporal Index | day (1–366) | Calendar day of $t$ | $[t, t]$ | District-agnostic | NO LEAKAGE | Deterministic | Julian Calendar | **READY** |
| 27 | `target_month` | Calendar | Temporal Index | month (1–12) | Calendar month of $t$| $[t, t]$ | District-agnostic | NO LEAKAGE | Deterministic | Gregorian Calendar | **READY** |
| 28–37 | River Telemetry (10 features) | CWC/NWIC | Operational Hydrology | m / $\Delta$m | Stage statistics | $[t-30, t-1]$ | Gauge station crosswalk | NO LEAKAGE | Preserve NaN | CWC / NWIC Telemetry | **BLOCKED** |

---

## 9. Deterministic ERA5 Extraction Resume Checklist

Should future operational needs require ingesting additional historical or real-time ERA5 chunks, the extraction pipeline in `backend/app/ingestion/sources/era5_historical.py` must be resumed deterministically.

### Verification Checklist
- [x] **Extraction Manifest State:** `data/raw/era5_historical/extraction_manifest.json` exists, valid JSON, exactly 858 chunk keys.
- [x] **Chunk Status Invariants:** Every chunk status is one of `{"SUCCEEDED", "RETRYABLE", "PENDING", "RUNNING"}`.
- [x] **Raw Artifact Existence:** For every `SUCCEEDED` chunk, both `chunk_id.json.gz` and `chunk_id.meta.json` exist on disk.
- [x] **Integrity & Decompression:** Raw `.json.gz` files decompress with valid Gzip CRC and parse to valid JSON.
- [x] **Checksum Verification:** Metadata JSON records SHA-256 and byte size matching physical raw files.
- [x] **Hourly Timestamp Continuity:** Every annual chunk covers all 8,760 hours (8,784 in leap years) without gaps.
- [x] **Spatial Grid Identity:** Grid cell coordinate coordinates strictly match the 318 eligible cells ($0.25^\circ \times 0.25^\circ$ grid).
- [x] **Non-Destructive Execution:** Script checks existing artifacts before API requests; never overwrites or re-downloads completed chunks.

---

## 10. Regression & Verification Test Suite

A comprehensive test suite of 10 targeted tests was implemented in `backend/tests/test_historical_feature_readiness.py`:

| Test Name | Verification Focus | Result |
|---|---|---|
| `test_01_feature_whitelist_canonical_27` | Enforces exact 27 canonical features | **PASSED** |
| `test_02_feature_units_integrity` | Verifies physical units across all 27 predictors | **PASSED** |
| `test_03_temporal_lookback_strictly_t_minus_30_to_t_minus_1` | Verifies lookback window $[t-30, t-1]$ | **PASSED** |
| `test_04_no_same_day_leakage` | Verifies day $t$ observations are strictly filtered out | **PASSED** |
| `test_05_cold_start_initialization_handling` | Verifies 930 cold-start rows are flagged & excluded | **PASSED** |
| `test_06_spatial_weight_normalization` | Verifies spatial weights sum to 1.000000 for all 31 districts | **PASSED** |
| `test_07_excluded_era5_cells_remain_excluded` | Verifies 6 offshore cells are omitted from weights | **PASSED** |
| `test_08_missing_data_does_not_become_zero` | Verifies missing values remain NaN and are never zeroed | **PASSED** |
| `test_09_historical_hydrology_does_not_use_2026_telemetry` | Verifies CWC features are BLOCKED for historical ML | **PASSED** |
| `test_10_predictor_target_separation` | Verifies targets and event metadata cannot be predictors | **PASSED** |

**Full Test Suite Run:** 45/45 tests passing (10 new readiness tests + 10 Phase 5.6 hydrology tests + 10 Phase 5.5 benchmark tests + 15 Phase 5.4 baseline tests).

---

## 11. Scientific Status & Blocker Register

### What is Completed (VERIFIED)
- Historical ERA5 1969–1994 extraction and daily processing are 100% complete (858/858 chunks SUCCEEDED).
- Spatial weight normalization is verified across all 31 districts with 0 offshore cell intrusions.
- Temporal anti-leakage contract is strictly enforced across all feature engines ($[t-30, t-1]$, zero day-$t$ leakage).
- 930 cold-start initialization rows are explicitly flagged and excluded from training without imputation.
- Authoritative feature contract established for 27 active predictors.

### What is Blocked (BLOCKED)
- **Historical In-Situ River Telemetry:** Blocked due to 0.000% observation coverage in 1969–1994 and 2011–2023. Cannot be included in historical ML training.
- **Production Model Deployment:** Blocked pending evaluation of combined multi-era training sets and validation on real negative data.
- **Calibrated Risk Probabilities:** Blocked because PU models output proxy propensity scores rather than calibrated event probabilities.

### ML Readiness Declaration
The ML models developed in Phase 5.4 and Phase 5.5 are **PU proxy benchmark models only**. They are **NOT PRODUCTION READY**. Unlabeled rows must remain `UNKNOWN` (not `NO_FLOOD`), and precision/recall metrics reflect catalogue detection relative to IFI rather than true ground-truth epidemiological flood occurrences.
