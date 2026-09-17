# FloodPulse Data Acquisition Specification

## Purpose

This document specifies the authoritative contracts, retrieval protocols, transformation rules, validation constraints, and architectural boundaries for all data ingestion adapters in **Phase 2 — Data Ingestion & Validation**.

Every adapter built in Phase 2 must comply strictly with the specifications defined herein.

---

## 1. Production Source Acquisition Specifications

### 1.1 Open-Meteo Weather & Forecast Adapter (`OpenMeteoAdapter`)

#### Source Identity
- **Source Name**: Open-Meteo Weather Forecast & Archive API
- **Authority / Provider**: Open-Meteo GmbH
- **Official URL**: `https://open-meteo.com`
- **Dataset / API Identifier**: `v1/forecast` and `v1/archive`
- **Operational Role**: `PRIMARY_OPERATIONAL`

#### Retrieval Protocol
- **Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **HTTP Method**: `GET`
- **Authentication**: None required.
- **Query Parameters**:
  - `latitude`: Decimal degrees (WGS84, float, e.g. `12.2958`)
  - `longitude`: Decimal degrees (WGS84, float, e.g. `76.6394`)
  - `current`: `temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m`
  - `hourly`: `temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m,surface_pressure`
  - `wind_speed_unit`: `ms` (mandatory to match `_mps` contract directly)
  - `forecast_days`: Integer `1` to `7` (default `3` for operational pipeline)
  - `timezone`: `UTC` (mandatory; never request local timezone at ingestion)
- **Expected Response**: JSON (`application/json`)
- **Rate Limit Compliance**: Maximum 600 calls/minute, 10,000 calls/day. Client caching required.

#### Variables & Transformation Mapping

| Source Field | Internal Target Field | Target Table | Datatype | Unit | Nullable | Transformation | Validation Rule |
|---|---|---|---|---|---|---|---|
| `current.time` | `observed_at` | `weather_observations` | `TIMESTAMPTZ` | UTC | NO | Parse ISO 8601 string to UTC datetime | Must not be in the future (> now + 5 min) |
| `current.temperature_2m` | `temperature_c` | `weather_observations` | `NUMERIC(5,2)` | °C | YES | None | Range: `-10.0` to `55.0` °C |
| `current.relative_humidity_2m` | `humidity_pct` | `weather_observations` | `NUMERIC(5,2)` | % | YES | None | Range: `0.0` to `100.0` % |
| `current.wind_speed_10m` | `wind_speed_mps` | `weather_observations` | `NUMERIC(5,2)` | m/s | YES | None (retrieved with `wind_speed_unit=ms`) | Range: `0.0` to `100.0` m/s |
| `hourly.surface_pressure` | `pressure_hpa` | `weather_observations` | `NUMERIC(6,1)` | hPa | YES | Match timestamp index | Range: `800.0` to `1080.0` hPa |
| `current.precipitation` | `rainfall_mm` | `rainfall_observations` | `NUMERIC(7,2)` | mm | YES | None | Value $\ge 0.0$ |
| `hourly.precipitation` | `rainfall_mm` | `weather_forecasts` | `NUMERIC(7,2)` | mm | YES | None | Value $\ge 0.0$ |
| `hourly.time` | `forecast_for` | `weather_forecasts` | `TIMESTAMPTZ` | UTC | NO | Parse ISO 8601 string to UTC datetime | `forecast_for >= issued_at` |

#### Temporal Handling
- All internal storage must use **UTC** (`TIMESTAMPTZ`).
- `observed_at`: Set from `current.time` (or `hourly.time[i]`) converted to UTC.
- `retrieved_at`: Recorded at the instant of HTTP response reception (`datetime.now(timezone.utc)`).
- `issued_at`: Set to `retrieved_at` for operational forecasts.
- User-facing conversion to **IST** (`Asia/Kolkata`, UTC+05:30) occurs strictly in presentation and API serialization layers.

#### Spatial Handling
- Source coordinates: Point in WGS84 (`EPSG:4326`).
- Coordinate validation:
  - Latitude: $11.5 \le \text{lat} \le 18.5$
  - Longitude: $74.0 \le \text{lon} \le 78.6$
- Grid location assignment: Assigned to `district_id` via spatial containment (`ST_Contains(districts.geometry, ST_SetSRID(ST_Point(lon, lat), 4326))`).

