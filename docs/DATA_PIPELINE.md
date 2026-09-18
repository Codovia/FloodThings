# DATA_PIPELINE.md

**Project:** FloodPulse  
**Status:** Implemented & Verified in Phase 2.4 (Real Data Ingestion Foundation).  
**Execution Interface:** CLI via `python -m app.ingestion.cli`.


---

## 1. Overview & Architectural Principles

The FloodPulse data pipeline moves real, attributable environmental, hydrological, and geospatial data from verified external providers into the PostgreSQL/PostGIS database, feature store, and downstream ML models.

```text
Official External Source (Verified API / CSV / GeoJSON / COG)
                           ↓
              1. Fetch & Provenance Logging
                 (Store raw payload, log HTTP status & timestamp)
                           ↓
              2. Parse & Format Extraction
                 (JSON / CSV / GeoJSON / COG window read)
                           ↓
              3. Schema Validation & Integrity Guard
                 (Enforce non-empty, valid structure, data contract checks)
                           ↓
              4. Explicit Unit Conversion
                 (e.g., feet → metres, TMC → MCM, cusecs → m³/s)
                           ↓
              5. Spatial & Administrative Normalization
                 (LGD code join, EPSG:4326 geometry validation, UTC timestamps)
                           ↓
              6. Idempotent Database Load
                 (PostgreSQL / PostGIS upsert: ON CONFLICT DO UPDATE)
                           ↓
              7. Health & Freshness Tracking
                 (Update DataSource registry: last_retrieved_at, status)
```

### Core Pipeline Invariants
1. **Never Fabricate Data**: Missing values are stored explicitly as `NULL`. Under no circumstances may a missing sensor reading or report be replaced by `0`, a historical average, or an interpolated guess (`missing ≠ 0`).
2. **Never Ingest Unattributed Records**: Every database row in observation, forecast, and facility tables must carry an attributable `source` string (e.g., `open_meteo`, `cwc_nwic`, `ifi_v3`, `openstreetmap`).
3. **Idempotence**: Running any pipeline multiple times across the same data window must produce identical database state without duplicate rows.
4. **Timezone Standardization**: All internal timestamps are stored as `TIMESTAMPTZ` in **UTC**. User-facing presentation converts to **IST** (UTC+05:30).

---

## 2. Ingestion Pipelines by Domain

### 2.1 Weather & Rainfall Telemetry Pipeline (`OpenMeteoAdapter`)

- **Source**: Open-Meteo Weather Forecast & Archive APIs
- **Frequency**: Operational polling every 1 to 3 hours for current weather and 7-day forecast; one-time batch load for historical reanalysis (1980–present).
- **Target Tables**:
  - `weather_observations` (`temperature_c`, `humidity_pct`, `wind_speed_mps`, `pressure_hpa`, `observed_at`, `lat`, `lon`, `geom`)
  - `rainfall_observations` (`rainfall_mm`, `observation_date`, `source="open_meteo"`, `quality="MODEL_OUTPUT"`)
  - `weather_forecasts` (`forecast_for`, `issued_at`, `rainfall_forecast_mm`, `temperature_c`, `wind_speed_mps`)
- **Unit Contract**:
  - Requires `wind_speed_unit=ms` in API query.
  - Precipitation in `mm`.
  - Temperature in `°C`.
  - Pressure in `hPa`.
- **Validation Rules**:
  - Latitude in $[11.5, 18.5]$, Longitude in $[74.0, 78.6]$.
  - Humidity in $[0, 100]$.
  - Wind speed $\ge 0.0$.
  - Precipitation $\ge 0.0$.

---

### 2.2 Reservoir Telemetry Pipeline (`NwicReservoirAdapter`)

- **Source**: NWIC Karnataka Reservoir Dataset (`karnataka_man_reservoir_data.csv`)
- **Frequency**: Daily batch fetch.
- **Target Tables**:
  - `reservoirs` (Metadata: name, basin, design capacity, full reservoir level)
  - `reservoir_observations` (`observed_at`, `water_level_m`, `storage_mcm`, `inflow_m3s`, `outflow_m3s`)
