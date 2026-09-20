# Phase 3.11: Historical Meteorological Processing & Daily Aggregation Design

## 1. Objective

This document defines and validates the processing layer that converts validated raw hourly Open-Meteo ERA5 reanalysis chunks into reproducible, canonical daily meteorological data suitable for subsequent machine learning (ML) feature construction.

> [!IMPORTANT]
> **Strict Scope Boundary:**
> This phase produces historical meteorological observations and aggregated features only.
> It does **not** create flood labels, join India Flood Inventory (IFI) disaster records, assign positive/negative class states, or train ML models.
> No database schema migrations or PostgreSQL insertions were performed.

---

## 2. Processing Architecture & Boundary

The historical data pipeline is structured into strictly separated stages to preserve provenance, idempotency, and auditability:

```text
Raw ERA5 JSON.gz (data/raw/era5_historical/year=YYYY/batch_BBB.json.gz)
        ↓
Raw-file integrity verification (SHA-256 match, gzip decompression)
        ↓
Hourly structural/value validation (HistoricalChunkValidator)
        ↓
Daily aggregation (DailyAggregator: UTC calendar days, precip sum, temp/RH/pressure means)
        ↓
Daily quality validation (DailyDatasetValidator: continuity, completeness, physical bounds)
        ↓
Partitioned Parquet (data/processed/era5_daily/year=YYYY/batch_BBB.parquet)
        ↓
Processing manifest (data/processed/era5_daily/processing_manifest.json)
        ↓
Downstream ML feature engineering (Phase 3.12+)
```

The pipeline guarantees:
1. **Zero Raw Mutation:** Raw `.json.gz` payloads and `.meta.json` files are strictly read-only.
2. **Deterministic Aggregation:** Repeated execution with identical input yields logically identical daily records.
3. **Traceability:** Every daily record retains pointers to its source chunk ID and raw payload SHA-256.

---

## 3. Daily Aggregation Contract

### Temporal Alignment: UTC Calendar Days
The canonical historical dataset aggregates hourly timestamps across UTC calendar days (`YYYY-MM-DD 00:00` to `23:00` UTC). IST reporting adjustments are deferred to downstream feature transformations to avoid corrupting the authoritative reanalysis timeline.

### Canonical Daily Fields
Each daily record contains:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `date` | `STRING` (`YYYY-MM-DD`) | UTC calendar date |
| `latitude` | `FLOAT64` | 0.25° ERA5 grid cell center latitude |
| `longitude` | `FLOAT64` | 0.25° ERA5 grid cell center longitude |
| `precipitation_total_mm` | `FLOAT64` | Arithmetic sum of valid hourly precipitation (mm) |
| `temperature_mean_c` | `FLOAT64` | Arithmetic mean of hourly 2m temperature (°C) |
| `temperature_min_c` | `FLOAT64` | Minimum hourly 2m temperature (°C) |
| `temperature_max_c` | `FLOAT64` | Maximum hourly 2m temperature (°C) |
| `relative_humidity_mean_pct`| `FLOAT64` | Arithmetic mean of hourly 2m relative humidity (%) |
| `surface_pressure_mean_hpa` | `FLOAT64` | Arithmetic mean of hourly surface pressure (hPa) |
| `hour_count` | `INT32` | Count of valid hourly observations contributing to the day (0–24) |
| `quality_status` | `STRING` | Quality flag: `COMPLETE` (24 valid hours) or `INCOMPLETE` (< 24 valid hours) |
| `source` | `STRING` | Provenance source (`Open-Meteo Historical Weather API`) |
| `dataset_model` | `STRING` | Underlying reanalysis model (`ERA5`) |
| `raw_chunk_id` | `STRING` | Unique chunk identifier (e.g. `era5_1994_batch_001`) |
| `raw_payload_sha256` | `STRING` | SHA-256 hash of uncompressed source JSON payload |
| `processing_version` | `STRING` | Software processing version (e.g. `1.0`) |

---

## 4. Aggregation Rules & Formulas

1. **Precipitation:**
   Hourly ERA5 precipitation represents the total precipitation in millimeters accumulated over the preceding 1-hour interval.
   $$\text{precipitation\_total\_mm} = \sum_{h=0}^{23} P_h$$
   - Precipitation is **never averaged**.
   - Hourly values are **not treated as cumulative**.
   - **0.0 mm ≠ Missing:** A valid dry day with 0.0 mm of rainfall is classified as `COMPLETE`.
2. **Temperature:**
   $$\text{temperature\_mean\_c} = \frac{1}{N} \sum_{h=1}^N T_h, \quad \text{temperature\_min\_c} = \min(T_h), \quad \text{temperature\_max\_c} = \max(T_h)$$