#### Provenance & Freshness
- `source`: `"open_meteo"`
- `source_record_id`: Formatted as `"openmeteo_{lat:.4f}_{lon:.4f}_{timestamp}"`
- `processing_version`: `"v1.0"`
- Freshness expectations:
  - `FRESH`: `observed_at` within past 3 hours.
  - `STALE`: `observed_at` older than 3 hours but within past 24 hours.
  - `UNAVAILABLE`: No successful response within past 24 hours.

---

### 1.2 NWIC Karnataka Reservoir Adapter (`NwicReservoirAdapter`)

#### Source Identity
- **Source Name**: National Water Data Portal — Karnataka Manual Reservoir Telemetry
- **Authority / Provider**: National Water Informatics Centre (NWIC) / Ministry of Jal Shakti
- **Official URL**: `https://nwdp.nwic.gov.in`
- **Dataset / File Resource**: `karnataka_man_reservoir_data.csv` (`resource/26800982-045c-41de-821d-b1ca080a79a8`)
- **Operational Role**: `PRIMARY_HISTORICAL` (Daily Batch)

#### Retrieval Protocol
- **Access Method**: HTTP Direct CSV Download / Range Stream
- **URL**: `https://nwdp.nwic.gov.in/dataset/e35dc28a-6f9c-486d-b598-87a21397018e/resource/26800982-045c-41de-821d-b1ca080a79a8/download/karnataka_man_reservoir_data.csv`
- **HTTP Method**: `GET`
- **Authentication**: None required for public dataset download.
- **Encoding**: UTF-8 CSV with commas as delimiters.

#### Variables & Unit Conversion Contracts

| Source CSV Column | Target Field | Target Table | Source Unit | Target Unit | Conversion Contract | Validation Rule |
|---|---|---|---|---|---|---|
| `Reservoir Name` | `reservoirs.name` | `reservoirs` | String | String | Trim and normalize whitespace | Must match registered reservoir name |
| `Monitoring Date` | `observed_at` | `reservoir_observations` | `DD-MM-YYYY HH:MM:SS` (IST) | `TIMESTAMPTZ` (UTC) | Parse IST datetime, convert to UTC (`-05:30`) | Must not be future date |
| `Reservoir Level (ft)` | `level_m` | `reservoir_observations` | feet (`ft`) | metres (`_m`) | $\text{level\_m} = \text{val} \times 0.3048$ | Value $> 0.0$; within reservoir physical limits |
| `Live Capacity (TMC)` | `storage_mcm` | `reservoir_observations` | `TMC` | `_mcm` | $\text{storage\_mcm} = \text{val} \times 28.3168$ | Value $\ge 0.0$ and $\le \text{gross\_capacity\_mcm} \times 1.2$ |
| `Inflow (Cusecs)` | `inflow_m3s` | `reservoir_observations` | `cusecs` | `_m3s` | $\text{inflow\_m3s} = \text{val} \times 0.0283168$ | Value $\ge 0.0$ |
| `Outflow to River (Cusecs)` | `outflow_m3s` | `reservoir_observations` | `cusecs` | `_m3s` | $\text{outflow\_m3s} = \text{val} \times 0.0283168$ | Value $\ge 0.0$ |

#### Monitored Karnataka Reservoirs
The adapter must match records against verified Karnataka reservoir facilities:
1. `Almatti Dam` (Krishna Basin)
2. `Krishna Raja Sagar (KRS)` (Cauvery Basin)
3. `Kabini Reservoir` (Cauvery Basin)
4. `Tungabhadra Dam` (Krishna / Tungabhadra Basin)
5. `Bhadra Reservoir` (Krishna / Bhadra Basin)
6. `Ghataprabha (Hidkal) Dam` (Krishna Basin)
7. `Malaprabha (Renukasagar) Dam` (Krishna Basin)
8. `Harangi Reservoir` (Cauvery Basin)
9. `Hemavathi (Gorur) Reservoir` (Cauvery Basin)
10. `Linganamakki Dam` (Sharavathi Basin)
11. `Supa Dam` (Kali Basin)
12. `Narayanpur Dam` (Krishna Basin)