- **Unit Conversion Engine**:
  $$\text{Level}_{\text{m}} = \text{Level}_{\text{ft}} \times 0.3048$$
  $$\text{Storage}_{\text{MCM}} = \text{Storage}_{\text{TMC}} \times 28.3168$$
  $$\text{Inflow}_{\text{m}^3/\text{s}} = \text{Inflow}_{\text{cusecs}} \times 0.0283168$$
  $$\text{Outflow}_{\text{m}^3/\text{s}} = \text{Outflow}_{\text{cusecs}} \times 0.0283168$$
- **Validation Rules**:
  - Negative values in levels or capacities are mapped to `NULL`.
  - `monitoring_date` parsed from IST string `DD-MM-YYYY HH:mm:ss` to UTC `TIMESTAMPTZ`.

---

### 2.3 River Stage Telemetry Pipeline (`NwicRiverLevelAdapter`)

- **Source**: NWIC / CWC Hourly River Water Level CSVs (`rwl_manual_hr_cwc_*.csv`)
- **Frequency**: Daily tranche sync.
- **Target Tables**:
  - `river_basins` (Basin name: Cauvery, Krishna, Godavari)
  - `rivers` (River name, tributary name)
  - `river_stations` (Station name, LGD district code, coordinates `geom`)
  - `river_observations` (`observed_at`, `water_level_m`, `discharge_m3s`)
- **Validation Rules**:
  - `water_level_m` must be a valid float $> 0.0$ and $< 2000.0$ metres.
  - If `Is_DischargeDataAvailable` is "No" or discharge is blank, `discharge_m3s` must be set to `NULL` (`missing ≠ 0`).
  - Station coordinates validated within Karnataka hydrological bounds.

---

### 2.4 Historical Flood Ground Truth Pipeline (`IfiFloodEventLoader`)

- **Source**: India Flood Inventory (IFI v3.0, IIT Delhi)
- **Execution**: Batch execution during dataset creation.
- **Target Tables**:
  - `flood_observations` (`district_id`, `observation_date`, `flooded`, `source="ifi_v3"`, `severity`, `fatalities`)
  - `flood_events` (`start_date`, `end_date`, `duration_days`, `affected_districts`, `damage_description`)
- **Target Formulation**:
  - Spatial resolution: **District level** (using LGD District Codes).
  - Formulation: Binary classification target per District × Day:
    $$y_{d, t} = \begin{cases} 1 & \text{if documented flood event in district } d \text{ on date } t \\ 0 & \text{otherwise} \end{cases}$$
  - Negative Sampling ($y=0$): Days without recorded flood damage/events in district $d$ during the active evaluation period.

---

### 2.5 Terrain & Elevation Pipeline (`CopernicusDemExtractor`)

- **Source**: Copernicus DEM GLO-30 via AWS Open Data (`s3://copernicus-dem-30m`)
- **Execution**: Static one-time computation.
- **Processing**:
  - Stream Cloud Optimized GeoTIFF (COG) bounding boxes corresponding to Karnataka district and taluk polygons.
  - Compute zonal statistics using `rasterstats` / PostGIS:
    - Mean elevation (`elevation_mean_m`)
    - Minimum elevation (`elevation_min_m`)
    - Maximum elevation (`elevation_max_m`)
    - Mean slope in degrees (`slope_mean_deg`)
- **Target Table**: `terrain_datasets` and static administrative features.

---

### 2.6 Emergency Facilities Pipeline (`OsmEmergencyFacilityLoader`)

- **Source**: OpenStreetMap via Overpass API
- **Target Table**: `emergency_facilities`
- **Filtering Contract**:
  - `node["amenity"="hospital"]` → `facility_type="hospital"`
  - `node["amenity"="fire_station"]` → `facility_type="fire_station"`
  - `node["amenity"="police"]` → `facility_type="police_station"`
- **Strict Prohibition**: Generic OSM `amenity=shelter` or `building=school` nodes are **strictly forbidden** from being imported as official flood evacuation shelters.
- **Shelters**: Designated flood evacuation shelters are imported solely from curated District Disaster Management Plan (DDMP) official tables, with occupancy set to `NULL`.