3. **Relative Humidity:**
   $$\text{relative\_humidity\_mean\_pct} = \frac{1}{N} \sum_{h=1}^N \text{RH}_h$$
4. **Surface Pressure:**
   $$\text{surface\_pressure\_mean\_hpa} = \frac{1}{N} \sum_{h=1}^N \text{SP}_h$$

---

## 5. Completeness & Missing-Data Policy

A complete day requires all 24 valid hourly records:
$$\text{hour\_count} = 24 \implies \text{quality\_status} = \text{COMPLETE}$$
$$\text{hour\_count} < 24 \implies \text{quality\_status} = \text{INCOMPLETE}$$

### Strict Invariants:
- **Zero Imputation:** Missing hours are **never** filled or interpolated.
- **Zero Synthetic Replacement:** Missing values are **not** replaced with means, medians, or zeros.
- **Explicit Quality Recording:** If an incomplete day occurs, the available records are preserved only with `quality_status = INCOMPLETE` and the exact `hour_count` recorded. Downstream ML feature pipelines must explicitly filter or handle incomplete records.

---

## 6. Leap-Year Handling

- **Leap Years (e.g. 1980, 1988):**
  - Exactly 366 daily records per grid cell ($366 \times 24 = 8,784$ hourly records).
  - `YYYY-02-29` appears exactly once per grid cell.
- **Non-Leap Years (e.g. 1979, 1994):**
  - Exactly 365 daily records per grid cell ($365 \times 24 = 8,760$ hourly records).
  - `YYYY-02-29` does **not** exist.
- Calendar boundaries strictly cover `YYYY-01-01` through `YYYY-12-31` with zero timezone shifting.

---

## 7. Spatial Identity & Preservation

The processing engine reuses the authoritative 324 Karnataka ERA5 grid cells established in Phase 3.7B and Phase 3.9:
- Coordinates (`latitude`, `longitude`) are preserved exactly as returned by the API ($\pm 0.0001^\circ$ precision).
- Grid cell coordinates are **not snapped** to district centroids or arbitrary locality coordinates.
- Spatial aggregation to districts is strictly deferred to subsequent ML feature generation steps.

---

## 8. Partitioned Parquet Storage Design

Aggregated daily records are stored in a deterministic, partitioned directory layout:
```text
data/processed/era5_daily/
    processing_manifest.json
    year=1994/
        batch_001.parquet
        batch_002.parquet
        ...
```

### Storage Characteristics:
- **Format:** Apache Parquet with Snappy compression (`compression="snappy"`).
- **Partitioning:** Partitioned by calendar year (`year=YYYY`), mirroring the extraction chunk structure.
- **Determinism:** Rows are deterministically sorted by `(latitude, longitude, date)`.
- **Atomic Writes:** Parquet files are written to temporary files and atomically renamed.
- **Git Protection:** `data/processed/*` is ignored by `.gitignore` (verified via `git check-ignore`).

---

## 9. Processing Manifest & Idempotency

A dedicated manifest tracks daily processing status at:
`data/processed/era5_daily/processing_manifest.json`

### Manifest Fields:
- `chunk_id`: Unique chunk identifier (e.g. `era5_1994_batch_001`)
- `year`, `batch_id`: Chunk scope
- `source_raw_path`: Path to source `.json.gz`
- `input_sha256`: SHA-256 of uncompressed raw payload
- `output_path`: Path to target Parquet file
- `output_record_count`: Number of daily records written
- `quality_summary`: Counts of complete vs. incomplete days
- `processing_version`: Processing engine version
- `status`: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, or `VALIDATION_FAILED`

### Cache & Reprocessing Rules:
- **Cache Hit:** If `status == SUCCEEDED`, target Parquet exists and is non-empty, and recorded `input_sha256` equals current raw payload hash, the chunk is skipped (`SKIPPED (CACHED)`).
- **Cache Invalidation:** If the raw input payload SHA-256 changes or the Parquet file is missing, the chunk is reprocessed automatically.

---

## 10. Controlled Empirical Test: `era5_1994_batch_001`

### Execution Details:
- **Raw Chunk:** `data/raw/era5_historical/year=1994/batch_001.json.gz`
- **Payload SHA-256:** `b6aaa5d92b6572a3b22ee14e0292df056f1a6348192d2da6a55a36a0927de4f9`
- **Output Parquet:** `data/processed/era5_daily/year=1994/batch_001.parquet`
- **Output Records:** Exactly **3,650 daily records** (10 grid cells $\times$ 365 calendar days).
- **Completeness:** 3,650 complete days (100%), 0 incomplete days.
- **Calendar Bounds:** `1994-01-01` verified, `1994-12-31` verified, `1994-02-29` verified absent.
- **Key Uniqueness:** Zero duplicate `(latitude, longitude, date)` tuples.
- **Idempotency:** Second run logged `[era5_1994_batch_001] Skipped (Cached)` with zero file re-writes.

