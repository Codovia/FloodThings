# Pre-Phase 2.5 Data & Source Coverage Audit

**Project:** FloodPulse  
**Audit Date:** September 2026  
**Auditor:** Data Source & Pipeline Architecture Specialist  
**Current Commit:** `ddec612` (Phase 2.4.1 Complete)  
**Database Host:** PostgreSQL 16 + PostGIS 3.4 (`floodpulse-postgres`)  
**Audit Nature:** Read-Only Empirical Audit  

---

## 1. Audit Scope

This audit establishes the empirical baseline of FloodPulse's live database, ingestion framework, and documented source ecosystem prior to implementing Phase 2.5 (Automated Background Ingestion & Source-Health Monitoring).

### Scope Boundaries:
- Read-only inspection of all 34 database tables, 5 active source adapters, and Alembic migrations.
- Direct query-based extraction of timestamp boundaries, category distributions, nullability metrics, and spatial geometries.
- Verification of accessibility tiers for all candidate data providers documented in Phase 2.3 and Phase 2.4.
- Zero modifications to database records, schema, adapter logic, or production code during this audit.

---

## 2. Database Snapshot

The live PostgreSQL database contains 34 registered application tables. The table below reports the exact row count across all core entities:

| Domain | Table Name | Total Rows | Nature / Purpose |
|---|---|---|---|
| **Environmental** | `weather_observations` | **397** | Gridded operational nowcasts & ERA5 reanalysis |
| **Environmental** | `rainfall_observations` | **397** | Hourly precipitation proxy records |
| **Environmental** | `weather_forecasts` | **275** | 72-hour forward NWP predictions |
| **Environmental** | `river_observations` | **101** | In-situ manual river stage gauge readings |
| **Environmental** | `river_forecasts` | **0** | Gridded discharge forecasts (not yet populated) |
| **Environmental** | `reservoir_observations` | **100** | Daily dam levels, storage, inflow, outflow |
| **Environmental** | `flood_events` | **100** | Historical documented flood event catalog |
| **Environmental** | `flood_observations` | **186** | Ground-truth district flood binary targets |
| **Registry** | `data_sources` | **5** | Authoritative data provider registrations |
| **Registry** | `data_ingestion_runs` | **148** | Ingestion run lifecycle & provenance logs |
| **Geography** | `states` | **1** | Karnataka State (LGD: 29) |
| **Geography** | `districts` | **31** | Karnataka Administrative Districts |
| **Geography** | `taluks` | **0** | Sub-district administrative units (unpopulated) |
| **Geography** | `localities` | **0** | Urban / village localities (unpopulated) |
| **Hydrology** | `river_basins` | **2** | Cauvery and Krishna River Basins |
| **Hydrology** | `sub_basins` | **0** | Hydrological sub-basins (unpopulated) |
| **Hydrology** | `rivers` | **2** | Cauvery and Krishna main stems |
| **Hydrology** | `river_stations` | **1** | CWC Gauging Station (`AKKIHEBBAL`) |
| **Hydrology** | `reservoirs` | **1** | Major Dam Entity (`Almatti Dam`) |
| **Modeling** | `prediction_grid_cells` | **0** | 0.05° spatial prediction grid (Phase 3 scope) |
| **Facilities** | `emergency_facilities` | **0** | Hospitals / fire stations (Phase 2.4+ batch scope) |

*Zero-row tables are expected at this project phase and reflect strict unpopulated status rather than system degradation.*

---

## 3. Environmental Data Coverage

Every populated environmental table was queried for timestamps, category distributions, source attribution, and field nullability:

### 3.1 `weather_observations`
- **Total Rows:** 397
- **Timestamp Range (`observed_at`):** `2024-07-01 00:00:00+00:00` to `2026-09-17 16:00:00+00:00`
- **Data Category Distribution:**
  - `MODEL_OUTPUT`: 325 (81.9%) — Operational past 2 days from Open-Meteo
  - `REANALYSIS`: 72 (18.1%) — ERA5 archive reanalysis
- **Source Attribution:** `Open-Meteo Weather API` (397 records, 100%)
- **Nullability Analysis:**
  - `temperature`, `humidity`, `pressure`, `wind_speed`, `wind_direction`: **0 NULLs** (100% complete)
  - `geometry`: **0 NULLs** (all 397 have valid `POINT` geometries)
  - `district_id`: **0 NULLs** (all linked to valid LGD districts)
  - `quality_status`: **0 NULLs** (all `VALID`)
  - `data_category`: **0 NULLs**

### 3.2 `rainfall_observations`
- **Total Rows:** 397
- **Timestamp Range (`observed_at`):** `2024-07-01 00:00:00+00:00` to `2026-09-17 16:00:00+00:00`
- **Data Category Distribution:**
  - `MODEL_OUTPUT`: 325 (81.9%)
  - `REANALYSIS`: 72 (18.1%)
