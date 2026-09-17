# FloodPulse API Validation Lab (Phase 2.3 Report)

## 1. Executive Summary

This document establishes the empirical results of the **Phase 2.3 Real Source / API Validation Lab** for the Karnataka AI Flood Intelligence & Early-Warning System (FloodPulse). 

In accordance with `MASTER_PROJECT_SPEC.md`, `CONSTRAINTS.md`, and strict scientific integrity guidelines:
- **No data was fabricated**: No synthetic weather, river levels, reservoir capacities, flood observations, or mock coordinates were generated.
- **No API endpoints were invented**: Only officially documented or visibly exposed and verified endpoints were queried.
- **No production database modification**: The 34 application tables deployed in Phase 2.2 remain completely clean of unvalidated or synthetic records.
- **Failed or restricted sources are reported honestly**: Where endpoints require institutional credentials, static public IPs, or are restricted to government intranets, they are recorded as `CREDENTIAL_BLOCKED` or `UNAVAILABLE` without assumption.

---

## 2. API Validation Laboratory Architecture

A reproducible API testing lab was constructed using Postman (Collection Format v2.1.0) and command-line `curl` tooling.

- **Postman Collection**: `postman/FloodPulse_API_Validation_Lab.postman_collection.json`
- **Postman Environment**: `postman/FloodPulse_Lab.postman_environment.json`

The validation lab is organized into 8 source domain modules:
```text
FloodPulse API Validation Lab
├── 01_IMD (India Meteorological Department)
├── 02_CWC (Central Water Commission / NWIC)
├── 03_NRSC_NDEM (National Database for Emergency Management)
├── 04_Bhuvan (ISRO Geoportal)
├── 05_India_WRIS (Water Resources Information System)
├── 06_Karnataka_OGD (Karnataka Open Government Data / OpenCity)
├── 07_Open_Meteo (Operational NWP & Reanalysis Feeds)
└── 08_OSM (OpenStreetMap / Overpass API)
```

---

## 3. Empirical Test Probing & Field Verification

### 3.1 IMD (India Meteorological Department)

#### Official Authority & Gateway
- **Organization**: India Meteorological Department (Ministry of Earth Sciences, Govt of India)
- **Official Portal**: `https://api.imd.gov.in/` (IMD API Management Platform)
- **API Reference Documented**: `https://api.imd.gov.in/public/api_reference.html`
- **Visual Portals**: `https://mausam.imd.gov.in`, `https://city.imd.gov.in`

#### Authentication & Access Mechanism
- **Access Method**: REST API (HTTPS GET)
- **Authentication**: **Mandatory API Key**. User onboarding requires formal registration (`register.php`) restricted to official government/institutional domains (`@gov.in`, `@nic.in`, `@cdot.in`, `@cdac.in`, `@nhai.org`, `@icar.org.in`).
- **Unauthenticated Probing Result**:
  ```bash
  curl -sI "https://api.imd.gov.in/api/v1/aws_data?sid=13"
  # HTTP/1.1 401 Unauthorized
  # Response body: {"error":"API key missing"}
  ```

#### Documented & Probed Endpoints
| Product | Verified URL Pattern | Parameters | Discovered Real Fields | Status |
|---|---|---|---|---|
| **AWS / ARG Real-Time Telemetry** | `https://api.imd.gov.in/api/v1/aws_data` | `sid=13` (Karnataka) | `Station_ID`, `Station_Name`, `Date`, `Time_UTC`, `Rainfall_mm`, `Temp_degC`, `Humidity_pct`, `Wind_Speed_kmph`, `MSLP_hPa` | `CREDENTIAL_BLOCKED` |
| **District Rainfall** | `https://api.imd.gov.in/api/v1/districtrainfall` | `id={district_id}` | `OBJ_ID`, `District`, `Date`, `Daily Actual`, `Daily Normal`, `Daily Departure Per`, `Daily Category`, `Weekly Actual`, `Cumulative Actual` | `CREDENTIAL_BLOCKED` |
| **District Warnings** | `https://api.imd.gov.in/api/v1/districtwarning` | `id={district_id}` | `Obj_id`, `Date`, `UTC`, `District`, `Day_1`..`Day_5` warning codes, `Day1_Color`..`Day5_Color` | `CREDENTIAL_BLOCKED` |
| **Current Weather** | `https://api.imd.gov.in/api/v1/current_wx` | `id={station_id}` | `Station Id`, `Station`, `Date of Observation`, `Time of Observation`, `M.S.L.P`, `Wind Direction`, `Wind Speed`, `Temperature`, `Weather Code`, `Nebulosity`, `Humidity`, `Last 24 hrs Rainfall` | `CREDENTIAL_BLOCKED` |
| **City Forecast 7-Day** | `https://api.imd.gov.in/api/v1/cityforecastloc` | `id={station_id}` | `Date`, `Station_Code`, `Station_Name`, `Today_Max_temp`, `Today_Min_temp`, `Past_24_hrs_Rainfall`, `Relative_Humidity_at_0830`, `Relative_Humidity_at_1730`, `Day_1_Forecast`..`Day_7_Forecast`, `Latitude`, `Longitude` | `CREDENTIAL_BLOCKED` |