#### Provenance & Freshness
- `source`: `"nwic_karnataka_reservoir"`
- `source_record_id`: Formatted as `"nwic_res_{reservoir_code}_{date_YYYYMMDD}"`
- `processing_version`: `"v1.0"`
- Freshness:
  - `FRESH`: `observed_at` within past 36 hours.
  - `STALE`: `observed_at` older than 36 hours but within past 7 days.
  - `UNAVAILABLE`: Older than 7 days or missing.

---

### 1.3 CWC / NWIC River Gauge Telemetry Adapter (`NwicRiverLevelAdapter`)

#### Source Identity
- **Source Name**: National Water Data Portal — River Water Level Manual Hourly (CWC)
- **Authority / Provider**: Central Water Commission (CWC) / National Water Informatics Centre
- **Official URL**: `https://nwdp.nwic.gov.in`
- **Dataset Identifier**: `dataset/d951a09c-6cf8-470e-be77-e80116f13d34`
- **Operational Role**: `PRIMARY_OPERATIONAL`

#### Retrieval Protocol
- **Access Method**: HTTP Direct CSV Download
- **URL (Cauvery Tranche)**: `https://nwdp.nwic.gov.in/dataset/d951a09c-6cf8-470e-be77-e80116f13d34/resource/37cba82e-f745-4004-80d2-b05cad65b8e4/download/rwl_manual_hr_cwc_009_2026_2030.csv`
- **URL (Krishna Tranche)**: `https://nwdp.nwic.gov.in/dataset/d951a09c-6cf8-470e-be77-e80116f13d34/resource/83b11653-6e75-4f58-8529-2cbebfe4639a/download/rwl_manual_hr_cwc_007_2026_2030.csv`
- **HTTP Method**: `GET`
- **Authentication**: None required.
- **Filter**: Filter on `State LGD Code == 29` (Karnataka).

#### Variables & Transformation Mapping

| Source CSV Column | Target Field | Target Table | Source Unit | Target Unit | Transformation / Mapping |
|---|---|---|---|---|---|
| `Station` | `river_stations.name` | `river_stations` | String | String | Trim and normalize |
| `River` | `rivers.name` | `rivers` | String | String | Trim and normalize |
| `Basin` | `river_basins.name` | `river_basins` | String | String | Trim and normalize |
| `Latitude`, `Longitude` | `location` | `river_stations` | Decimal degrees | `Geometry(Point, 4326)` | `ST_SetSRID(ST_Point(lon, lat), 4326)` |
| `District LGD Code` | `district_id` | `river_stations` | Integer | UUID ForeignKey | Lookup `districts.id` via `districts.district_code` |
| `Data Acquisition Time` | `observed_at` | `river_observations` | `DD-MM-YYYY HH:MM` (IST) | `TIMESTAMPTZ` (UTC) | Parse IST datetime, convert to UTC (`-05:30`) |
| `River Water Level Manual Hourly (meter)` | `water_level_m` | `river_observations` | metres | `_m` | Parse float directly; validate $> 0.0$ |
| `Is_DischargeDataAvailable` | `discharge_m3s` | `river_observations` | Boolean / String | `_m3s` | If `"No"`, set `discharge_m3s = NULL` (never zero) |

#### Provenance & Freshness
- `source`: `"cwc_nwic_river_level"`
- `source_record_id`: Formatted as `"cwc_{station_name}_{observed_at_utc}"`
- `processing_version`: `"v1.0"`
- Freshness:
  - `FRESH`: `observed_at` within past 6 hours.
  - `STALE`: `observed_at` between 6 and 24 hours.
  - `UNAVAILABLE`: Older than 24 hours.

---

### 1.4 India Flood Inventory Historical Loader (`IfiFloodEventLoader`)

#### Source Identity
- **Source Name**: India Flood Inventory (IFI) v3.0
- **Authority / Provider**: HydroSense Lab, Department of Civil Engineering, IIT Delhi (Dr. Manabendra Saharia)
- **Repository URL**: `https://github.com/hydrosenselab/India-Flood-Inventory`
- **Resource URL**: `https://raw.githubusercontent.com/hydrosenselab/India-Flood-Inventory/main/v3.0/India_Flood_Inventory_v3.csv`
- **Citation**: Zenodo DOI `10.5281/zenodo.10892285`
- **Operational Role**: `PRIMARY_HISTORICAL` (ML Ground Truth)

