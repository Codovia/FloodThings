# ML-Ready Historical Feature Engineering Pipeline

**Project:** FloodPulse  
**Module:** `backend/app/ml`  
**Phase:** Phase 3.12 — ML Feature Pipeline Foundation  
**Status:** IMPLEMENTED, VALIDATED, & DETERMINISTIC  
**Zero Model Training | Zero Label Fabrication | Zero Synthetic Filling | Zero Temporal Leakage**

---

## 1. Architectural Overview

The ML Feature Engineering Pipeline bridges canonical daily meteorological reanalysis, high-resolution digital elevation models, and hydrological GIS topologies into a leakage-safe, ML-ready feature dataset.

```text
ERA5 Raw Artifacts (JSON.gz chunks)
         ↓
Daily Processed Data (Parquet via DailyProcessor)
         ↓
Spatial & Hydrological Enrichment (Copernicus DEM GLO-30 + PostGIS HydroSHEDS/CWC)
         ↓
Chronological Rolling Feature Engineering (FeatureGenerator)
         ↓
Validated ML-Ready Feature Dataset (Partitioned Parquet + Manifest)
```

The pipeline enforces:
1. **Strict Temporal Causality:** Features at date $t$ are derived exclusively from observations at or before date $t$ ($t' \le t$). No future observation ever enters any feature calculation.
2. **Missing Observation Integrity:** If any observation is missing or incomplete in a rolling window, the engineered feature evaluates to `NULL` / `NaN`. Missing days are **never** silently filled with `0.0` or interpolated.
3. **Exact Spatial and Lineage Traceability:** Every feature record maintains pointers to its `cell_id`, `chunk_id`, `raw_chunk_id`, and `raw_payload_sha256`.
4. **Physical and Numerical Consistency:** Strict bounds validation on temperature hierarchy ($T_{\min} \le T_{\text{mean}} \le T_{\max}$), relative humidity ($[0, 100]\%$), surface pressure ($[300, 1100]\text{ hPa}$), elevation, and slope.

---

## 2. Feature Schema & Data Dictionary

Each feature row corresponds to a single 0.25° ERA5 grid cell on a specific UTC calendar day.

### 2.1 Identity & Coordinate Features

| Field Name | Type | Unit | Description | Source |
| :--- | :--- | :--- | :--- | :--- |
| `date` | `STRING` | YYYY-MM-DD | UTC calendar date of the feature observation | ERA5 extraction timeline |
| `cell_id` | `STRING` | Text | Deterministic cell identifier (`ERA5_{lat*100:04d}_{lon*100:05d}`) | Authoritative Karnataka 0.25° Grid |
| `chunk_id` | `STRING` | Text | Identifier of the source chunk | Daily processing manifest |
| `latitude` | `FLOAT64` | Degrees | Centroid latitude in WGS 84 (EPSG:4326) | ERA5 grid definition |
| `longitude` | `FLOAT64` | Degrees | Centroid longitude in WGS 84 (EPSG:4326) | ERA5 grid definition |

### 2.2 Precipitation Rolling Features

All rainfall windows are strictly backward-looking: $[t - (W-1), t]$.

| Field Name | Type | Unit | Window | Transformation | Missing-Data Policy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `rainfall_1d` | `FLOAT64` | mm | 1 day ($t$) | $\sum_{h=0}^{23} P_h$ | `NaN` if `hour_count < 24` or day missing |
| `rainfall_3d` | `FLOAT64` | mm | 3 days ($[t-2, t]$) | $\sum_{k=0}^{2} P_{t-k}$ | `NaN` if any day in $[t-2, t]$ missing or incomplete |
| `rainfall_7d` | `FLOAT64` | mm | 7 days ($[t-6, t]$) | $\sum_{k=0}^{6} P_{t-k}$ | `NaN` if any day in $[t-6, t]$ missing or incomplete |
| `rainfall_14d` | `FLOAT64` | mm | 14 days ($[t-13, t]$) | $\sum_{k=0}^{13} P_{t-k}$ | `NaN` if any day in $[t-13, t]$ missing or incomplete |
| `rainfall_30d` | `FLOAT64` | mm | 30 days ($[t-29, t]$) | $\sum_{k=0}^{29} P_{t-k}$ | `NaN` if any day in $[t-29, t]$ missing or incomplete |

### 2.3 Atmospheric Weather Statistics

| Field Name | Type | Unit | Transformation | Physical Bounds |
| :--- | :--- | :--- | :--- | :--- |
| `temperature_mean_c` | `FLOAT64` | °C | Arithmetic mean of 24 hourly 2m air temperatures | $[-50.0, 65.0]$ |
| `temperature_min_c` | `FLOAT64` | °C | Minimum hourly 2m air temperature | $T_{\min} \le T_{\text{mean}}$ |
| `temperature_max_c` | `FLOAT64` | °C | Maximum hourly 2m air temperature | $T_{\max} \ge T_{\text{mean}}$ |
| `relative_humidity_mean_pct` | `FLOAT64` | % | Arithmetic mean of 24 hourly relative humidity observations | $[0.0, 100.0]$ |
| `surface_pressure_mean_hpa` | `FLOAT64` | hPa | Arithmetic mean of 24 hourly surface pressure observations | $[300.0, 1100.0]$ |

### 2.4 Terrain Features (Copernicus DEM GLO-30)

| Field Name | Type | Unit | Description | Calculation Method |
| :--- | :--- | :--- | :--- | :--- |
| `elevation` | `FLOAT64` | meters | Zonal mean elevation across 0.25° cell box | Copernicus DEM GLO-30 (~30m), EGM2008 geoid |
| `slope` | `FLOAT64` | degrees | Zonal mean topographic slope across 0.25° cell box | Horn (1981) metric slope with geodesic $\cos(\text{lat})$ metric scaling |

### 2.5 Hydrological & Administrative Crosswalk Features

| Field Name | Type | Description | Source Layer |
| :--- | :--- | :--- | :--- |
| `basin_id` | `STRING` | CWC statutory major river basin UUID | PostGIS `river_basins` |
| `basin_name` | `STRING` | CWC major river basin name (e.g. Cauvery, Krishna) | PostGIS `river_basins` |
| `sub_basin_id` | `STRING` | HydroBASINS Level-7 sub-basin UUID | PostGIS `sub_basins` |
| `sub_basin_name` | `STRING` | HydroBASINS Level-7 code (e.g. `HYBAS_4071140230`) | PostGIS `sub_basins` |
| `hybas_id` | `INT64` | HydroBASINS Level-7 unique identifier | PostGIS `sub_basins` |
| `distance_to_river_m` | `FLOAT64` | Geodesic distance in meters to nearest HydroRIVERS reach | PostGIS `rivers` (geodesic metric) |
| `nearest_river_id` | `STRING` | Nearest river reach name / identifier | PostGIS `rivers` |
| `district_id` | `STRING` | KSR-SAC administrative district UUID | PostGIS `districts` |
| `district_name` | `STRING` | KSR-SAC administrative district name | PostGIS `districts` |

### 2.6 Quality & Lineage Flags

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `hour_count` | `INT32` | Number of valid hourly observations contributing to day $t$ (0–24) |
| `quality_status` | `STRING` | `COMPLETE` iff `hour_count == 24`, else `INCOMPLETE` |
| `window_30d_valid_days` | `INT32` | Count of `COMPLETE` days in $[t-29, t]$ (0–30) |
| `is_complete` | `BOOL` | `TRUE` iff day $t$ and 30-day window are fully populated and valid |
| `raw_chunk_id` | `STRING` | Raw source extraction chunk identifier (e.g. `era5_1969_batch_001`) |
| `raw_payload_sha256` | `STRING` | SHA-256 hash of uncompressed raw extraction JSON payload |
| `feature_version` | `STRING` | Feature engineering pipeline version (`1.0`) |

---

## 3. Mathematical Formulations & Anti-Leakage Rules

### 3.1 Temporal Ordering
For each grid cell $c$, daily records are strictly sorted chronologically:
$$D_c = \langle (t_0, \mathbf{x}_0), (t_1, \mathbf{x}_1), \dots, (t_N, \mathbf{x}_N) \rangle \quad \text{where } t_0 < t_1 < \dots < t_N$$

### 3.2 Backward-Looking Rolling Windows
For window size $W \in \{1, 3, 7, 14, 30\}$, the rolling rainfall sum at date $t$ is:
$$\text{rainfall\_Wd}(c, t) = \sum_{k=0}^{W-1} P(c, t - k)$$
Subject to the strict completeness condition:
$$\text{rainfall\_Wd}(c, t) = \begin{cases} \sum_{k=0}^{W-1} P(c, t - k) & \text{if } \forall k \in [0, W-1]: (c, t-k) \text{ is present and } \text{quality} = \text{COMPLETE} \\ \text{NaN} & \text{otherwise} \end{cases}$$

### 3.3 Zero Silent Zero-Filling
A common defect in hydrological ML pipelines is replacing missing days with `0.0`. If a 7-day storm occurs but 1 day is dropped, treating the missing day as 0 creates an artificially suppressed cumulative total that corrupts flood prediction models. In this pipeline, missing days result in `NaN` and decrement `window_30d_valid_days`.

### 3.4 Cross-Year Lookback Continuity
When processing year $Y$, the pipeline inspects whether processed daily records for year $Y-1$ exist. If present, the trailing 29 days ($[Y-1\text{-12-03}, Y-1\text{-12-31}]$) are loaded into the cell lookback buffer. This allows January 1 to 29 of year $Y$ to evaluate full 30-day rolling windows without missing data or edge distortion, while strictly preventing any forward lookahead into future months.

---

## 4. Verification and Empirical Audit

### 4.1 Storage & Partitions
Features are persisted as partitioned columnar Parquet using Snappy compression:
- Base Directory: `data/processed/ml_features/`
- Directory Partitioning: `data/processed/ml_features/year=YYYY/batch_BBB.parquet`
- Spatial Cache: `data/processed/gis_cache/cell_spatial_features.json`
- Feature Manifest: `data/processed/ml_features/feature_manifest.json`

### 4.2 Real Production Benchmark (Year 1969 Full Statewide Run)
- Total Batches Processed: 33/33
- Total Eligible Cells: 318
- Total Daily Records Generated: **116,070**
- Complete Samples: **106,848** (Jan 30 to Dec 31 for all 318 cells)
- Incomplete Samples: **9,222** (Jan 1 to Jan 29, exactly $29 \times 318$ rows where 30-day lookback precedes dataset start)
- Parquet Dataset Size: 3.35 MB across 33 files
- Execution Time: ~42 seconds total (~1.2s per batch chunk)
- Physical Validation Failures: **0**

---

## 5. Next Stage: Flood Label Integration (Target A)

> [!IMPORTANT]
> **Definitive Stop Condition:**
> The feature pipeline is complete, tested, and validated.
> The dataset currently contains **predictors only** ($\mathbf{X}$).
> It does **not** contain flood target labels ($Y$).
> 
> The exact next dependency is **Phase 3.13: Target A (District Flood Occurrence) Label Integration**:
> 1. Ingest/normalize India Flood Inventory (IFI v3.0) historical flood disaster records ($Y_{d, t} = 1$).
> 2. Implement the three-state labelling contract (`POSITIVE`, `NEGATIVE`, `UNLABELLED`).
> 3. Perform audited meteorological non-event background sampling for verified negative training samples.
> 4. Join district-level labels $Y_{d, t}$ with cell-level or district-aggregated features $\mathbf{X}$.
> 5. Chronological train/validation/test temporal split (e.g. 1969–1980 train, 1981–1984 validation, 1985–1987 test).