#### IMD Gridded Rainfall (Historical Archives)
- **Portal**: `https://imdpune.gov.in`
- **Empirical Test**: Port 443 / 80 connection tests timed out or failed to negotiate TLS from non-whitelisted IP pools (`curl: (28) Failed to connect to imdpune.gov.in port 443`).
- **Offline Acquisition Pattern**: IMD 0.25° gridded daily rainfall binary files (1901–present) can be downloaded via Python `imdlib` package or acquired through official CDAC/IMD data distribution channels.

---

### 3.2 CWC & NWIC (Central Water Commission / National Water Informatics Centre)

#### Official Authority & Gateway
- **Organization**: National Water Informatics Centre (NWIC), Department of Water Resources, Ministry of Jal Shakti
- **Portal**: National Water Data Portal (`https://nwdp.nwic.gov.in`)
- **API Standard**: Open CKAN REST API v3 (`https://nwdp.nwic.gov.in/api/3/action/`)

#### Authentication & Access Mechanism
- **Access Method**: Completely Open HTTP GET (REST API + direct CSV/GeoJSON downloads). No API keys or authentication headers required.
- **CKAN Query Probing**:
  ```bash
  curl -s "https://nwdp.nwic.gov.in/api/3/action/package_search?q=karnataka&rows=5"
  # HTTP/1.1 200 OK (Found 45 official Karnataka water datasets)
  ```

#### Verified Hydrological Products
1. **Karnataka Reservoir Telemetry Dataset** (`karnataka_man_reservoir_data.csv`):
   - **URL**: `https://nwdp.nwic.gov.in/dataset/e35dc28a-6f9c-486d-b598-87a21397018e/resource/26800982-045c-41de-821d-b1ca080a79a8/download/karnataka_man_reservoir_data.csv`
   - **Size**: 16.4 MB (Active, modified 2026-09-17)
   - **Temporal Coverage**: 1990 to 2026 (daily records)
   - **Spatial Coverage**: 14+ major Karnataka dams (Almatti, KRS, Kabini, Tungabhadra, Bhadra, Ghataprabha, Malaprabha, Linganamakki, Supa, Harangi, Hemavathi, etc.)
   - **Verified Real Fields**:
     ```text
     Reservoir Name, Basin, Sub Basin, River, Monitoring Date, Percentage Full,
     Reservoir Level (ft), Design Gross Capacity (TMC), Gross Capacity (TMC),
     Live Capacity (TMC), Live Above Cill (TMC), Inflow (Cusecs), Outflow to River (Cusecs),
     Canal Withdrawal (Cusecs), Evaporation (Cusecs), Cumulative Inflow (TMC),
     Cumulative Outflow (TMC), Cumulative Withdrawal (TMC), Cumulative Evaporation (TMC)
     ```
   - **Mandatory Conversion Contracts**:
     - Water Level: $\text{Level}_{\text{m}} = \text{Level}_{\text{ft}} \times 0.3048$
     - Storage / Capacity: $\text{Storage}_{\text{MCM}} = \text{Storage}_{\text{TMC}} \times 28.3168$
     - Discharge / Inflow / Outflow: $\text{Discharge}_{\text{m}^3/\text{s}} = \text{Flow}_{\text{cusecs}} \times 0.0283168$