#### Ingestion & Extraction Protocol
- **Access Method**: HTTP Direct CSV Download via Raw GitHub / Zenodo CDN.
- **Filter Rule**: Filter rows where `State` contains `"Karnataka"` or `State_Codes` contains `"29"`. (Yields verified set of 494 historical flood event records).

#### Field Mapping Contract

| IFI Column | Target Field | Target Table | Datatype | Transformation |
|---|---|---|---|---|
| `UEI` | `source_record_id` | `flood_observations` | String | Preserved verbatim (e.g. `UEI-IMD-FL-2023-0347`) |
| `Start Date` | `start_date` | `flood_observations` | `DATE` | Parse `DD-MM-YYYY HH:MM` -> `YYYY-MM-DD` |
| `End Date` | `end_date` | `flood_observations` | `DATE` | Parse `DD-MM-YYYY HH:MM` -> `YYYY-MM-DD` |
| `Duration(Days)` | `duration_days` | `flood_observations` | `INTEGER` | Cast to integer |
| `Main Cause` | `cause` | `flood_observations` | `VARCHAR(100)` | Standardize strings (e.g. `"Heavy Rains & Floods"`) |
| `Districts` | `affected_districts_raw` | `flood_observations` | `TEXT` | Raw comma-separated district names |
| `District_LGD_Codes` | `district_lgd_codes` | `flood_observations` | `TEXT` / Array | Parse integer LGD codes; join to `districts.district_code` |
| `Human fatality` | `fatalities` | `flood_observations` | `INTEGER` | Parse integer; empty/blank becomes `NULL` |
| `Description of Casualties/injured` | `damage_description` | `flood_observations` | `TEXT` | Sanitize and store damage summary |
| `Event Source` | `source` | `flood_observations` | `VARCHAR(100)` | `"ifi_v3_imd"` |

#### ML Ground Truth Label Generation Contract
- **Target Spatial Unit**: District polygon (identified by `districts.district_code` / LGD code).
- **Target Temporal Unit**: Calendar day ($t \in [\text{start\_date}, \text{end\_date}]$).
- **Binary Label Assignment**:
  $$y_{d, t} = \begin{cases} 1 & \text{if district } d \text{ belongs to an active flood event on date } t \\ 0 & \text{if no documented flood event for district } d \text{ on date } t \end{cases}$$
- **Evaluation Split Contract**: Strictly time-based per `CONSTRAINTS.md` and `DECISIONS.md`:
  - Training Period: `1980-01-01` to `2018-12-31`
  - Validation / Test Period: `2019-01-01` to `2023-12-31`
  - Random train/test split is **strictly prohibited**.

---

### 1.5 Copernicus DEM Terrain Feature Extractor (`CopernicusDemExtractor`)

#### Source Identity
- **Source Name**: Copernicus DEM GLO-30
- **Authority / Provider**: European Space Agency (ESA) / Airbus Defence and Space / DLR
- **Distribution**: Registry of Open Data on AWS (`s3://copernicus-dem-30m`)
- **Operational Role**: `PRIMARY_HISTORICAL` / `SUPPORTING_GEOGRAPHIC`

#### Retrieval & Processing Protocol
- **Access Protocol**: Direct AWS S3 HTTPS tile access via Cloud Optimized GeoTIFF (COG) HTTP range requests.
- **Karnataka Tile Bounding Box**: $11^\circ\text{N}$ to $19^\circ\text{N}$, $74^\circ\text{E}$ to $79^\circ\text{E}$.
- **Required Tile Set** (18 tiles total):
  ```text
  N11_E074, N11_E075, N11_E076, N11_E077,
  N12_E074, N12_E075, N12_E076, N12_E077, N12_E078,
  N13_E074, N13_E075, N13_E076, N13_E077, N13_E078,
  N14_E074, N14_E075, N14_E076, N14_E077,
  N15_E074, N15_E075, N15_E076, N15_E077,
  N16_E074, N16_E075, N16_E076, N16_E077,
  N17_E075, N17_E076, N17_E077,
  N18_E076, N18_E077
  ```
- **Derived Terrain Features (per District and Taluk polygon)**:
  1. `elevation_mean_m`: Zonal mean elevation (metres above sea level).
  2. `elevation_min_m`: Zonal minimum elevation.
  3. `elevation_max_m`: Zonal maximum elevation.
  4. `slope_mean_deg`: Calculated from raster gradient ($\text{degrees}$), not hardcoded per district.
  5. `slope_max_deg`: Maximum local slope gradient.
