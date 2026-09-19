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

### 2.4 Historical Flood Event Normalization Pipeline (`IfiEventNormalizer`)

- **Source**: India Flood Inventory (IFI v3.0, HydroSenseLab / India Meteorological Department), local raw archive `data/raw/ifi/ifi_v3_karnataka_20260917_164914.csv`.
- **Raw-Source Preservation Policy**: Raw IFI CSV archive on disk is strictly read-only and must never be modified or overwritten.
- **Normalization Layer**: In-memory deterministic normalizer (`app.gis.ifi.IfiEventNormalizer`) aligned directly with the authoritative KSR-SAC administrative GIS foundation (`KsrsacAdminNormalizer`).
- **Target Schema Entities**:
  - `flood_events` (Disaster event catalog: `name`, `start_time` [UTC derived], `end_time` [UTC derived], `start_date_raw`, `end_date_raw`, `duration_days`, `main_cause`, `severity`, `affected_area`, `description`, `geometry=NULL`, `source_id`, `confidence=NULL`).
  - `flood_observations` (District-level historical evidence: `observation_time`, `district_id`, `source_record_id=f"ifi_{uei}_{lgd_code}"`, `flooded=True`, `flood_depth=NULL`, `geometry=NULL`, `confidence=NULL`, `mapping_status="DETERMINISTIC"`, `quality_status="VALID"`, `data_category="HISTORICAL_EVENT"`).
- **Zero-Fabrication & Semantics Constraints**:
  - **No Manufactured Polygons or Points**: Raw IFI records have no coordinate geometry. Geometries must remain strictly `NULL` (`None`).
  - **Centroid Inference Strictly Prohibited**: Flood geometry must never be inferred or synthesized from district centroids or bounding boxes.
  - **Depth Nullability**: Missing flood depth remains strictly `NULL` (never 0.0 or estimated).
  - **Confidence Semantics**: The IFI source does not publish a confidence or probability score. Source `confidence` must remain `NULL` (`None`) per CONSTRAINTS.md; assigning `1.0` as source confidence is unjustified. Administrative resolution certainty is tracked as `mapping_status="DETERMINISTIC"`.
  - **Timezone Assumption**: Raw IFI records report timestamps without timezone offsets (predominantly `00:00` nominal midnight, representing calendar day events). Conversion to UTC assuming Indian Standard Time (IST = UTC+05:30) is an **operational assumption** based on reporting agencies (IMD/CWC), not an explicit source metadata declaration. Both `start_date_raw` and derived UTC datetimes are preserved.
  - **Historical Disaster Evidence**: IFI events represent documented disaster damage reports, NOT satellite inundation ground truth.
- **Deterministic Administrative Mapping Protocol**:
  - **KSR-SAC Alignment**: Deterministically resolves raw district tokens to verified KSR-SAC `NormalizedDistrict` entities (preserving KGIS codes 01–31, official LGD codes 524–738, and canonical names).
  - **Spelling & Geocoding Repairs**:
    - Raw tokens with `District_LGD_Codes == 'None'`: 173 total. Of these, exactly 142 are recovered via verified spelling/headquarters aliases (`Uttar Kashia Kannada` 71 $\to$ Uttara Kannada, `Beedar` 36 $\to$ Bidar, `Bagalkotee` 20 $\to$ Bagalkote, `Chamarajanagaraa` 9 $\to$ Chamarajanagara, `Mangalore` 6 $\to$ Dakshina Kannada). The remaining 31 are unresolved tokens.
    - Upstream LGD misattribution: Exactly 32 occurrences of `Bijapur` (assigned LGD 636 [Chhattisgarh] in upstream IFI) are recovered and mapped to Vijayapura (KGIS 03, LGD 530).
    - Other verified canonical aliases: `ramanagara` $\to$ Bengaluru South (KGIS 29, LGD 631), `bellary` $\to$ Ballari, `mysore` $\to$ Mysuru, `coorg` $\to$ Kodagu, `shimoga` $\to$ Shivamogga, `gulbarga` $\to$ Kalaburagi.
  - **Out-of-State Non-Karnataka Filtering**: 35 non-Karnataka district tokens in multi-state events (Kerala, Gujarat, AP/Telangana, Uttarakhand) are deterministically identified and excluded without error.
  - **Unresolved Token Auditing**: Exactly 31 token occurrences across 18 distinct strings cannot be deterministically mapped without guessing (13 OCR concatenations like `Chamarajanagaraa Chikkaballapura` [6], `Bagalkotee Belagavi` [5], `Bagalkotee Bengaluru Urban` [3], `Chamarajanagaraa Hassan` [2], etc.; 2 taluk-level tokens `Mudigere` [1] and `Chikodi` [1]; 1 locality token `Rugi` [1]; 2 non-district descriptors `Parts of Karnataka` [2]; 1 ambiguous token `Uttar Kashia` [1]; 1 unmapped corrupted string `Davangere` [1]; and 1 composite `Bijapur Surendranagar` [1]). The normalizer **never guesses**; these are recorded in `UnresolvedDistrictTokenRecord` and reported in the audit log.