2. **CWC In-Situ River Gauge Water Level** (`rwl_manual_hr_cwc_009_2026_2030.csv`):
   - **URL**: `https://nwdp.nwic.gov.in/dataset/d951a09c-6cf8-470e-be77-e80116f13d34/resource/37cba82e-f745-4004-80d2-b05cad65b8e4/download/rwl_manual_hr_cwc_009_2026_2030.csv`
   - **Temporal Coverage**: Hourly readings (current active tranche 2026–2030, historical tranches back to 1961)
   - **Spatial Coverage**: Cauvery, Krishna, and Godavari river basins in Karnataka
   - **Verified Real Fields**:
     ```text
     SlNo, Station, Agency, State LGD Code, State, District LGD Code, District,
     Tehsil, Block, Village, River, Basin, Tributary, Subtributary, SubSubtributary,
     Local River, Latitude, Longitude, Is_DischargeDataAvailable, RL_of_zeroGauge,
     MeanSeaLevel, Data Acquisition Time, River Water Level Manual Hourly (meter)
     ```
   - **Units**: Level in metres (`_m`), Coordinates in decimal degrees WGS84 (`EPSG:4326`).
   - **Status**: `VERIFIED`

---

### 3.3 NRSC / ISRO / NDEM

#### Official Authority & Gateway
- **Organization**: National Remote Sensing Centre (NRSC), Indian Space Research Organisation (ISRO)
- **Portal**: National Database for Emergency Management (`https://ndem.nrsc.gov.in`)

#### Authentication & Access Probing
- **Access Protocol**: Restricted institutional web service
- **Authentication**: **Mandatory Login & OTP Authentication**. Restricted strictly to designated disaster managers (MHA, NDMA, SDMAs, District Collectors).
- **Probing Result**: Root URL timed out or denied access from unauthenticated client IPs (`curl: (28) Failed to connect to ndem.nrsc.gov.in`).
- **Machine-Readable Status**: `PORTAL PRODUCT — MACHINE-READABLE ACCESS NOT CONFIRMED` / `CREDENTIAL_BLOCKED`.
- **Policy**: Inundation maps and flood hazard layers shown on the NDEM portal are **not** accessible via open public REST/WFS APIs. Map screenshots must **never** be scraped or converted to pseudo-numerical data.

---

### 3.4 Bhuvan (ISRO Geoportal)

#### Official Authority & Gateway
- **Organization**: NRSC / ISRO
- **Portal**: `https://bhuvan.nrsc.gov.in` (modern Next.js entry: `/ngmaps`)
- **Documented OGC Endpoints**:
  - `https://bhuvan-ras2.nrsc.gov.in/cgi-bin/hazard.exe` (Flood Hazard WMS)
  - `https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe` (Annual Flood WMS)
  - `https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms` (Thematic Vector WMS)

#### Empirical Probing Results
- Web portal entry `https://bhuvan.nrsc.gov.in/ngmaps` is active (HTTP 200/302).
- Vector WMS `bhuvan-vec2.nrsc.gov.in` timed out (`curl: (28)`).
- Raster WMS endpoints (`hazard.exe`, `flood.exe`) return HTTP 200 headers via Akamai CDN, but return `content-length: 0` without valid XML capabilities to public clients.
- **Classification**: `PORTAL ONLY — VISUALIZATION SERVICE`. Suitable for reference map rendering in browser overlays, but **not suitable** as machine-readable feature or target pipelines.

---

### 3.5 India-WRIS

#### Official Authority & Gateway
- **Organization**: Ministry of Jal Shakti / NWIC
- **Portal**: `https://indiawris.gov.in` / `https://nwdp.nwic.gov.in`

#### Verified Spatial Datasets
- **Karnataka Water Spread Area Phase I & Phase II** (Package ID: `bbfedeba-9ea1-4b85-9b59-399bec4e93c3`):
  - Water Spread Area Phase I GeoJSON: `https://nwdp.nwic.gov.in/.../dwa_ph1_ka_geojson.zip`
  - Water Spread Area Phase II GeoJSON: `https://nwdp.nwic.gov.in/.../dwa_ph2_ka_geojson.zip`
  - Formats: GeoJSON, KML, ESRI Shapefile
  - CRS: WGS84 (`EPSG:4326`)
  - Status: `VERIFIED` (Supporting GIS layer for surface water bodies)