- **Source Attribution:** `Open-Meteo Weather API` (397 records, 100%)
- **Nullability Analysis:**
  - `rainfall_mm`: **0 NULLs** (all valid floats $\ge 0.0$)
  - `duration_minutes`: **0 NULLs** (all 60 min)
  - `geometry`, `district_id`, `quality_status`, `data_category`: **0 NULLs**

### 3.3 `weather_forecasts`
- **Total Rows:** 275
- **Timestamp Range (`forecast_for`):** `2026-09-17 17:00:00+00:00` to `2026-09-19 23:00:00+00:00`
- **Data Category:** Forecasts are stored in a dedicated forecast entity table; `data_category` column is not applicable.
- **Source Attribution:** `Open-Meteo Weather API` (275 records, 100%)
- **Nullability Analysis:**
  - `issued_at`, `temperature`, `forecast_rainfall_mm`, `humidity`, `wind_speed`: **0 NULLs**
  - `quality_status`: **0 NULLs** (all `VALID`)
  - `district_id`: **0 NULLs**

### 3.4 `river_observations`
- **Total Rows:** 101
- **Timestamp Range (`observed_at`):** `2026-01-02 02:30:00+00:00` to `2026-06-04 20:30:00+00:00`
- **Data Category Distribution:** `OBSERVATION`: 101 (100%) — Physical in-situ manual gauge readings
- **Source Attribution:** `NWIC Central Water Commission River Gauge Telemetry` (101 records, 100%)
- **Nullability Analysis:**
  - `water_level`: **0 NULLs** (all valid positive floats in metres)
  - `water_level_unit`: **0 NULLs** (all `m`)
  - `discharge`: **101 NULLs (100%)** — Strictly preserved as `NULL` because CWC hourly manual stage logs do not contain discharge measurements (`missing ≠ 0`)
  - `warning_level`, `danger_level`, `highest_flood_level`: **101 NULLs (100%)** — Not populated in raw manual stage CSV
  - `quality_status`: **0 NULLs** (all `VALID`)
  - `station_id`: **0 NULLs** (all linked to `AKKIHEBBAL`)

### 3.5 `river_forecasts`
- **Total Rows:** 0
- **Status:** Unpopulated. GloFAS/Open-Meteo Flood integration planned for Phase 3 hydrological baseline.

### 3.6 `reservoir_observations`
- **Total Rows:** 100
- **Timestamp Range (`observed_at`):** `2006-06-08 06:36:00+00:00` to `2008-02-08 06:32:00+00:00`
- **Data Category Distribution:** `OBSERVATION`: 100 (100%) — Physical in-situ daily dam monitoring logs
- **Source Attribution:** `NWIC Karnataka Reservoir Telemetry` (100 records, 100%)
- **Nullability Analysis:**
  - `water_level`: **0 NULLs** (converted from feet to metres)
  - `storage`: **0 NULLs** (converted from TMC to MCM)
  - `inflow`: **0 NULLs** (converted from cusecs to m³/s)
  - `outflow`: **0 NULLs** (converted from cusecs to m³/s)
  - `storage_percentage`: **100 NULLs (100%)** — Blank/unusable in the top 100 rows of the raw CSV
  - `quality_status`: **0 NULLs** (all `VALID`)
  - `reservoir_id`: **0 NULLs** (all linked to `Almatti Dam`)

### 3.7 `flood_events`
- **Total Rows:** 100
- **Timestamp Range (`start_time`):** `1969-07-14 18:30:00+00:00` to `1994-10-05 18:30:00+00:00`
- **Source Attribution:** `India Flood Inventory (IFI v3.0)` (100 records, 100%)
- **Nullability Analysis:**
  - `end_time`: **0 NULLs**
  - `severity`: **0 NULLs** (e.g. `Class 1`, `Class 2`)
  - `confidence`: **0 NULLs** (all `1.0`)
  - `affected_area`: **100 NULLs (100%)** — Not reported in raw records
  - `geometry`: **100 NULLs (100%)** — Catalog provides district-level tabular event data, not spatial flood boundary polygons

### 3.8 `flood_observations`
- **Total Rows:** 186
- **Timestamp Range (`observation_time`):** `1969-07-14 18:30:00+00:00` to `1994-10-05 18:30:00+00:00`
- **Data Category Distribution:** `HISTORICAL_EVENT`: 186 (100%)
- **Source Attribution:** `India Flood Inventory (IFI v3.0)` (186 records, 100%)
- **Nullability Analysis:**
  - `flooded`: **0 NULLs** (all `true`)
  - `flood_depth`: **186 NULLs (100%)** — Flood depth is unmeasured; strictly kept as `NULL` per `DATA_CONTRACT.md`
  - `district_id`: **0 NULLs** (all 186 linked to valid Karnataka districts)
  - `taluk_id`, `basin_id`: **186 NULLs (100%)** — Ground truth is at district resolution
  - `geometry`: **186 NULLs (100%)** — Tabular ground truth; no satellite inundation polygon

