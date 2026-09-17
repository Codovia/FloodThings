# Data Semantics & Provenance Audit

**Phase**: 2.4.1 (Data Semantics & Provenance Correction)  
**Date**: September 2026  
**Status**: APPROVED & APPLIED  
**Migration ID**: `ccfc6a6b5d06`  

---

## 1. Executive Summary

Prior to commencing Phase 2.5 (Automated Background Ingestion) and Phase 3 (Machine Learning & Hydrological Modeling), an exhaustive scientific audit of the data ingested during Phase 2.4 was conducted. 

The audit identified a critical scientific distinction: **numerical weather model outputs and atmospheric reanalysis had been ingested into tables named `*_observations` without explicit semantic provenance tags**. In physical hydrology and meteorology, treating gridded model outputs or reanalyses as physical station measurements introduces severe bias and invalidates scientific assumptions (e.g., ground-truth validation of weather forecasts against "observations" that are actually model predictions from the same model family).

To rectify this, Phase 2.4.1:
1. Introduced an explicit, validated `data_category` provenance column on all observation tables.
2. Backfilled all 1,181 live records with scientifically accurate provenance classifications.
3. Updated all source adapters to assign `data_category` deterministically upon ingestion.
4. Purged integration test fixtures from production database tables and hardened the test suite with automated teardowns.
5. Formally documented data semantics for downstream feature engineering and ML training.

---

## 2. Scientific Data Hierarchy

Per `MASTER_PROJECT_SPEC.md` §6 and `DATA_CONTRACT.md`, FloodPulse strictly distinguishes among the following data states:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA PROVENANCE HIERARCHY                       │
├──────────────────┬─────────────────────────────────────────────────────┤
│ Category         │ Definition & Physical Nature                        │
├──────────────────┼─────────────────────────────────────────────────────┤
│ OBSERVATION      │ Physical in-situ measurement from sensors, staff    │
│                  │ gauges, or manual field observers.                  │
│                  │                                                     │
│ REANALYSIS       │ Gridded model reconstruction of past atmospheric    │
│                  │ conditions synthesizing observations and physics    │
│                  │ (e.g., ECMWF ERA5, ERA5-Land).                      │
│                  │                                                     │
│ MODEL_OUTPUT     │ Operational Numerical Weather Prediction (NWP)      │
│                  │ hindcast or nowcast from deterministic models       │
│                  │ (e.g., ICON, GFS).                                  │
│                  │                                                     │
│ FORECAST         │ Forward-looking model simulation for future         │
│                  │ timestamps (stored in separate forecast tables).   │
│                  │                                                     │
│ HISTORICAL_EVENT │ Curated historical disaster catalog or event record │
│                  │ documenting flood impacts and extents.             │
│                  │                                                     │
│ REFERENCE        │ Static authoritative administrative or geographic   │
│                  │ reference dataset (e.g., LGD, Survey of India).     │
└──────────────────┴─────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Database Audit (Live Verification)

The table below details the verified live database state as of Phase 2.4.1 completion:

| Table | Live Count | Source Provider | Physical Nature | Assigned `data_category` | Downstream ML Usage |
|---|---|---|---|---|---|
| `weather_observations` | 325 | Open-Meteo Operational | 0.1° gridded NWP model nowcast | `MODEL_OUTPUT` | Input feature (proxy weather) |
| `weather_observations` | 72 | Open-Meteo Archive | 0.1° ERA5 atmospheric reanalysis | `REANALYSIS` | Historical training feature |
| `rainfall_observations` | 325 | Open-Meteo Operational | 0.1° gridded NWP model nowcast | `MODEL_OUTPUT` | Input feature (proxy precipitation) |
| `rainfall_observations` | 72 | Open-Meteo Archive | 0.1° ERA5-Land precipitation reanalysis | `REANALYSIS` | Historical training feature |
| `weather_forecasts` | 275 | Open-Meteo Operational | 72-hour forward NWP prediction | N/A (table semantics) | Early-warning trigger feature |
| `river_observations` | 101 | CWC / NWIC | Manual gauge reading at river station | `OBSERVATION` | Ground-truth hydrological state |
| `reservoir_observations` | 100 | WRD Karnataka / NWIC | Daily dam log (level, storage, inflow) | `OBSERVATION` | Ground-truth reservoir state |
| `flood_events` | 100 | India Flood Inventory v3.0 | Curated event catalog (2018–2023) | N/A (event catalog) | Historical validation benchmark |
| `flood_observations` | 186 | India Flood Inventory v3.0 | District-level flood occurrence ground truth | `HISTORICAL_EVENT` | ML training classification label |
| `districts` | 31 | Local Government Directory (LGD) | Authoritative administrative boundaries | `REFERENCE` | Spatial aggregation & join key |

**Total unclassified records (`data_category IS NULL`) across all tables:** `0`  
**Total test fixture residue records across all tables:** `0`  

---

## 4. Deep-Dive Findings & Corrections

