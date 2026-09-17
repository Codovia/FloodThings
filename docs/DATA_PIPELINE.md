# DATA_PIPELINE.md

**Project:** FloodPulse  
**Status:** Architecture Specification following Phase 2.3 Validation Lab.  
**Implementation Phase:** Phase 2.4 (Source Adapters & Ingestion Pipelines).

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
- **Phase 2.4**: Implementation of lightweight source adapters and batch ingestion scripts.
- **Phase 2.5**: Automated background ingestion (APScheduler) and source-health monitoring dashboard.