---

### 2.7 KSR-SAC Administrative GIS Normalization Pipeline (`KsrsacAdminNormalizer`)

- **Source**: KSR-SAC / KGIS official gazetted shapefiles (`data/raw/gis/ksrsac/District.shp`, `data/raw/gis/ksrsac/Taluk.shp`).
- **Raw-Source Preservation Policy**: Raw source files on disk are strictly read-only and must never be modified, repaired in-place, or overwritten.
- **Source CRS**: `EPSG:32643` (UTM Zone 43N, metres).
- **Target Storage CRS**: `EPSG:4326` (WGS 84 decimal degrees).
- **Validation Contract**:
  - Exactly 31 districts, 240 taluks.
  - Unique KGIS codes (`KGISDistri`, `KGISTalukC`) and LGD codes (`LGD_Distri`, `LGD_TalukC`).
  - Strict preservation of source codes (KGIS 31, LGD 738 for Vijayanagara).
  - No empty or null geometries.
- **Deterministic In-Memory Geometry Repair**:
  - Detects ring self-intersections in source survey digitization.
  - Exactly 3 taluk geometries repaired in memory via `shapely.make_valid()`: Shivamogga (KGIS 1506 / LGD 5520), Sringeri (KGIS 1701 / LGD 5525), Hosanagar (KGIS 1504 / LGD 5518).
  - Area difference after repair is sub-millimetric floating-point noise ($< 10^{-14}$ relative difference).
  - `buffer(0)` is strictly prohibited.
- **Topological Integrity**:
  - Parent-child spatial containment: All 240 taluks intersect parent district; all 240 representative points lie strictly within parent district geometry.
  - Vijayanagara 6-taluk condition: District KGIS 31 has exactly 6 constituent taluks.
  - Non-overlap: No substantive overlaps exceeding relative tolerance $\text{REL\_TOL} = 10^{-10}$.
- **Target Dataclasses**: Produces `NormalizedDistrict` and `NormalizedTaluk` with `wkt` (`SRID=4326;MULTIPOLYGON...`) and `centroid_wkt` ready for PostGIS ingestion.

---

### 2.8 Data Semantics & Provenance Classification (`data_category`)

Per Phase 2.4.1 and `docs/DATA_SEMANTICS_AUDIT.md`, all observation tables enforce a strict `data_category VARCHAR(30)` column:

| Table | Category | Provenance Meaning |
|---|---|---|
| `weather_observations` (operational past) | `MODEL_OUTPUT` | Numerical weather prediction nowcast/hindcast (ICON/GFS 0.1° grid) |
| `weather_observations` (historical archive) | `REANALYSIS` | ECMWF ERA5 atmospheric reanalysis reconstruction |
| `rainfall_observations` (operational past) | `MODEL_OUTPUT` | NWP gridded precipitation nowcast/hindcast |
| `rainfall_observations` (historical archive) | `REANALYSIS` | ECMWF ERA5-Land gridded precipitation reanalysis |
| `river_observations` | `OBSERVATION` | In-situ physical staff gauge reading by CWC/NWIC observers |
| `reservoir_observations` | `OBSERVATION` | In-situ physical daily dam monitoring reading by WRD Karnataka |
| `flood_observations` | `HISTORICAL_EVENT` | Curated disaster occurrence ground truth from India Flood Inventory |

Under no circumstances should `MODEL_OUTPUT` or `REANALYSIS` be confused with physical station observations in downstream feature engineering or model evaluation.

---

## 3. Data Flow & Feature Store Bridge

```text
Raw Observation Tables
(weather_observations, rainfall_observations, river_observations, reservoir_observations)
                           ↓
             Rolling Window Feature Aggregator
       (1h, 3h, 6h, 12h, 24h, 72h, 7d, 14d rainfall sums,
        river stage rate-of-rise, reservoir percent full)
                           ↓
                      FeatureStore
                  (feature_snapshots)
                           ↓
               Time-Based Holdout Split
            (Train: 1980–2018 | Test: 2019–2023)
                           ↓
                 Supervised ML Training
           (RandomForest, XGBoost, LightGBM)
```