### Finding 1: Open-Meteo Weather Data Is Gridded Model Output, Not Physical Observations

- **Finding**: Open-Meteo does not own or operate physical weather stations. Their `/v1/forecast` endpoint provides numerical weather prediction (NWP) model runs (ICON from DWD, GFS from NOAA, ECMWF IFS), while their `/v1/archive` endpoint provides ECMWF ERA5 reanalysis. Storing these into `weather_observations` without category tags creates the false impression of in-situ gauge readings.
- **Correction**: 
  - Records from `/v1/forecast` with past timestamps (`openmeteo_obs_*`, `openmeteo_rain_*`) are classified as `data_category = 'MODEL_OUTPUT'`.
  - Records from `/v1/archive` (`openmeteo_hist_obs_*`, `openmeteo_hist_rain_*`) are classified as `data_category = 'REANALYSIS'`.
  - The adapter `OpenMeteoAdapter` explicitly assigns `DataCategory.MODEL_OUTPUT` for operational queries and `DataCategory.REANALYSIS` for archive queries.

### Finding 2: Hydrological Telemetry Is Physical In-Situ Measurement

- **Finding**: NWIC CWC river level telemetry (`rwl_manual_hr_cwc_*.csv`) and Karnataka reservoir telemetry (`karnataka_man_reservoir_data.csv`) represent actual physical readings taken at dam gauges and river gauging stations by central and state irrigation staff.
- **Correction**:
  - `river_observations` tagged with `data_category = 'OBSERVATION'`.
  - `reservoir_observations` tagged with `data_category = 'OBSERVATION'`.
  - Adapters `NwicRiverLevelAdapter` and `NwicReservoirAdapter` set `DataCategory.OBSERVATION`.

### Finding 3: Flood Catalog Ground Truth Is Historical Event Documentation

- **Finding**: India Flood Inventory (IFI v3.0) provides ground truth of flood disaster occurrences compiled from official state disaster management authorities, relief commissioners, and news archives. It does not measure continuous physical water depth.
- **Correction**:
  - `flood_observations` tagged with `data_category = 'HISTORICAL_EVENT'`.
  - Missing `flood_depth` remains strictly `NULL` (`missing != 0`).
  - Adapter `IfiFloodAdapter` sets `DataCategory.HISTORICAL_EVENT`.

### Finding 4: Test Residue Isolation

- **Finding**: Integration tests executing against the local database (`Test Loc`, `Idemp Loc`, `IDEMP_STN`, `IDEMP_RES`, `UEI-IDEMP-KA-001`) committed fixtures that remained in production tables.
- **Correction**:
  - Alembic migration `ccfc6a6b5d06` pruned all legacy test fixtures.
  - All ingestion tests in `tests/test_ingestion_adapters.py` and `tests/test_ingestion_idempotency.py` were refactored with guaranteed `try...finally` teardowns.
  - Test suite now passes with 52 tests and leaves 0 residual records in the database.

---

## 5. Database Schema Changes & Constraints

### 5.1 Added Columns

The column `data_category VARCHAR(30)` was added to:
- `weather_observations`
- `rainfall_observations`
- `river_observations`
- `reservoir_observations`
- `flood_observations`

### 5.2 Check Constraints Enforced

Each table enforces valid categories via a PostgreSQL CHECK constraint:
```sql
CONSTRAINT ck_weather_obs_data_category CHECK (
    data_category IS NULL OR data_category IN (
        'OBSERVATION', 'REANALYSIS', 'MODEL_OUTPUT', 'FORECAST', 'HISTORICAL_EVENT', 'REFERENCE'
    )
)
```
(Identical check constraints created for `ck_rainfall_obs_data_category`, `ck_river_obs_data_category`, `ck_reservoir_obs_data_category`, and `ck_flood_obs_data_category`).

---

## 6. Guidelines for Downstream Phases

### Phase 2.5: Automated Ingestion & Health Monitoring
- Health metrics must report ingestion volume partitioned by `data_category`.
- Alerts must distinguish between station sensor outages (`OBSERVATION` pipeline delay) and upstream model provider downtime (`MODEL_OUTPUT` / `REANALYSIS` API errors).

### Phase 3: Feature Engineering & Model Training
- **Ground Truth Target**: Supervised classification models for flood inundation must train on `flood_observations` (`HISTORICAL_EVENT`) with `flooded = TRUE` / `FALSE`.
- **Weather Features**: Feature pipelines must be aware that historical features are `REANALYSIS` (ERA5), while real-time inference uses `MODEL_OUTPUT` (nowcasts) and `FORECAST` (NWP predictions). Feature distributions between ERA5 and operational GFS/ICON must be checked for covariate shift.
- **Hydrological Verification**: Hydrological routing models must calibrate against `river_observations` (`OBSERVATION`) and `reservoir_observations` (`OBSERVATION`). Never calibrate a physical discharge model against synthetic or reanalysis water levels.