---

## 4. Geographic Coverage

The audit evaluated actual spatial representations across all levels of administrative, hydrological, and environmental geometry:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   GEOGRAPHIC REPRESENTATION MATRIX                     │
├─────────────────────┬───────┬───────────────────┬──────────────────────┤
│ Entity              │ Count │ Spatial Form      │ Geometry Column      │
├─────────────────────┼───────┼───────────────────┼──────────────────────┤
│ State (Karnataka)   │ 1     │ Identity only     │ geometry: NULL       │
│ Districts           │ 31    │ Centroid Point    │ centroid: POINT      │
│                     │       │ (No boundary)     │ geometry: NULL       │
│ Taluks              │ 0     │ Not populated     │ N/A                  │
│ Localities          │ 0     │ Not populated     │ N/A                  │
│ River Basins        │ 2     │ Identity/Code     │ geometry: None       │
│ River Stations      │ 1     │ Point Gauge       │ geometry: POINT      │
│ Reservoirs          │ 1     │ Point Dam         │ geometry: POINT      │
│ Weather Obs         │ 397   │ Point Coordinates │ geometry: POINT      │
│ Weather Forecasts   │ 275   │ Station Ref       │ geometry: None       │
│ Flood Events        │ 100   │ Tabular Event     │ geometry: NULL       │
│ Flood Observations  │ 186   │ District FK       │ geometry: NULL       │
│ Prediction Grid     │ 0     │ Unpopulated       │ N/A                  │
└─────────────────────┴───────┴───────────────────┴──────────────────────┘
```

### Critical Geometric Findings:
1. **Districts:** All 31 Karnataka districts are officially registered with valid LGD codes and verified centroid coordinates stored in `districts.centroid` (`POINT(lon lat)` in EPSG:4326). However, `districts.geometry` (`MULTIPOLYGON`) is **100% NULL**. Boundary polygons are not yet ingested.
2. **Sub-districts:** `taluks` and `localities` tables contain **0 records**.
3. **Weather / Rainfall Monitoring:** Operational weather data is restricted to **5 monitoring points** across Karnataka:
   - Bengaluru (`12.9716, 77.5946`) — Bangalore Urban
   - Mangaluru (`12.8700, 75.2500`) — Dakshina Kannada
   - Kalaburagi (`17.3300, 76.8300`) — Kalaburagi
   - Belagavi (`15.8500, 74.5000`) — Belagavi
   - Mandya (`12.5200, 76.9000`) — Mandya
   *26 of 31 districts currently have zero operational weather records.*
4. **Hydrological Infrastructure:**
   - River stations: exactly **1 station** (`AKKIHEBBAL` on Cauvery river).
   - Reservoirs: exactly **1 reservoir** (`Almatti Dam` on Krishna river).
5. **Flood Ground Truth:** The 186 historical flood observations span **23 distinct Karnataka districts** (top: Bangalore Urban with 23, Davanagere with 13, Mysuru with 13). They represent administrative tabular associations, not satellite inundation footprints.

---

## 5. Temporal Coverage

A rigorous temporal analysis was conducted for each populated source:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TEMPORAL HORIZON AUDIT                            │
├─────────────────────┬──────────────┬──────────────┬──────────┬──────────────┤
│ Series              │ Earliest     │ Latest       │ Count    │ Cadence      │
├─────────────────────┼──────────────┼──────────────┼──────────┼──────────────┤
│ Open-Meteo Archive  │ 2024-07-01   │ 2024-07-03   │ 72       │ 1 hour       │
│ (REANALYSIS)        │ 00:00 UTC    │ 23:00 UTC    │          │ (0 gaps)     │
│                     │              │              │          │              │
│ Open-Meteo Forecast │ 2026-09-15   │ 2026-09-17   │ 325      │ 1 hour       │
│ (MODEL_OUTPUT past) │ 00:00 UTC    │ 16:00 UTC    │ (5 locs) │ (0 gaps)     │
│                     │              │              │          │              │
│ Open-Meteo Forecast │ 2026-09-17   │ 2026-09-19   │ 275      │ 1 hour       │
│ (FORECAST future)   │ 17:00 UTC    │ 23:00 UTC    │ (5 locs) │ (0 gaps)     │
│                     │              │              │          │              │
│ CWC River Stage     │ 2026-01-02   │ 2026-06-04   │ 101      │ 1 hr / gap   │
│ (OBSERVATION)       │ 02:30 UTC    │ 20:30 UTC    │          │ of 149 days  │
│                     │              │              │          │              │
│ NWIC Reservoir Dam  │ 2006-06-08   │ 2008-02-08   │ 100      │ Daily / gaps │
│ (OBSERVATION)       │ 06:36 UTC    │ 06:32 UTC    │          │ 1-17 days    │
│                     │              │              │          │              │
│ IFI Flood Inventory │ 1969-07-14   │ 1994-10-05   │ 100 ev / │ Episodic     │
│ (HISTORICAL_EVENT)  │ 18:30 UTC    │ 18:30 UTC    │ 186 obs  │ event dates  │
└─────────────────────┴──────────────┴──────────────┴──────────┴──────────────┘
```