- **CRS & Units**:
  - Horizontal CRS: WGS 84 (`EPSG:4326`).
  - Vertical Datum: EGM2008 geoid.
  - Measurement unit: metres (`_m`).

---

### 1.6 OpenStreetMap Emergency Facilities Loader (`OsmEmergencyFacilityLoader`)

#### Source Identity
- **Source Name**: OpenStreetMap Amenities & Emergency Infrastructure
- **Authority / Provider**: OpenStreetMap Community / FOSSGIS e.V.
- **Access Method**: Overpass API (`https://overpass-api.de/api/interpreter`)
- **Operational Role**: `SUPPORTING_GEOGRAPHIC`

#### Retrieval Protocol
- **HTTP Method**: `GET` / `POST`
- **Mandatory Header**: Custom User-Agent header (e.g. `User-Agent: FloodPulse-Research/1.0`) to avoid HTTP 406.
- **Overpass Query Filters**:
  - `node["amenity"="hospital"](bbox);`
  - `node["amenity"="fire_station"](bbox);`
  - `node["amenity"="police"](bbox);`
  - `node["healthcare"="hospital"](bbox);`
- **Prohibited Overpass Queries**: `amenity=shelter` must **not** be queried or ingested as an evacuation shelter.

#### Mapping to `emergency_facilities`
- `name`: `tags.name` (fallback to `"Unnamed " + amenity` if blank)
- `facility_type`: Mapped strictly to `'hospital'`, `'fire_station'`, `'police_station'`
- `location`: `ST_SetSRID(ST_Point(lon, lat), 4326)`
- `source`: `'openstreetmap'`
- `verification_status`: `'UNVERIFIED'` (unless cross-referenced with ABDM / official registry)
- `capacity`: `NULL` (unknown capacity is never treated as zero or available)

---

## 2. Phase 2 Adapter Boundaries

To prevent architectural drift and preserve data integrity, every Phase 2 adapter is constrained by strict positive and negative operational boundaries:

### `OpenMeteoAdapter`
- **MUST**:
  - Retrieve valid JSON from documented Open-Meteo forecast and archive endpoints.
  - Enforce `wind_speed_unit=ms` and `timezone=UTC`.
  - Validate coordinate bounds within Karnataka.
  - Store observation timestamps in UTC.
  - Record complete provenance metadata (`source`, `retrieved_at`, `processing_version`).
  - Flag missing or corrupted fields explicitly.
- **MUST NOT**:
  - Calculate or infer flood risk scores.
  - Assign flood event labels.
  - Replace missing rainfall with `0.0`.
  - Present numerical weather prediction output as physical in-situ rain gauge observations.
  - Attempt to write to emergency facility, shelter, or prediction tables.

### `NwicReservoirAdapter`
- **MUST**:
  - Download official NWIC CSV resource using stream buffers.
  - Apply exact unit conversions ($ft \to m$, $TMC \to MCM$, $cusecs \to m^3/s$).
  - Filter and match records to verified Karnataka reservoir entities.
  - Store conversion parameters in provenance metadata.
- **MUST NOT**:
  - Silently store raw imperial units in metric database columns.
  - Impute reservoir storage from rainfall or previous year averages.
  - Generate synthetic daily inflows/outflows during communication outages.
  - Mix river gauge station data into reservoir tables.

### `NwicRiverLevelAdapter`
- **MUST**:
  - Extract CWC river monitoring records for Karnataka (`State LGD Code == 29`).
  - Map river gauge locations to PostGIS Point geometries in EPSG:4326.
  - Normalize station names and link to parent river and basin entities.
  - Set `discharge_m3s = NULL` when discharge telemetry is withheld.
- **MUST NOT**:
  - Convert missing discharge to `0.0 m³/s`.
  - Extrapolate danger levels or invent flood warnings not present in the data.
  - Modify administrative district boundaries based on station addresses.

### `IfiFloodEventLoader`
- **MUST**:
  - Extract and normalize historical flood events for Karnataka from IFI v3.0.
  - Validate start and end dates ($start\_date \le end\_date$).
  - Map affected district names to standardized LGD district codes.
  - Generate discrete daily District × Day binary labels.
  - Enforce temporal train/test split cutoff.