- **Idempotency**: Events deduplicated by `UEI`; district observations deduplicated by `(UEI, kgis_district_code)`.

---

### 2.4.1 Historical Flood Evidence Audit & Spatial-Temporal Coverage Contract (`IfiEvidenceAuditor`)

- **Audit Module**: In-memory, deterministic audit engine (`app.gis.ifi_audit.IfiEvidenceAuditor`).
- **Audit Target**: Evaluates normalized IFI v3.0 historical flood records against all 31 authoritative KSR-SAC districts.
- **Audit Findings (Real Source Archive)**:
  - **Source Records**: 6,876 raw rows; 494 Karnataka-filtered events (`State_Codes` contains `29`); 493 valid events; 1 rejected event (`UEI-IMD-FL-2001-0043` with empty start timestamp).
  - **Raw Token Evaluation & Resolution Reconciliation**:
    - Exactly 1,344 raw district tokens evaluated across the 493 valid events:
      - `DIRECT_LGD`: 1,104 raw resolutions $\to$ 5 duplicate observations skipped $\to$ **1,099** normalized observations.
      - `VERIFIED_ALIAS`: 142 raw resolutions $\to$ 2 duplicate observations skipped (`Mangalore` when `Dakshina Kannada` already present in same event) $\to$ **140** normalized observations.
      - `BIJAPUR_CORRECTION`: 32 raw resolutions $\to$ 0 duplicate observations skipped $\to$ **32** normalized observations.
      - `OUT_OF_STATE`: 35 non-Karnataka tokens skipped.
      - `UNMAPPED`: 31 unresolved token occurrences across 18 distinct strings.
    - Total normalized district observations: $1,099 + 140 + 32 = \mathbf{1,271}$.
  - **Normalized Historical Evidence**: 1,271 district observations; 0 duplicate events; 7 duplicate observations skipped within same events.
  - **Unresolved Evidence**: Exactly 31 occurrences across 18 distinct strings cannot be deterministically mapped without guessing (13 OCR concatenations, 2 taluk-level tokens, 1 locality token, 2 non-district descriptors, 1 ambiguous token, 2 unmapped/corrupted tokens).
  - **Spatial & Administrative Coverage**:
    - Exactly 30 districts have documented historical flood evidence in IFI v3.0.
    - Exactly 1 district has zero evidence: **Vijayanagara** (KGIS 31, LGD 738) has zero matching IFI v3 observations in the audited archive.
    - Districts with zero evidence remain explicitly zero. Coverage is never manufactured.
    - Absence of evidence does not constitute proof of zero flooding.
  - **Temporal Coverage**:
    - Earliest recorded event: `1969-07-14`.
    - Latest recorded event: `2023-07-24`.
    - 5 calendar years with zero documented events: `[1970, 1971, 1973, 1976, 1977]`.
    - Coverage gaps are not interpolated or synthetically filled.
- **Source Semantics & Limitations**:
  - `source_name = "India Flood Inventory (IFI v3.0)"`
  - `data_category = "HISTORICAL_EVENT"`
  - Spatial resolution is coarse district-level damage reports.
  - Coordinate geometry is strictly `NULL` (`None`).
  - Flood depth is strictly `NULL` (`None`).
  - Source confidence is strictly `NULL` (`None`) per CONSTRAINTS.md (IFI v3 publishes no confidence score; mapping status `DETERMINISTIC` is separate from source confidence).
  - IFI is **not** satellite inundation ground truth; it represents recorded administrative damage.
  - Absence of evidence does **not** constitute proof of no flooding.
  - This audit does **not** define an ML target or label dataset.

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

- **Source**: KSR-SAC / KGIS official shapefiles (`data/raw/gis/ksrsac/State.shp`, `data/raw/gis/ksrsac/District.shp`, `data/raw/gis/ksrsac/Taluk.shp`).
- **Raw-Source Preservation Policy**: Raw source files on disk are strictly read-only and must never be modified, repaired in-place, or overwritten.
- **Source CRS**: `EPSG:32643` (UTM Zone 43N, metres).
- **Target Storage CRS**: `EPSG:4326` (WGS 84 decimal degrees).
- **Validation Contract**:
  - Exactly 1 state (`KGISStateC=29`, `KGISStateN=Karnataka`), 31 districts, 240 taluks.
  - Unique KGIS codes (`KGISStateI`, `KGISDistri`, `KGISTalukC`) and LGD codes (`KGISStateC`, `LGD_Distri`, `LGD_TalukC`).
  - Strict preservation of source codes (KGISStateC 29 for Karnataka; KGIS 31, LGD 738 for Vijayanagara).
  - No empty or null geometries.
  - State is a single valid MultiPolygon feature.