### Detailed Findings:
- **Open-Meteo REANALYSIS:** Ingested for Bengaluru over a 3-day calibration sample (July 1–3, 2024). Cadence is strictly hourly without missing intervals.
- **Open-Meteo MODEL_OUTPUT:** Ingested across 5 locations spanning 65 hours (2.7 days). Cadence is strictly hourly without missing intervals.
- **Open-Meteo FORECAST:** 55 hourly forecast steps per location extending 55 hours into the future.
- **CWC River Stage (`AKKIHEBBAL`):** 99 consecutive hourly readings from Jan 2–6, 2026, followed by a **149-day gap** to a single observation on June 4, 2026.
- **NWIC Reservoir (`Almatti Dam`):** Covers June 2006 to February 2008. Contains 58 1-day intervals, but has frequent multi-day reporting gaps (13 gaps of 8 days, 12 gaps of 2 days, 7 gaps of 16–17 days). *Crucially: this dataset contains no recent 2024–2026 observations.*
- **IFI Flood Ground Truth:** The 100 ingested flood disaster events cover 1969 to 1994 (the first 100 Karnataka rows of the IFI v3.0 catalog). The remaining 1995–2023 catalog rows are not yet loaded.

---

## 6. Source Accessibility

Based on empirical probing from Phase 2.3 (`API_VALIDATION_LAB.md`) and Phase 2.4, external sources are classified into six distinct operational tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                       SOURCE ACCESSIBILITY TIERS                       │
├──────────────────────────┬─────────────────────────────────────────────┤
│ Tier                     │ Assigned Sources                            │
├──────────────────────────┼─────────────────────────────────────────────┤
│ OPEN                     │ 1. Open-Meteo Weather & Forecast API        │
│                          │ 2. Open-Meteo Historical Archive API        │
│                          │ 3. Open-Meteo Flood API (GloFAS)            │
│                          │                                             │
│ OPEN_WITH_LIMITATIONS    │ 4. NWIC CWC River Level CSV                 │
│                          │    (Open data, but monolithic CSV tranche)  │
│                          │ 5. NWIC Reservoir Telemetry CSV             │
│                          │    (Open data, but static historical window)│
│                          │ 6. India Flood Inventory v3.0               │
│                          │    (Public GitHub repo, static batch CSV)   │
│                          │ 7. OpenStreetMap Overpass API               │
│                          │    (Open, but strict rate limits/timeouts)  │
│                          │                                             │
│ CREDENTIAL_REQUIRED      │ 8. IMD Official API Gateway                 │
│                          │    (Mandatory API key; gov domain required) │
│                          │ 9. Copernicus Climate Data Store (GloFAS)   │
│                          │    (Requires API token + accepted license)  │
│                          │                                             │
│ RESTRICTED               │ 10. NRSC NDEM Disaster Portal               │
│                          │     (Restricted officer OTP login)          │
│                          │ 11. IDRN Emergency Resource Portal          │
│                          │     (Government DC/DM credentials only)     │
│                          │                                             │
│ REFERENCE_ONLY           │ 12. Local Government Directory (LGD)        │
│                          │ 13. Copernicus DEM GLO-30 (AWS Open Data)   │
│                          │ 14. Datameet Census 2011 Shapefiles         │
│                          │ 15. Curated DDMP PDF Shelters               │
│                          │                                             │
│ NOT_CURRENTLY_           │ 16. IMD Pune Gridded Binary (`imdlib` gated)│
│ AUTOMATABLE              │ 17. Bhuvan OGC Flood Hazard WMS             │
│                          │ 18. Live Intra-Day Dam Spillway Webhooks    │
└──────────────────────────┴─────────────────────────────────────────────┘
```

---

## 7. Adapter Audit

Each of the 5 implemented source adapters was audited for repeatability, idempotency, and operational robustness:

### 7.1 `OpenMeteoAdapter`
- **Source:** Open-Meteo Weather API (`https://api.open-meteo.com`)
- **Input:** Lat/lon pairs, start/end dates, mode (`operational` vs `historical`).
- **Output Tables:** `weather_observations`, `rainfall_observations`, `weather_forecasts`.
- **Data Category:** `MODEL_OUTPUT` (operational past), `REANALYSIS` (historical archive).
- **Idempotency Mechanism:** Deduplication query using compound key `(source_id, source_record_id)` where record ID is `openmeteo_[obs|rain|fcst]_[lat]_[lon]_[iso_dt]`.
- **Duplicate Handling:** Skips insertion; increments `records_valid` without duplicate error.
- **Failure Behavior:** Rolls back active session transaction, logs exception to `DataIngestionRun.error_message`, marks status `FAILED`.
- **Timestamp Handling:** Standardized via `parse_utc_timestamp(..., default_tz=timezone.utc)` to timezone-aware UTC.
- **Geographic Handling:** Validates WGS84 coordinates, constructs PostGIS `POINT` geometry via `make_point_wkt()`.
- **Credential Requirement:** None (Open REST API, 10,000 req/day).
- **Automation Readiness:** **HIGH (Ready for background scheduler)**.