- **MUST NOT**:
  - Fabricate taluk-level or locality-level flood labels.
  - Merge rainfall thresholds into the target definition.
  - Use future flood events to train past timeframes (no data leakage).
  - Perform random train/test splits.

### `CopernicusDemExtractor`
- **MUST**:
  - Stream Cloud Optimized GeoTIFF windows via HTTP range requests.
  - Compute zonal summary metrics (mean elevation, min elevation, slope in degrees) per district and taluk polygon.
  - Validate that horizontal CRS is EPSG:4326 and vertical units are metres.
- **MUST NOT**:
  - Hardcode district slope or elevation values.
  - Treat decimal degree differences as metric distances in terrain gradient calculations.
  - Overwrite raw boundary geometries with raster extents.

---

## 3. Strict Missing-Data & Integrity Rules

Every adapter and database service in Phase 2 must enforce the core integrity principles from `CONSTRAINTS.md` and `DATA_CONTRACT.md`:

```text
MISSING ≠ ZERO
UNAVAILABLE ≠ ZERO
STALE ≠ CURRENT
UNKNOWN SHELTER OCCUPANCY ≠ AVAILABLE CAPACITY
FAILED API REQUEST ≠ NO RAINFALL
MISSING FLOOD OBSERVATION ≠ NO FLOOD
MISSING RESERVOIR MEASUREMENT ≠ ZERO STORAGE
MISSING RIVER GAUGE VALUE ≠ SAFE RIVER LEVEL
```

### Concrete Enforcement Specifications:
1. **Rainfall Observations**: If an API query fails, times out, or returns a null field, the resulting record must record `rainfall_mm = NULL`. It must **never** be recorded as `0.0 mm`.
2. **Missing Flag Decoding**: NASA POWER encodes missing values as `-999.0`. The adapter must intercept `-999.0` and store `NULL`. It must **never** store `-999.0` as valid temperature or rainfall.
3. **River Discharge**: When CWC marks `Is_DischargeDataAvailable: No`, `discharge_m3s` must be set to `NULL`. It must **never** default to `0.0`.
4. **Shelter Occupancy**: Because real-time occupancy telemetry is absent, `shelter_occupancy` must remain `NULL`. Ingestion code must **never** default occupancy to `0` or infer occupancy from capacity.
5. **No Median or Stale Imputation**: Missing values must never be silently backfilled with past values or district averages. If data is unavailable, the database must store `NULL`, and the API must return `null` with `status: "UNAVAILABLE"` or `"STALE"`.

---

## 4. Source Fallback & Failure Policies

When a primary operational source fails or experiences an outage, adapters must execute explicit, deterministic fallback procedures without violating data integrity:

| Data Requirement | Primary Operational Source | Failure Mode | Permitted Fallback Action | Strictly Prohibited Actions |
|---|---|---|---|---|
| **Operational Weather & Rainfall** | Open-Meteo API | HTTP 5xx, Network Timeout, Rate Limit | 1. Retry up to 3 times with exponential backoff.<br>2. If still failing, record ingestion run status as `FAILED`.<br>3. Mark current weather status as `STALE` (if prior data $< 24$h) or `UNAVAILABLE`.<br>4. Trigger secondary query to NASA POWER for retrospective daily baseline. | - Do NOT fabricate synthetic rainfall.<br>- Do NOT silently record `0.0 mm`.<br>- Do NOT copy yesterday's weather as today's forecast. |
| **Reservoir Telemetry** | NWIC Karnataka Reservoir CSV | Network Failure, Portal 404/500 | 1. Log failure in `data_ingestion_runs`.<br>2. Preserve existing database observations.<br>3. Mark reservoir telemetry freshness as `STALE`. | - Do NOT simulate daily reservoir release.<br>- Do NOT invent storage numbers.<br>- Do NOT extrapolate inflow from rainfall. |
| **River Gauge Water Level** | NWIC CWC Hourly CSV | Stream Inaccessible, Station Offline | 1. Mark station observation status as `UNAVAILABLE`.<br>2. Retain previous valid gauge reading flagged with `freshness = STALE`. | - Do NOT assume river level has returned to normal.<br>- Do NOT guess water levels.<br>- Do NOT compute synthetic discharge. |
| **Administrative Boundaries** | KSRSAC / KGIS Portal | Direct Download 404/403 | 1. Ingest verified offline KSRSAC gazetted shapefiles.<br>2. Use Datameet Census 2011 WGS84 shapefiles as validated secondary geometric reference.<br>3. Validate all polygon boundaries against LGD master code table. | - Do NOT generate bounding-box rectangles.<br>- Do NOT approximate administrative units with centroids.<br>- Do NOT hand-draw boundaries. |
| **Emergency Facilities & Shelters** | DDMP Official PDF Extraction | Missing District DDMP | 1. Ingest only verified districts.<br>2. Mark unverified districts as `SHELTER_DATA_PENDING`.<br>3. Display hospital/fire facilities only. | - Do NOT use OSM `amenity=shelter` as evacuation shelters.<br>- Do NOT manufacture shelter addresses or capacities. |

