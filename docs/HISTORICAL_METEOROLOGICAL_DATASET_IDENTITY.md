# Phase 3.7B — Historical Meteorological Dataset Identity

## Objective

Determine exactly which Open-Meteo historical weather model/dataset can be requested reproducibly for the 1969–1994 historical flood-label period across Karnataka, verify whether the API response explicitly identifies the model, and establish whether precipitation and thermal variables are populated without missing values or unexpected nulls.

This is a validation task only. No production ingestion pipeline is created, no database records are modified, and no machine learning features are generated.

---

## Official API Documentation Evidence

The Open-Meteo Historical Weather API (`https://archive-api.open-meteo.com/v1/archive`) documents several historical models that can be explicitly selected via the `models` query parameter:

1. **`era5` (ECMWF ERA5 Reanalysis):**
   - **Provider:** European Centre for Medium-Range Weather Forecasts (ECMWF).
   - **Spatial Resolution:** 0.25° (~28 km atmospheric grid).
   - **Temporal Resolution:** Hourly, daily.
   - **Documented Availability:** 1940-01-01 to present.
   - **Variables:** Full atmospheric suite including precipitation, temperature at 2m, relative humidity, surface pressure, and wind components.
   - **Category:** `REANALYSIS`.

2. **`era5_land` (ECMWF ERA5-Land Reanalysis):**
   - **Provider:** ECMWF.
   - **Spatial Resolution:** 0.1° (~11 km terrestrial land grid).
   - **Temporal Resolution:** Hourly, daily.
   - **Documented Availability:** 1950-01-01 to present.
   - **Variables:** Land-surface variables (temperature, soil moisture, runoff, etc.).
   - **Category:** `REANALYSIS`.
   - **Crucial Open-Meteo Implementation Note:** In Open-Meteo's `/v1/archive` endpoint implementation, precipitation is **NOT** served under `models=era5_land` (returns 100% nulls).

3. **`best_match` (Default Composite / Blended):**
   - **Provider:** Open-Meteo automated pipeline.
   - **Spatial Resolution:** Variable (combines 0.1° ERA5-Land for surface parameters with 0.25° ERA5 for atmospheric/precipitation parameters).
   - **Temporal Resolution:** Hourly, daily.
   - **Category:** Composite/Blended model output.
   - **Suitability:** Non-transparent composite; unsuitable as an auditable production dataset where provenance must be strictly documented.

4. **`ecmwf_ifs` (ECMWF Integrated Forecasting System):**
   - **Provider:** ECMWF.
   - **Documented Availability:** Operational periods only (2017+).
   - **Category:** Operational Numerical Weather Prediction (NWP) analysis / `MODEL_OUTPUT`.
   - **Historical Span:** Completely lacks multi-decade historical reanalysis coverage for 1969–1994.

---

## Candidate Models

| Model | Exact API Identifier | Spatial Resolution | Documented Availability | Precipitation Available? | Data Type | Empirically Tested? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ECMWF ERA5** | `era5` | 0.25° (~28 km) | 1940-01-01 to present | **YES** (Populated) | `REANALYSIS` | **YES** |
| **ECMWF ERA5-Land** | `era5_land` | 0.10° (~11 km) | 1950-01-01 to present | **NO** (100% NULL in API) | `REANALYSIS` | **YES** |
| **Best Match** | `best_match` | Variable (0.1° / 0.25°) | 1940-01-01 to present | **YES** (via ERA5 fallback) | `COMPOSITE` | **YES** (Comparison only) |
| **ECMWF IFS** | `ecmwf_ifs` | ~9 km | Modern operational only | **NO** (100% NULL for 1969–1994) | `MODEL_OUTPUT` | **YES** |

---

## Empirical Probe Results

Probes were executed with explicit parameters:
- `timezone=UTC`
- `precipitation_unit=mm`
- `temperature_unit=celsius`
- `hourly=precipitation,temperature_2m,relative_humidity_2m`
- Coordinates:
  - Bengaluru Urban: `(12.9716°N, 77.5946°E)`
  - Belagavi: `(15.8500°N, 74.5000°E)`