---

### 3.6 Karnataka State OGD & KSNDMC

#### Official Authority & Gateway
- **Authority**: Karnataka State Natural Disaster Monitoring Centre (KSNDMC) / OpenCity
- **Portal**: `https://data.opencity.in` (CKAN API) / `https://karnataka.data.gov.in`
- **Probing Result**:
  - Direct KSNDMC automated live streaming API is non-existent.
  - OpenCity CKAN API (`https://data.opencity.in/api/3/action/package_search?q=rainfall+karnataka`) returned HTTP 200 OK.
  - Verified dataset: `ka_dist_rainfall_2025.csv` (Karnataka Annual Rainfall 2025 across 31 districts).
  - Columns: `Sl No`, `District`, `Annual Normal`, `Annual Actual`, `Annual Departure (%)`, `Pre Monsoon Normal`, `Pre Monsoon Actual`, `SWM Normal`, `SWM Actual`, `NEM Normal`, `NEM Actual`.
  - Units: Millimetres (`mm`).
  - **Limitation**: Aggregated annual and seasonal reports only; does not provide the real-time hourly/daily feeds needed for operational flood early warning.
  - Status: `VERIFIED (SECONDARY REFERENCE)`

---

### 3.7 Open-Meteo

#### Official Authority & Documentation
- **Organization**: Open-Meteo GmbH
- **Documentation**: `https://open-meteo.com/en/docs`
- **Authentication**: None required for standard usage volume (up to 10,000 queries/day).

#### Verified Operational Endpoints
1. **Weather Forecast API** (`https://api.open-meteo.com/v1/forecast`):
   - Probed at Mysuru coordinates (`12.2958`, `76.6394`):
     ```bash
     curl -s "https://api.open-meteo.com/v1/forecast?latitude=12.2958&longitude=76.6394&current=temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m&hourly=temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m,surface_pressure&wind_speed_unit=ms&forecast_days=3&timezone=UTC"
     # HTTP/1.1 200 OK
     ```
   - **Units Verified**:
     - `temperature_2m`: `°C`
     - `relative_humidity_2m`: `%`
     - `precipitation`, `rain`: `mm`
     - `wind_speed_10m`: `m/s` (with `wind_speed_unit=ms`)
     - `surface_pressure`: `hPa`
   - **Time**: ISO 8601 UTC.
   - **Status**: `VERIFIED (PRIMARY OPERATIONAL)`

2. **Historical Weather Archive API** (`https://archive-api.open-meteo.com/v1/archive`):
   - Probed for Karnataka July 2023 flood period:
     ```bash
     curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=12.2958&longitude=76.6394&start_date=2023-07-01&end_date=2023-07-03&daily=precipitation_sum,rain_sum,temperature_2m_max,temperature_2m_min&timezone=UTC"
     # HTTP/1.1 200 OK
     # Returns: daily.precipitation_sum: [0.90, 1.10, 3.80] mm
     ```
   - **Status**: `VERIFIED (HISTORICAL WEATHER FEATURES)`

3. **GloFAS River Discharge Forecast API** (`https://flood-api.open-meteo.com/v1/flood`):
   - Probed for Karnataka coordinates:
     ```bash
     curl -s "https://flood-api.open-meteo.com/v1/flood?latitude=12.2958&longitude=76.6394&daily=river_discharge,river_discharge_mean,river_discharge_max,river_discharge_min&forecast_days=3"
     # HTTP/1.1 200 OK
     # Returns: daily_units: {"river_discharge":"m³/s"}, daily: {"river_discharge":[0.22,0.03,0.30]}
     ```
   - **Units Verified**: `m³/s` (matches `_m3s` contract).
   - **Status**: `VERIFIED (HYDROLOGICAL FORECAST REFERENCE)`

---

### 3.8 OpenStreetMap (OSM) / Overpass API