### 7.2 `NwicRiverLevelAdapter`
- **Source:** Central Water Commission via NWIC (`nwdp.nwic.gov.in`).
- **Input:** Remote CSV URL or raw string content.
- **Output Tables:** `river_basins`, `rivers`, `river_stations`, `river_observations`.
- **Data Category:** `OBSERVATION`.
- **Idempotency Mechanism:** Station code uniqueness for stations; `cwc_{station}_{observed_at_compact}` for observations.
- **Duplicate Handling:** Idempotent skip on conflict; entity caching prevents duplicate basin/river creation.
- **Failure Behavior:** Logs invalid rows to `metrics.errors`, flags status `PARTIAL` if errors occur, `FAILED` on unhandled exception.
- **Timestamp Handling:** Parses IST formatted string `DD-MM-YYYY HH:mm` to UTC `TIMESTAMPTZ`.
- **Geographic Handling:** Point coordinates validated within Karnataka envelope.
- **Credential Requirement:** None (Open Data CSV).
- **Automation Readiness:** **MEDIUM (Requires cached tranche handling or download retry/backoff)**.

### 7.3 `NwicReservoirAdapter`
- **Source:** Karnataka Water Resources Department via NWIC.
- **Input:** Remote CSV URL or raw string content.
- **Output Tables:** `river_basins`, `rivers`, `reservoirs`, `reservoir_observations`.
- **Data Category:** `OBSERVATION`.
- **Idempotency Mechanism:** Deduplication query on `(source_id, nwic_res_{code}_{timestamp})`.
- **Duplicate Handling:** Idempotent skip; in-memory cache for reservoirs and river basins.
- **Failure Behavior:** Exception triggers rollback, updates run status to `FAILED`.
- **Timestamp Handling:** Converts `DD-MM-YYYY HH:mm:ss` IST to UTC `TIMESTAMPTZ`.
- **Geographic Handling:** Pre-configured reservoir coordinate lookup (`KNOWN_RESERVOIRS`) provides WGS84 point coordinates.
- **Credential Requirement:** None.
- **Automation Readiness:** **LOW/MEDIUM (Dataset is historical 2006–2008; daily polling yields zero new records unless updated file is published)**.

### 7.4 `IfiFloodAdapter`
- **Source:** India Flood Inventory (HydroSenseLab / IIT Delhi).
- **Input:** GitHub raw CSV URL or string content.
- **Output Tables:** `flood_events`, `flood_observations`.
- **Data Category:** `HISTORICAL_EVENT`.
- **Idempotency Mechanism:** Unique event name matching on `FloodEvent`; compound `ifi_{uei}_{district_code}` on `FloodObservation`.
- **Duplicate Handling:** Idempotent skip.
- **Failure Behavior:** Per-row validation error tracking; batch-level transaction commit.
- **Timestamp Handling:** Parses `DD-MM-YYYY HH:mm` IST to UTC.
- **Geographic Handling:** Joins via LGD District Codes (`District_LGD_Codes`). Geometry column left strictly `NULL`.
- **Credential Requirement:** None.
- **Automation Readiness:** **NOT AN AUTOMATION CANDIDATE (Static historical archive)**.

### 7.5 `KarnatakaGeographyAdapter`
- **Source:** Local Government Directory (LGD) - Karnataka standard.
- **Input:** Hardcoded authoritative standard seed list (31 districts).
- **Output Tables:** `states`, `districts`.
- **Data Category:** `REFERENCE`.
- **Idempotency Mechanism:** Unique constraints on `State.code` and `District.code`.
- **Duplicate Handling:** Upserts / skips existing district records.
- **Failure Behavior:** Transactional rollback on integrity failure.
- **Timestamp Handling:** Static timestamps.
- **Geographic Handling:** Populates `centroid` (`POINT`), leaves boundary `geometry` `NULL`.
- **Credential Requirement:** None.
- **Automation Readiness:** **NOT AN AUTOMATION CANDIDATE (Static reference seeder)**.