---

## 4. Phase Boundaries

- **Phase 2.1**: Project Foundation (Completed).
- **Phase 2.2**: Database Models & Internal Data Contract (Completed).
- **Phase 2.3**: Real Source / API Validation Lab (Completed).
- **Phase 2.4**: Implementation of lightweight source adapters and batch ingestion scripts (Completed).
- **Phase 2.4.1**: Data Semantics & Provenance Correction Audit (Completed).
- **Phase 2.5**: Automated background ingestion (APScheduler) and source-health monitoring (Completed).
- **Phase 3**: GIS & Administrative Boundary Ingestion / Spatial Feature Engineering.

---

## 5. Automated Background Ingestion & Source Health (Phase 2.5)

### 5.1 In-Process Background Scheduler
- **Technology**: `apscheduler.schedulers.asyncio.AsyncIOScheduler` (APScheduler 3.10.4).
- **Lifecycle Integration**: Managed via FastAPI `@asynccontextmanager` application lifespan (`app.main:lifespan`).
- **Configuration Flags**:
  - `scheduler_enabled: bool = True` (Can be set to `False` in testing/CLI via `SCHEDULER_ENABLED=false`).
  - `openmeteo_ingestion_interval_minutes: int = 60` (Default 60-minute polling cycle).

### 5.2 Automation Scope (Group A Only)
- **Included in Background Automation**:
  - `OpenMeteoAdapter`: Operational weather observations nowcast (`data_category='MODEL_OUTPUT'`) and 72-hour forward forecasts (`weather_forecasts`).
  - Query points: Fixed 5 district representative/model query points (Bengaluru, Belagavi, Mangaluru, Kalaburagi, Mandya).
- **Excluded from Background Automation**:
  - Static archives (`IfiFloodAdapter`, `KarnatakaGeographyAdapter`).
  - Monolithic batch datasets (`NwicRiverLevelAdapter`, `NwicReservoirAdapter`).
  - Community/rate-limited APIs (`OsmEmergencyFacilityLoader`).
  - Credential-gated sources (`IMD API Gateway`, `Copernicus GloFAS`).

### 5.3 Concurrency & Async/Sync Safety
- **Dual-Layer Concurrency Guard**:
  1. APScheduler: `max_instances=1`, `coalesce=True` on job registration.
  2. Application Layer: In-process `asyncio.Lock` in `IngestionJobRunner`. Overlapping trigger attempts are safely skipped and logged without fabricating fake success runs.
- **Thread Offloading**: Synchronous database and HTTP calls in `OpenMeteoAdapter` are executed in a worker thread via `asyncio.to_thread` to ensure zero blocking of the FastAPI asyncio event loop.
- **Session Isolation**: Each execution generates an isolated SQLAlchemy session from `_get_session_factory()`, guaranteed closed in `finally`.

### 5.4 Dynamic Source Health & Internal Operational Policy
- **No Schema Columns Added**: Health is dynamically computed by `SourceHealthService` without adding persistent `health_status` columns to `DataSource`.
- **Governing States**: `HEALTHY`, `DEGRADED`, `DOWN`.
- **Deterministic Evaluation Criteria**:
  - `is_active = False` → `DOWN`
  - Zero ingestion history → `DOWN`
  - Consecutive failures $\ge 3$ → `DOWN`
  - Latest run `FAILED` (< 3 failures) → `DEGRADED`
  - Latest run `PARTIAL` → `DEGRADED`
  - Latest run `SUCCESS`: evaluated against freshness policy.
- **Freshness SLA Policy Clarification**:
  Upstream providers (Open-Meteo, CWC, NWIC) do **not** define FloodPulse's freshness SLA. All freshness thresholds (e.g. 4-hour staleness window for operational weather) are strictly **FloodPulse internal operational policies** configured in `Settings` (`openmeteo_freshness_threshold_hours`), never external provider requirements.

### 5.5 Source Health API Endpoints
- `GET /api/v1/health/sources`: Evaluates runtime health across all registered data providers.
- `GET /api/v1/health/sources/{source_id}/runs`: Paginated ingestion run history ordered by `started_at DESC`.