- **Deterministic In-Memory Geometry Repair**:
  - Detects ring self-intersections in source survey digitization.
  - Exactly 3 taluk geometries repaired in memory via `shapely.make_valid()`: Shivamogga (KGIS 1506 / LGD 5520), Sringeri (KGIS 1701 / LGD 5525), Hosanagar (KGIS 1504 / LGD 5518).
  - State geometry is 100% topologically valid in source data and requires zero repair.
  - Area difference after repair is sub-millimetric floating-point noise ($< 10^{-14}$ relative difference).
  - `buffer(0)` is strictly prohibited.
- **Topological Integrity**:
  - State hierarchy containment: All 31 districts and all 240 taluks intersect the normalized state boundary; representative points for all 31 districts and 240 taluks lie strictly within the state polygon.
  - Parent-child spatial containment: All 240 taluks intersect parent district; all 240 representative points lie strictly within parent district geometry.
  - Vijayanagara 6-taluk condition: District KGIS 31 has exactly 6 constituent taluks.
  - Non-overlap: No substantive overlaps exceeding relative tolerance $\text{REL\_TOL} = 10^{-10}$.
- **Target Dataclasses**: Produces `NormalizedState`, `NormalizedDistrict`, and `NormalizedTaluk` with `wkt` (`SRID=4326;MULTIPOLYGON...`) and `centroid_wkt` ready for PostGIS ingestion.

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

### 2.9 Administrative GIS ↔ Environmental Spatial Association Audit (`SpatialAssociationAuditor`)

- **Purpose**: Deterministic, read-only spatial verification between populated KSR-SAC administrative GIS polygons (`states`, `districts`, `taluks`) in PostGIS (EPSG:4326) and existing environmental / historical records.
- **Audited Entities**:
  1. `weather_observations`: 397 examined, 397 matched within assigned districts (8.95 km to 32.32 km interior; 0 outside Karnataka, 0 wrong district).
  2. `rainfall_observations`: 397 examined, 397 matched within assigned districts (8.95 km to 32.32 km interior; 0 outside Karnataka, 0 wrong district).
  3. `river_stations`: 1 examined (`AKKIHEBBAL`), 0 matched, 1 flagged for manual review. Stored district is Koppal (Northern Karnataka), actual spatial location is Mandya (Southern Karnataka; 284 km distant; 2.94 km from Mandya boundary). Stored FK is preserved without silent mutation.
  4. `taluk_containment`: 240 examined, 240 have PointOnSurface inside assigned district (100.0%), 44 strictly within (`ST_Within`), 196 micro-boundary slivers (overlap >= 99.999% due to KSR-SAC digitization precision), 0 cross-district mismatches.
  5. `flood_observations` (IFI): 186 examined, 186 reference valid KSR-SAC districts (23 distinct districts), 186 have `geometry IS NULL` (100.0% zero-fabrication preserved).
- **Execution**:
  ```bash
  python -m app.ingestion.cli spatial-audit [--format text|json] [--export-path PATH]
  ```
- **Invariants**: Strictly read-only; zero synthetic coordinates; zero centroid inference; preserves source provenance.

### 2.10 District Code Integrity Audit & Controlled Station Correction (Phase 3.4B)
- **District Code Integrity Audit**:
  - Compares database `districts.code` against authoritative KSR-SAC / Government of India Local Government Directory (LGD) catalog.
  - Identified 25 code mismatches resulting from sequential numbering in the Phase 2.4 geography seeder.
  - Updated all 31 `districts.code` values to official LGD codes (`524`–`738`), exactly matching KSR-SAC `District.shp` (`LGD_Distri`).
  - 100% of district UUIDs preserved; 0 foreign keys broken.
- **Controlled AKKIHEBBAL River Station Correction**:
  - Station `AKKIHEBBAL` (`station_code = 'AKKIHEBBAL'`) updated from Koppal UUID (`d1aeeddc-141b-4ab0-8899-ab9844e29b8d`) to Mandya UUID (`c9065c38-f2c3-4b56-8209-1009e4faa6f7`).
  - 101 river observations remain intact and untouched with valid `station_id` FK.
- **Ingestion Adapter Hardening (`nwic_river.py`)**:
  - Cross-validates source district code against authoritative Karnataka LGD catalog.
  - Cross-checks source district name (including canonical aliases).
  - Conflicting code/name combinations are rejected and logged rather than silently misassigned.
- **Post-Correction Spatial Alignment**:
  - Re-audit confirms 1,221 / 1,221 records (100.0%) spatially matched with 0 discrepancies:
    - River stations: 1/1 matched (0 outside, 0 manual review)
    - Weather observations: 397/397 matched
    - Rainfall observations: 397/397 matched
    - Taluks: 240/240 matched
    - IFI flood observations: 186/186 valid
- **Execution**:
  ```bash
  python -m app.ingestion.cli district-code-audit [--format text|json] [--export-path PATH]
  python -m app.ingestion.cli district-code-correct [--dry-run]
  ```

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