- Target Dates:
  - Earliest historical flood date: `1969-07-14` to `1969-07-15` (48 hours)
  - Latest historical flood date: `1994-10-04` to `1994-10-05` (48 hours)

| Date Range | Location (Lat, Lon) | Requested Model | HTTP Status | Hourly Records | Precip Nulls | Temp Nulls | RH Nulls | Returned Grid Coords | Elevation | Response Fields |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1969-07-14 to 1969-07-15** | Bengaluru Urban (12.9716, 77.5946) | `era5` | `200` | 48 | **0** | 0 | 0 | (13.0, 77.5) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Bengaluru Urban (12.9716, 77.5946) | `era5_land` | `200` | 48 | **48 (100%)** | 0 | 0 | (13.0, 77.600006) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Bengaluru Urban (12.9716, 77.5946) | `best_match` | `200` | 48 | **0** | 0 | 0 | (12.970123, 77.56364) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Bengaluru Urban (12.9716, 77.5946) | `ecmwf_ifs` | `200` | 48 | **48 (100%)** | **48 (100%)** | **48 (100%)** | (12.970123, 77.56364) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Bengaluru Urban (12.9716, 77.5946) | `era5` | `200` | 48 | **0** | 0 | 0 | (13.0, 77.5) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Bengaluru Urban (12.9716, 77.5946) | `era5_land` | `200` | 48 | **48 (100%)** | 0 | 0 | (13.0, 77.600006) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Bengaluru Urban (12.9716, 77.5946) | `best_match` | `200` | 48 | **0** | 0 | 0 | (12.970123, 77.56364) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Bengaluru Urban (12.9716, 77.5946) | `ecmwf_ifs` | `200` | 48 | **48 (100%)** | **48 (100%)** | **48 (100%)** | (12.970123, 77.56364) | 910 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Belagavi (15.8500, 74.5000) | `era5` | `200` | 48 | **0** | 0 | 0 | (15.75, 74.5) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Belagavi (15.8500, 74.5000) | `era5_land` | `200` | 48 | **48 (100%)** | 0 | 0 | (15.900002, 74.5) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Belagavi (15.8500, 74.5000) | `best_match` | `200` | 48 | **0** | 0 | 0 | (15.852372, 74.53258) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1969-07-14 to 1969-07-15** | Belagavi (15.8500, 74.5000) | `ecmwf_ifs` | `200` | 48 | **48 (100%)** | **48 (100%)** | **48 (100%)** | (15.852372, 74.53258) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Belagavi (15.8500, 74.5000) | `era5` | `200` | 48 | **0** | 0 | 0 | (15.75, 74.5) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Belagavi (15.8500, 74.5000) | `era5_land` | `200` | 48 | **48 (100%)** | 0 | 0 | (15.900002, 74.5) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Belagavi (15.8500, 74.5000) | `best_match` | `200` | 48 | **0** | 0 | 0 | (15.852372, 74.53258) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |
| **1994-10-04 to 1994-10-05** | Belagavi (15.8500, 74.5000) | `ecmwf_ifs` | `200` | 48 | **48 (100%)** | **48 (100%)** | **48 (100%)** | (15.852372, 74.53258) | 782 m | `[lat, lon, gen_ms, utc_offset, tz, tz_abbr, elev, hourly_units, hourly]` |

---

## Dataset Identity Finding

### 1. Explicit Model Identity in API Response
- **Empirical Finding:** The Open-Meteo HTTP response payload **does NOT contain any explicit model identifier**.
- **Payload Inspection:** The JSON response contains only:
  `['latitude', 'longitude', 'generationtime_ms', 'utc_offset_seconds', 'timezone', 'timezone_abbreviation', 'elevation', 'hourly_units', 'hourly']`.
  There is no `model`, `model_id`, or `model_name` field returned.
- **Deduction Constraint:** It is impossible to confirm from the response body alone which model generated the numbers. The model identity is determined solely by client request routing (`models=era5`) and confirmed through secondary physical evidence (grid coordinate snapping).