---

## 5. Blockers & Open Decisions Before Phase 2 Execution

Before production ingestion code is executed in Phase 2, the following specific blockers and open decisions must be resolved:

### Blocker 1: Official KGIS Shapefile Curation vs Datameet Geometry Baseline
- **Current Status**: KGIS root portal is active, but direct automated downloads against legacy IIS directories return HTTP 404/403. Datameet Census 2011 boundaries are verified in WGS84 (`EPSG:4326`) and accessible.
- **Impact**: Ingestion of administrative boundaries is the foundation for all spatial joins and PostGIS foreign keys.
- **Resolution Path**:
  1. For Phase 2 development and testing, load the verified Datameet Census 2011 Karnataka district and taluk shapefiles.
  2. Normalize all district names against the master LGD code registry (LGD State Code `29`).
  3. Reconcile post-2011 administrative changes (specifically Vijayanagara district split from Ballari in 2021) via a documented geometry split or official KSRSAC offline shapefile import.
- **Phase 2 Readiness**: `READY WITH WORKAROUND` (Can proceed using Datameet WGS84 shapefiles + LGD code dictionary).

### Blocker 2: Machine-Readable LGD Code Master Directory Ingestion
- **Current Status**: LGD web portal was verified (HTTP 200), and LGD codes were empirically confirmed in CWC and IFI datasets. Direct programmatic web-service API is government-gated.
- **Impact**: Required as the universal primary key for administrative units across weather, hydrology, and flood tables.
- **Resolution Path**: Download official LGD Directory CSV export for Karnataka (State 29) from `lgdirectory.gov.in` and place in `data/raw/lgd/` as a static master reference table.
- **Phase 2 Readiness**: `READY` (CSV export is publicly downloadable without credentials).

### Blocker 3: Designated Evacuation Shelter Dataset Curation
- **Current Status**: No machine-readable shelter API exists in Karnataka. Designated relief shelters are documented in static PDF annexures of published District Disaster Management Plans (DDMPs).
- **Impact**: FloodPulse cannot provide automated shelter routing until verified relief centers are populated.
- **Resolution Path**:
  1. Create a curated, peer-reviewed seed dataset (`data/raw/shelters/verified_karnataka_ddmp_shelters.csv`) containing officially designated relief centers extracted from published DDMPs for top flood-prone districts (Belagavi, Kodagu, Dakshina Kannada).
  2. Each record must include district, taluk, village/town, facility name, address, source DDMP document, page number, and contact info.
  3. Coordinates must be assigned by geocoding verified addresses against official village centroids.
  4. Occupancy must be set to `NULL`.
- **Phase 2 Readiness**: `READY WITH SPECIFIC PROCESS` (Requires static seed file preparation prior to running shelter loader).

### Blocker 4: GloFAS / Copernicus CDS Credential Setup
- **Current Status**: Credential-blocked. Unauthenticated API access returns 404/403.
- **Impact**: GloFAS gridded river discharge forecasts cannot be retrieved automatically in current development environment.
- **Resolution Path**: Exclude GloFAS from Phase 2 MVP blocking dependencies. Rely on in-situ CWC river gauge water level observations from NWIC. If CDS user credentials are provided later, implement `GlofasForecastAdapter` in Phase 3.
- **Phase 2 Readiness**: `DEFERRED` (Does not block Phase 2 core ingestion).