---

## 8. DataSource and DataIngestionRun Audit

The schema and lifecycle capabilities of `DataSource` and `DataIngestionRun` were evaluated against Phase 2.5 requirements:

### A. Can current `DataSource` represent source health?
**Partially / Indirectly.**
The `DataSource` model represents static metadata (`name`, `organization`, `source_url`, `access_method`, `data_type`, `update_frequency`, `is_active`). It **does NOT** contain native columns for `health_status`, `last_successful_run_at`, `consecutive_errors`, or `latest_data_timestamp`.
Source health can currently only be computed dynamically via aggregation queries joining `DataIngestionRun` and observation tables.

### B. Can current `DataIngestionRun` represent operational states?
**Yes.**
The table enforces a check constraint:
```sql
status IN ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')
```
- `RUNNING`: Execution active (`completed_at IS NULL`). Equivalent to `STARTED`.
- `SUCCESS`: Ingestion succeeded with zero errors.
- `PARTIAL`: Ingestion completed but encountered non-fatal record rejections or warnings.
- `FAILED`: Execution crashed with an unhandled exception (`error_message` populated).

### C. Can we determine `last attempted`, `last successful`, and `latest data timestamp` as separate concepts?
- **Last Attempted Ingestion:** **YES** — `MAX(started_at)` from `data_ingestion_runs` for that source.
- **Last Successful Ingestion:** **YES** — `MAX(completed_at)` from `data_ingestion_runs WHERE status IN ('SUCCESS', 'PARTIAL')`.
- **Latest Actual Source Data Timestamp:** **NO (Cannot be determined from registry tables alone)** — Neither `DataSource` nor `DataIngestionRun` records the physical observation time of the payload. It requires querying `MAX(observed_at)` on the respective observation table.

### D. Missing Fields (Identified for future consideration):
1. On `DataSource`:
   - `health_status` (`HEALTHY`, `DEGRADED`, `DOWN`, `UNKNOWN`)
   - `last_health_check_at` (timestamp of last probe/run)
   - `consecutive_failures` (integer counter)
   - `latest_source_timestamp` (cached observation horizon)
2. On `DataIngestionRun`:
   - `trigger_type` (`SCHEDULED`, `MANUAL_CLI`, `EVENT`)
   - `execution_duration_ms` (runtime latency)
   - `latest_record_timestamp` (max timestamp in the ingested batch)

---

## 9. Freshness Audit