### 2. Secondary Physical Evidence: Grid Snapping
- When `models=era5` is passed:
  - Input `(12.9716, 77.5946)` returns `(13.0, 77.5)` — snapped exactly to the 0.25° ERA5 atmospheric grid.
  - Input `(15.8500, 74.5000)` returns `(15.75, 74.5)` — snapped exactly to the 0.25° ERA5 atmospheric grid.
- When `models=era5_land` is passed:
  - Input `(12.9716, 77.5946)` returns `(13.0, 77.600006)` — snapped to the 0.1° ERA5-Land terrestrial grid.
  - Input `(15.8500, 74.5000)` returns `(15.900002, 74.5)` — snapped to the 0.1° ERA5-Land terrestrial grid.
- This confirms that passing `models=era5` routes to the 0.25° ERA5 reanalysis grid, whereas `models=era5_land` routes to the 0.1° ERA5-Land grid.

### 3. ERA5 vs. ERA5-Land Non-Interchangeability
- **Precipitation Deficit:** `era5_land` returns **100% null values for precipitation** in all historical queries (`precip_nulls = 48 / 48`).
- **Conclusion:** `era5_land` cannot serve as a standalone historical meteorological dataset for flood modeling. `era5` must be used for precipitation.
- **Best Match Caveat:** `best_match` achieves non-null precipitation by silently combining ERA5 precipitation (at 0.25°) with ERA5-Land temperature (at 0.1°), but provides no metadata explaining this blend.

### 4. What Remains Unverified
- Continuous day-by-day availability across the full 1969–1994 interval (only test dates have been probed).
- Exact numerical consistency across repeated extractions over time.
- Completeness of all 31 Karnataka district representations on the 0.25° grid.

---

## Selection Status

| Model | Status | Rationale |
| :--- | :--- | :--- |
| **`era5`** | **VERIFIED FOR NEXT VALIDATION GATE** | Supported at both test dates (`1969-07-14`, `1994-10-04`), returns 0 nulls for precipitation, temperature, and relative humidity, and snaps deterministically to the documented 0.25° ERA5 grid. |
| **`era5_land`** | **BLOCKED (for precipitation) / CONDITIONALLY VERIFIED (for thermal variables only)** | 100% null values for precipitation across all tested historical queries. Cannot serve as a primary flood-ML dataset. |
| **`best_match`** | **BLOCKED** | Non-transparent composite that blends multiple underlying models without explicit metadata in the response. |
| **`ecmwf_ifs`** | **BLOCKED** | 100% null values for all variables during the historical 1969–1994 period. |

> [!IMPORTANT]
> **VERIFIED FOR NEXT VALIDATION GATE** indicates that `era5` is technically qualified to proceed to Gate 2. It does **NOT** mean that production ingestion is approved.

---

## Phase 3.7B Gate 2 Prerequisites

Before production ingestion can be approved or implemented, Gate 2 must perform:

1. **Continuous Temporal Completeness:** Perform a systematic multi-decade audit across 1969-07-14 to 1994-10-05 (9,215 days) to verify that no missing days, empty records, or data dropouts exist in `era5`.
2. **Karnataka Grid Construction & PostGIS Intersection:** Construct the theoretical 0.25° ERA5 grid in PostGIS, intersect it with official Karnataka state and district boundaries (`admin_boundaries`), and verify that all 31 districts contain valid intersecting grid cells.
3. **Missing / Null Analysis:** Measure null and invalid rates across all four required variables (`precipitation`, `temperature_2m`, `relative_humidity_2m`, `surface_pressure`) over extended multi-year windows.
4. **Unit and Timestamp Validation:** Empirically verify timestamp semantics (UTC vs. IST offset), ensure precipitation is cumulative or hourly flux, and check that units match project database specifications.
5. **Reproducible Extraction Test:** Execute repeated queries for identical coordinate/time pairs to prove bitwise/numerical determinism.
6. **Request-Volume Feasibility:** Evaluate API rate limits (10,000 daily requests, concurrency constraints, latency per call) using a small representative batch workload.
7. **Independent Precipitation Cross-Check:** Cross-reference `era5` precipitation values against independent observational records (e.g. IMD gridded daily rainfall or CWC station logs) for a documented historical storm event.