#### Official Documentation & Protocol
- **Endpoint**: `https://overpass-api.de/api/interpreter`
- **Protocol**: Overpass QL via HTTP POST.
- **Mandatory Policy**: Custom `User-Agent` header required (standard curl returns `406 Not Acceptable`).

#### Empirical Probing Results
- Query executed for Mysuru healthcare facilities:
  ```bash
  curl -s -A "FloodPulse-API-Lab/1.0" --data-urlencode 'data=[out:json][timeout:15]; node["amenity"="hospital"](12.28,76.60,12.33,76.68); out body;' "https://overpass-api.de/api/interpreter"
  # HTTP/1.1 200 OK
  # Elements returned: 542383450 ("Ashoka Clinic", lat 12.2922, lon 76.6423)
  ```
- **CRS**: WGS84 (`EPSG:4326`).
- **Critical Policy Confirmation**:
  - **OSM places tagged `shelter` are NOT flood evacuation shelters.**
  - OSM ingestion is strictly limited to `facility_type="hospital"`, `facility_type="fire_station"`, and `facility_type="police_station"`.
- **Status**: `VERIFIED (SUPPORTING FACILITIES)`

---

## 4. Flood Target Ground Truth Verification

Supervised flood prediction requires authentic historical flood observations ($y \in \{0, 1\}$).

- **Primary Source**: **India Flood Inventory (IFI v3.0)** — IIT Delhi HydroSense Lab (Dr. Manabendra Saharia).
- **Repository**: `https://github.com/hydrosenselab/India-Flood-Inventory` (Zenodo DOI `10.5281/zenodo.10892285`).
- **Empirical Confirmation**:
  - **494 documented flood events in Karnataka** spanning 1969 to 2023.
  - Contains: Unique Event ID (`UEI`), `Start Date`, `End Date`, `Duration(Days)`, `Main Cause`, `Districts`, `District_LGD_Codes`, `State_Codes: 29`, `Severity`, `Human fatality`, `Extent of damage`.
  - Spatial Resolution: **District level**.
  - **Scientific Independence**: Derived from official IMD Disastrous Weather Reports; independent of rainfall formula thresholds or elevation heuristics.
- **Secondary Target**: CWC Official River Water Level exceeding Danger Level (`water_level_m >= danger_level_m`).

---

## 5. Machine-Readable Availability Summary

| Availability Class | Sources / Products Included | Integration Strategy |
|---|---|---|
| **Verified API** | Open-Meteo Weather API, Open-Meteo Archive API, Open-Meteo Flood API, NWIC CKAN API, OpenCity CKAN API, Overpass API | Direct automated HTTP REST adapters |
| **Verified Download** | NWIC Reservoir CSV (`karnataka_man_reservoir_data.csv`), NWIC River Level CSV (`rwl_manual_hr_cwc_*.csv`), IFI v3.0 CSV, Copernicus DEM GLO-30 (AWS S3 COG), NWIC Water Spread Area (GeoJSON) | Automated batch download & streaming range parsers |
| **Verified GIS Service** | Datameet Census 2011 WGS84 Shapefiles, Copernicus DEM COG window streams | GeoPandas / PostGIS direct ingestion |
| **Credential Blocked** | IMD API Gateway (`api.imd.gov.in`), Copernicus CDS (GloFAS raw GRIB/NetCDF), NDEM Restricted Portal | Documented onboarding procedures; deferred from MVP blocking path |
| **Portal Only** | Bhuvan Web Map Services, KSNDMC Web Dashboard, IDRN Disaster Resource Portal | Human reference only; no automated scraping |
| **Unavailable** | Real-time live dam spillway webhook, live municipal shelter occupancy API | Handled as explicitly `NULL` (`missing ≠ 0`) |

---

## 6. Stop Conditions & Blockers Encountered

1. **IMD API Platform Registration**: Requires institutional static public IP and verified government domain credentials. Open-Meteo functions as the primary operational weather feed.
2. **Authoritative Live Shelter Occupancy**: No government department publishes real-time bed availability for flood relief shelters. Real-time occupancy must remain `NULL` in the database and API.
3. **Sub-District Flood Ground Truth**: Historical flood inundation polygons at taluk/village resolution do not exist across multi-decade records. Target resolution is fixed at the **District** level.