An evaluation of whether data freshness can be determined without inventing assumptions:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRESHNESS POLICY STATUS                         │
├─────────────────────┬──────────────────┬───────────────────────────────┤
│ Source              │ Status           │ Freshness Policy Assessment   │
├─────────────────────┼──────────────────┼───────────────────────────────┤
│ Open-Meteo Weather  │ PARTIALLY        │ Update frequency is HOURLY.   │
│                     │ DOCUMENTED       │ Polling interval is 1–3 hours.│
│                     │                  │ Stale threshold (>3h vs >6h)  │
│                     │                  │ THRESHOLD NOT YET JUSTIFIED   │
│                     │                  │                               │
│ NWIC CWC River      │ PARTIALLY        │ Update frequency is HOURLY.   │
│                     │ DOCUMENTED       │ Tranche upload is irregular.  │
│                     │                  │ SLA threshold is              │
│                     │                  │ THRESHOLD NOT YET JUSTIFIED   │
│                     │                  │                               │
│ NWIC Reservoirs     │ PARTIALLY        │ Frequency is documented as    │
│                     │ DOCUMENTED       │ DAILY, but live file stops in │
│                     │                  │ 2008. Real-time threshold is  │
│                     │                  │ THRESHOLD NOT YET JUSTIFIED   │
│                     │                  │                               │
│ India Flood Inv.    │ DOCUMENTED       │ Static catalog (1969–2023).   │
│ (IFI v3.0)          │                  │ Freshness policy:             │
│                     │                  │ NOT APPLICABLE (STATIC)       │
│                     │                  │                               │
│ Karnataka LGD       │ DOCUMENTED       │ Gazette standard reference.   │
│                     │                  │ Freshness policy:             │
│                     │                  │ NOT APPLICABLE (STATIC)       │
└─────────────────────┴──────────────────┴───────────────────────────────┘
```

**Rule:** In Phase 2.5, freshness thresholds must not be guessed. If an operational threshold (e.g. "stale if $>4$ hours") is not documented by the data provider, it must be labeled `THRESHOLD NOT YET JUSTIFIED` until defined by system engineering policy.

---

## 10. Automation Candidates

All audited sources are categorized into three engineering automation groups:

### Group A — Ready / Appropriate for Automation
*Sources with verified open access, reliable endpoints, predictable payloads, and deterministic idempotency.*
1. **Open-Meteo Weather & Forecast API (`OpenMeteoAdapter`):**
   - **Reason:** Public REST API, hourly updates, fast response (<1s), strict UTC timestamps, valid coordinates, 10,000 req/day allowance. Ideal candidate for scheduled recurring execution (e.g. every 1–3 hours).

### Group B — Needs Additional Work Before Full Automation
*Legitimate sources that require resolved network handling, updated endpoints, or operational adaptations.*
1. **NWIC CWC River Level Telemetry (`NwicRiverLevelAdapter`):**
   - **Reason:** Requires large multi-megabyte CSV downloads. Endpoints can experience server-side network lag or HTTP 504 timeouts. Needs download retry backoff, response stream timeouts, and incremental line parsing.
2. **NWIC Karnataka Reservoir Telemetry (`NwicReservoirAdapter`):**
   - **Reason:** The public CSV on NWIC contains historical records (stopping in 2008). Automating a daily background job that downloads the same static historical file creates redundant bandwidth without adding operational data. Needs upstream verification with NWIC/WRD on whether a true 2026 daily telemetry endpoint exists.
3. **Open-Meteo Historical Archive (`v1/archive`):**
   - **Reason:** Designed for retrospective batch calibration and feature store backfills, not recurring operational schedules.

### Group C — Do Not Automate
*Static archives, reference standards, or credential-gated services that must not be put on a recurring polling schedule.*
1. **India Flood Inventory (`IfiFloodAdapter`):** Static historical disaster catalog. Ingested once as a batch benchmark.
2. **Local Government Directory (`KarnatakaGeographyAdapter`):** Static administrative reference.
3. **IMD Official API Gateway:** Credential-blocked (HTTP 401).
4. **Copernicus CDS GloFAS API:** Credential-blocked (API token required).
5. **NRSC NDEM & IDRN Portals:** Restricted government logins.
6. **OpenStreetMap Overpass:** High compute cost on public community servers; should be batch refreshed monthly, not continuously polled.
7. **DDMP PDF Shelters:** Unstructured PDF annexures requiring manual data extraction.

---

## 11. Scientific and Data Gaps (`PRE-PHASE-2.5 GAPS`)

The audit identifies the following evidence-backed gaps:

1. **Weather Spatial Coverage Gap:**
   Operational weather ingestion queries only 5 monitoring locations (Bengaluru, Mangaluru, Kalaburagi, Belagavi, Mandya). 26 of Karnataka's 31 administrative districts have zero operational weather observations.
2. **Missing Boundary Geometry:**
   All 31 districts in `districts` have valid `centroid` points, but `geometry` (`MULTIPOLYGON`) is completely `NULL`. Spatial intersection queries, watershed clipping, and choropleth visualizations cannot function on the current table.
3. **Empty Sub-district Geography:**
   `taluks` (0 records) and `localities` (0 records) are completely unpopulated.
4. **Hydrological Gauging Sparsity:**
   The database contains exactly 1 river station (`AKKIHEBBAL`) and 1 reservoir (`Almatti Dam`). Statewide hydrological early warning cannot be modeled from single-station coverage.
5. **Temporal Discontinuity in River Stage:**
   The CWC river stage series contains a 149-day void between January 6, 2026 and June 4, 2026.
6. **Reservoir Data Staleness:**
   The ingested NWIC reservoir data terminates in February 2008. The system has zero 2024–2026 reservoir observations.
7. **Unpopulated River Forecasts:**
   `river_forecasts` contains 0 records. River flood forecasting currently has no populated inputs.
8. **Incomplete Historical Ground Truth:**
   Only the first 100 Karnataka events from IFI v3.0 (1969–1994) have been ingested. The 1995–2023 disaster events remain in the external CSV.
9. **Registry Health Decoupling:**
   `DataSource` lacks denormalized health state fields, requiring runtime aggregation across `DataIngestionRun`.

---

## 12. Documentation vs Database

A direct comparison between project documentation claims and actual live database state:

| Documented Expectation | Actual DB State | Match | Action Required |
|---|---|---|---|
| 34 Application Tables deployed via Alembic | 34 tables registered, Alembic head `ccfc6a6b5d06` | **MATCH** | None |
| 31 Karnataka Districts with official LGD codes | 31 districts with LGD codes 524–553, 744 | **MATCH** | None |
| District boundary polygons in EPSG:4326 | `districts.geometry` is `NULL` for all 31 districts | **MISMATCH** | Ingest district polygon boundaries from Datameet/KSRSAC |
| Weather Observations and Forecasts strictly separated | Stored in separate tables (`weather_obs` vs `weather_fcst`) | **MATCH** | None |
| Provenance classified via `data_category` | 100% of rows classified (`MODEL_OUTPUT`, `REANALYSIS`, `OBSERVATION`, `HISTORICAL_EVENT`), 0 NULLs | **MATCH** | None |
| CWC River Level observations in SI metres | `water_level` in metres, `water_level_unit='m'` | **MATCH** | None |
| Missing CWC discharge stored as `NULL` (`missing ≠ 0`) | `discharge` is `NULL` for all 101 river rows | **MATCH** | None |
| NWIC Reservoir storage in MCM, flow in m³/s | Converted to MCM and m³/s according to D-026 | **MATCH** | None |
| NWIC Reservoir historical coverage 1990–2026 | Ingested sample only covers 2006–2008 (100 rows) | **MISMATCH** | Clarify scope in docs; investigate 2026 reservoir telemetry |
| IFI Ground truth coverage 1969–2023 | Ingested sample only covers 1969–1994 (100 events) | **MISMATCH** | Batch load full 494 Karnataka events up to 2023 |
| Statewide weather coverage | Only 5 district monitoring points configured | **MISMATCH** | Expand default locations in `open_meteo.py` to 31 districts |
| 240 Taluks in Karnataka administrative layer | `taluks` table contains 0 rows | **MISMATCH** | Seed taluks from LGD in future reference task |
| Zero test fixture residue in production database | 0 test fixtures found across all tables | **MATCH** | None |

---

## 13. Phase 2.5 Readiness Decision

```
================================================================================
                           PHASE 2.5 READINESS:
                          READY WITH CONDITIONS