---

## 11. Numerical Spot Checks

Four sample points were compared directly against the uncompressed raw JSON payload:

| Spot Check Description | Coordinates | Date | Raw Hourly Calculation | Parquet Value | Match |
| :--- | :---: | :---: | :--- | :--- | :---: |
| **Max Precipitation Day** | (12.00°, 75.75°) | 1994-07-14 | $\sum P_h = 73.0\text{ mm}$<br>$\text{Mean } T = 24.3958^\circ\text{C}$<br>$\text{Min } T = 23.0^\circ\text{C}, \text{Max } T = 25.2^\circ\text{C}$<br>$\text{Mean RH} = 98.625\%$<br>$\text{Mean SP} = 998.5333\text{ hPa}$ | $73.0\text{ mm}$<br>$24.3958^\circ\text{C}$<br>$23.0^\circ\text{C}, 25.2^\circ\text{C}$<br>$98.625\%$<br>$998.5333\text{ hPa}$ | **EXACT** |
| **Winter Dry Day** | (11.50°, 76.50°) | 1994-01-01 | $\sum P_h = 0.0\text{ mm}$<br>$\text{Mean } T = 20.5375^\circ\text{C}$<br>$\text{Min } T = 15.7^\circ\text{C}, \text{Max } T = 27.6^\circ\text{C}$<br>$\text{Mean RH} = 75.7917\%$<br>$\text{Mean SP} = 909.1375\text{ hPa}$ | $0.0\text{ mm}$<br>$20.5375^\circ\text{C}$<br>$15.7^\circ\text{C}, 27.6^\circ\text{C}$<br>$75.7917\%$<br>$909.1375\text{ hPa}$ | **EXACT** |
| **Monsoon Day** | (11.75°, 76.00°) | 1994-07-15 | $\sum P_h = 29.9\text{ mm}$<br>$\text{Mean } T = 20.1667^\circ\text{C}$<br>$\text{Min } T = 19.3^\circ\text{C}, \text{Max } T = 21.8^\circ\text{C}$<br>$\text{Mean RH} = 98.125\%$<br>$\text{Mean SP} = 924.9542\text{ hPa}$ | $29.9\text{ mm}$<br>$20.1667^\circ\text{C}$<br>$19.3^\circ\text{C}, 21.8^\circ\text{C}$<br>$98.125\%$<br>$924.9542\text{ hPa}$ | **EXACT** |
| **Post-Monsoon Day** | (12.00°, 75.75°) | 1994-10-20 | $\sum P_h = 2.8\text{ mm}$<br>$\text{Mean } T = 26.0125^\circ\text{C}$<br>$\text{Min } T = 22.7^\circ\text{C}, \text{Max } T = 29.4^\circ\text{C}$<br>$\text{Mean RH} = 89.625\%$<br>$\text{Mean SP} = 1002.2458\text{ hPa}$ | $2.8\text{ mm}$<br>$26.0125^\circ\text{C}$<br>$22.7^\circ\text{C}, 29.4^\circ\text{C}$<br>$89.625\%$<br>$1002.2458\text{ hPa}$ | **EXACT** |

---

## 12. Database Safety Verification

PostgreSQL row counts before and after Phase 3.11 execution:

| Table | Pre-Execution Count | Post-Execution Count | Change |
| :--- | :---: | :---: | :---: |
| `weather_observations` | 397 | 397 | **0 (Unchanged)** |
| `rainfall_observations` | 397 | 397 | **0 (Unchanged)** |
| `districts` | 31 | 31 | **0 (Unchanged)** |
| `taluks` | 240 | 240 | **0 (Unchanged)** |

---

## 13. Limitations & Future ML Integration Boundary

1. **Spatial Aggregation:** This processing layer operates at the native 0.25° grid level. District-level zonal weighting (e.g. area-weighted average or centroid nearest-neighbor) is not performed here and must be explicitly defined in Phase 3.12 prior to feature generation.
2. **Controlled Scope:** Only one chunk (`era5_1994_batch_001`) was processed in this test. Bulk processing across all extracted chunks remains subject to controlled expansion.
3. **No Target Labelling:** This module does not construct flood target labels or join IFI disaster events.