================================================================================
```

### Justification:
The engineering architecture (FastAPI backend, PostgreSQL/PostGIS schema, Alembic migration state, `BaseAdapter` pattern, and `DataIngestionRun` tracking) is fully established, rigorously tested (52/52 passing), and operates with verified data semantics and zero test residue.

### Mandatory Pre-Conditions for Phase 2.5 Execution:
1. **Automation Boundary Restriction:** Background scheduling in Phase 2.5 must be restricted exclusively to **Group A** candidates (`OpenMeteoAdapter` operational weather and forecasts). Static datasets (IFI, LGD) must not be scheduled.
2. **Spatial Expansion of Weather Polling:** The target location list for `OpenMeteoAdapter` should be expanded from 5 points to all **31 Karnataka district centroids** so that automated ingestion provides true statewide coverage.
3. **Health Decoupling Architecture:** The source-health monitoring service must compute health metrics dynamically from `DataIngestionRun` and observation table timestamps without modifying existing model semantics unless formally introduced via a tracked migration.
4. **No Synthetic Fallbacks:** If an external source is unreachable during scheduled execution, the scheduler must log a `FAILED` or `PARTIAL` run in `DataIngestionRun` and flag the source as degraded. Under no circumstances may fallback synthetic data be inserted.

---

## 14. Recommended Phase 2.5 Scope

1. **Background Job Orchestrator (APScheduler):**
   - Lightweight, in-process `AsyncIOScheduler` integrated into the FastAPI application lifespan.
   - Configurable cron/interval triggers (e.g. hourly weather polling).
   - Execution lock mechanism preventing overlapping runs of the same adapter.
2. **Automated Polling Pipeline:**
   - Automated hourly execution of `OpenMeteoAdapter` across all 31 Karnataka district centroids.
   - Idempotent upserting ensuring repeated runs never create duplicate observations.
3. **Source-Health Tracking Engine:**
   - Real-time health evaluation service calculating:
     - `last_attempted_at`
     - `last_successful_at`
     - `latest_data_timestamp`
     - `health_status` (`HEALTHY`, `DEGRADED`, `DOWN`)
     - Ingestion throughput and error rates
4. **Health API Endpoints:**
   - `GET /api/v1/health/sources` — Detailed health summary for every registered provider.
   - `GET /api/v1/health/sources/{source_id}/runs` — Recent ingestion run history.

---

## 15. Limitations

- **No Live In-Situ River Telemetry API:** CWC does not provide an authenticated public REST API; automation relies on periodically parsed open data files.
- **Reservoir Latency:** Current public reservoir datasets reflect historic tranches. Intra-day reservoir releases cannot be tracked until WRD live webhooks or active feeds become available.
- **Single-Node In-Process Scheduler:** APScheduler embedded in FastAPI is appropriate for single-instance development and staging. Multi-replica production deployment will eventually require Celery/Redis or Cloud Scheduler to prevent concurrent execution.
