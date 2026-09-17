# FloodPulse Final Source Selection

## Purpose

This document defines the final operational and historical data source selection for the FloodPulse project. Every candidate source evaluated during Phase 1.1 and Phase 1.2 is assigned exactly one definitive project role based on empirical testing, official documentation, accessibility, coverage, provenance, and compliance with project constraints.

This document serves as the decision authority for Phase 2 (Data Ingestion & Validation).

---

## Source Selection Rules & Taxonomy

Every data source in FloodPulse is assigned exactly one of the following operational roles:

| Role | Definition | Usage in FloodPulse |
|---|---|---|
| `PRIMARY_OPERATIONAL` | Authoritative or verified operational data feed providing near-real-time observations, continuous telemetry, or operational forecasts. | Direct ingestion into active operational tables (`weather_observations`, `weather_forecasts`, `river_observations`). |
| `PRIMARY_HISTORICAL` | Authoritative, multi-year historical dataset providing empirical observations for feature engineering, baseline statistics, or ML training targets. | Batch ingestion for historical baseline tables, feature store snapshots, and ML dataset generation. |
| `SECONDARY_REFERENCE` | Verified secondary, reanalysis, or scientific dataset used for cross-validation, sanity-checking, or spatial imputation where primary data is sparse. | Offline validation pipelines, model comparison, and cross-source consistency audits. |
| `SUPPORTING_GEOGRAPHIC` | Verified static or slowly changing cartographic, administrative, terrain, or facility geometries. | Geocoding, administrative containment queries, spatial distance metrics, and routing networks. |
| `CREDENTIAL_BLOCKED` | Verified public/scientific service requiring institutional credentials, personal API keys, or IP whitelisting not currently provisioned. | Documented with required onboarding path; excluded from Phase 2 blocking dependencies. |
| `DEFERRED` | Viable source whose integration is technically sound but postponed to post-MVP phases due to complexity, latency, or scope boundaries. | Retained in inventory; no Phase 2 adapter built. |
| `UNAVAILABLE` | Source investigated and confirmed to lack public machine-readable access, restricted exclusively to government internal logins, or non-existent. | Prohibited from integration; gaps documented honestly without synthetic substitution. |

---

## Final Source Selection Matrix

| Source | Dataset / API | Project Role | Entity / Tables Served | Variables / Fields | Spatial Coverage | Temporal Coverage | Frequency | Units | Provenance | Freshness | Access Status | Limitations | Phase 2 Action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Open-Meteo** | Weather Forecast & Archive API | `PRIMARY_OPERATIONAL` | `weather_observations`, `rainfall_observations`, `weather_forecasts` | Current & hourly precipitation, temperature, humidity, wind speed, surface pressure, 7-day forecast precipitation | Karnataka statewide (Point queries / 0.1° grid) | 1940–present (historical) + 7-day forecast | Hourly | `_mm`, `_c`, `_pct`, `_mps`, `_hpa` | API URL + timestamp + generation time | Fresh (<3h for obs, <6h for forecast) | Open HTTP REST (No credentials required) | Model-derived reanalysis and NWP forecast, not in-situ physical rain gauges. Must be attributed as model output. | Build operational weather ingestion adapter (`OpenMeteoAdapter`). |
| **NASA POWER** | Daily Point API (`temporal/daily/point`) | `SECONDARY_REFERENCE` | `weather_observations`, `feature_snapshots` | Daily precipitation (`PRECTOTCORR`), temperature (`T2M`), humidity (`RH2M`), wind speed (`WS10M`) | Karnataka statewide (0.5° grid) | 1981–present (2–3 day latency) | Daily | `_mm`, `_c`, `_pct`, `_mps` | NASA POWER API metadata + fill value tracking | Stale (2–3 day lag) | Open HTTP REST (No credentials required) | Coarse 0.5° spatial grid; 2–3 day publication latency prevents zero-day warning; missing values encoded as `-999.0`. | Build secondary reference validator for feature cross-checking (`NasaPowerValidator`). |
| **NWIC / CWC** | Karnataka Reservoir Dataset (`karnataka_man_reservoir_data.csv`) | `PRIMARY_HISTORICAL` | `reservoirs`, `reservoir_observations` | Water level, live storage, gross capacity, inflow, river outflow, canal withdrawal | 14+ Major Karnataka Dams (Almatti, KRS, Kabini, Tungabhadra, Bhadra, etc.) | 1990–2026 (daily records) | Daily manual report | Imperial: `ft`, `TMC`, `cusecs` (Convert to `_m`, `_mcm`, `_m3s`) | NWIC dataset resource URL + modification date | Fresh (Updated daily on NWIC) | Open HTTP CSV Download (No credentials required) | Uses imperial/custom engineering units requiring mandatory mathematical conversion; manual reporting times. | Build reservoir CSV ingestion pipeline with strict unit conversion (`NwicReservoirAdapter`). |
| **NWIC / CWC** | River Water Level Manual Hourly (`rwl_manual_hr_cwc_*.csv`) | `PRIMARY_OPERATIONAL` | `rivers`, `river_basins`, `river_stations`, `river_observations` | River water level, station name, basin, river, tributary, latitude, longitude, LGD state/district codes | Monitored CWC hydrological stations across Cauvery, Krishna, Godavari basins | 1961–present (current 2026 active tranche) | Hourly | `_m`, decimal degrees WGS84 | NWIC resource URL + CWC station acquisition time | Fresh (Hourly/daily updates) | Open HTTP CSV Download (No credentials required) | River discharge (`m3s`) is withheld or unavailable on many sensitive tributaries; water level is primary. | Build river telemetry ingestion adapter for Karnataka basins (`NwicRiverLevelAdapter`). |
| **IIT Delhi HydroSense Lab** | India Flood Inventory (IFI v3.0) | `PRIMARY_HISTORICAL` | `flood_observations`, `flood_events`, ML Training Ground Truth | Unique Event ID (`UEI`), Start Date, End Date, Duration, Main Cause, Affected Districts, LGD District Codes, Fatalities, Damage | 494 documented flood events across Karnataka districts | 1967–2023 (56 continuous years) | Event-driven historical records | Days, counts, LGD codes | IIT Delhi GitHub / Zenodo DOI `10.5281/zenodo.10892285` | Historical archive | Open GitHub / Zenodo CSV (No credentials required) | Resolution is at the District level, not taluk/locality level. Captures severe/damaging floods; mild localized street waterlogging unrecorded. | Build historical flood event loader and label generator at District × Day resolution (`IfiFloodEventLoader`). |
| **KSRSAC / KGIS** | Karnataka Administrative Boundaries | `PRIMARY_OPERATIONAL` | `states`, `districts`, `taluks`, `localities` | State, 31 District polygons, ~240 Taluk polygons, Hobli polygons | Karnataka statewide | Current gazetted administrative boundaries | Static / Gazetted | Polygon geometries (EPSG:4326) | KSRSAC gazetted spatial data | Static | Web Portal (Direct automated script download unstable) | Automated headless downloads blocked by IIS portal instability (HTTP 404/403). Requires manual/batch acquisition. | Ingest verified offline KSRSAC shapefiles; use verified Datameet Census 2011 WGS84 shapefiles as secondary validation (`GisBoundaryLoader`). |
| **Datameet** | Maps Repository (`Census_2011/2011_Dist`) | `SECONDARY_REFERENCE` | `districts`, `taluks` | Karnataka district and taluk boundary polygons | Karnataka statewide | 2011 Census baseline + community updates | Static | Polygon geometries (EPSG:4326) | GitHub `datameet/maps` repository | Static | Open GitHub raw download | Community-maintained; based on 2011 census boundaries (pre-dates 2021 Vijayanagara district split from Ballari). | Retain as secondary geometric reference and local testing fallback. |
| **Ministry of Panchayati Raj** | Local Government Directory (LGD) | `SUPPORTING_GEOGRAPHIC` | `states`, `districts`, `taluks` (Normalization keys) | State LGD Code (`29`), District LGD Codes (31 districts), Sub-district/Taluk LGD Codes | All administrative units in Karnataka | Live authoritative registry | Reference | Numeric codes, official English/Kannada names | `lgdirectory.gov.in` official directory | Authoritative current standard | Open CSV directory export | Web service API requires formal departmental application; CSV directory export is public. | Ingest LGD code directory as master normalization table in database (`LgdCodeDirectoryLoader`). |
| **ESA / Airbus / DLR** | Copernicus DEM GLO-30 | `PRIMARY_HISTORICAL` / `SUPPORTING_GEOGRAPHIC` | `terrain_datasets`, Feature Store (Elevation, Slope) | Elevation above sea level, derived topographic slope, aspect, relief ratio | Karnataka statewide (100% coverage, tiles `N11`–`N18`, `E074`–`E078`) | 2011–2015 acquisition (v2021 release) | Static baseline | Elevation in metres (`_m`), Slope in degrees (`_deg`) | AWS Open Data `s3://copernicus-dem-30m` COG | Static high-accuracy baseline | Open AWS S3 / HTTPS (No credentials required) | Digital Surface Model (DSM) includes canopy heights; vastly superior vertical accuracy (<2m) to 2000 SRTM. | Build terrain feature extractor to compute district/taluk zonal elevation and slope (`CopernicusDemExtractor`). |
| **OpenStreetMap** | Overpass API / Geofabrik Karnataka Extract | `SUPPORTING_GEOGRAPHIC` | `emergency_facilities` (`hospital`, `fire_station`, `police_station`) | Hospital, fire station, and police station point coordinates, facility names, district address tags | Karnataka statewide | Continuously updated community data | Dynamic | Decimal degrees WGS84 (`EPSG:4326`) | OpenStreetMap contributors (ODbL) | Fresh (Daily community updates) | Open HTTP Overpass QL (Requires custom User-Agent) | **CRITICAL: OSM places tagged `shelter` are NOT official flood evacuation shelters.** OSM is restricted to hospital, fire, and police facilities. | Build emergency facility geographic loader for hospitals/fire stations (`OsmEmergencyFacilityLoader`). |
| **Copernicus CEMS** | GloFAS River Discharge (`cems-glofas-forecast`) | `CREDENTIAL_BLOCKED` | `river_forecasts`, `river_observations` | Gridded 24-hour river discharge forecast (m³/s), return-period exceedance | Karnataka major river channels (0.05° grid) | 1979–present (reanalysis) + 30-day forecast | Daily | `_m3s` | Copernicus CDS API | Fresh (Daily run) | Credential-blocked (Requires `~/.cdsapirc` token & license acceptance) | Modern CDS migration requires personal token; unauthenticated calls return 404/403. Model-based, not in-situ gauge. | Document configuration instructions; defer integration until credentials are provided. Exclude from Phase 2 blocker list. |
| **IMD** | API Management Platform (`api.imd.gov.in`) | `CREDENTIAL_BLOCKED` | `weather_observations`, `weather_forecasts` | Official IMD nowcasts, city forecasts, heavy rainfall warnings | Karnataka meteorological subdivisions / districts | Real-time & 7-day forecast | Sub-daily | `_mm`, `_c`, `_mps` | IMD official gateway | Fresh | Credential-blocked (Requires JWT token + Static Public IP) | Requires institutional government registration and server static public IP whitelisting. | Defer until static production IP and credentials are provisioned. Open-Meteo serves as operational primary. |
| **KSDMA / DDMAs** | District Disaster Management Plans (DDMP) | `PRIMARY_HISTORICAL` (Manual PDF Extraction) | `emergency_facilities` (`facility_type="shelter"`) | Designated flood relief centers, cyclone shelters, school/community hall shelters, designated capacities | Flood-prone districts (Belagavi, Bagalkote, Kodagu, Dakshina Kannada, Udupi) | Annual disaster management editions | Annual / Episodic | Persons (capacity), address, coordinates | Official published DDMP PDF annexures | Semi-static | Public PDF documents (Manual extraction required) | No machine-readable API exists; requires geocoding and manual curation from official PDF tables; live occupancy is non-existent. | Curate verified official relief shelters from DDMP PDF tables into a versioned seed file (`data/raw/shelters/verified_karnataka_ddmp_shelters.csv`). |
| **NDMA / NIDM** | India Disaster Resource Network (IDRN) | `UNAVAILABLE` | N/A | Disaster equipment, relief warehouse inventories, emergency personnel | Karnataka districts | Real-time administrative portal | Continuous | Varied | Ministry of Home Affairs / NIDM | Fresh | Blocked / Unavailable (Restricted to DC/DM government logins) | Inaccessible to public applications and open APIs. | Do NOT attempt access; record as unavailable. |
| **Karnataka WRD** | Live Dam Release Webhook | `UNAVAILABLE` | N/A | Sub-hourly automated spillway release telemetry | Intra-state dams | Real-time | Continuous | Cusecs | Water Resources Dept | Fresh | Non-existent as an open automated API | No webhook or streaming API published. Data is posted to HTML web tables and daily bulletins. | Ingest daily reservoir bulletins from NWIC and KSNDMC. Mark intraday telemetry freshness honestly. |

---

## Source Evaluations

### A. Open-Meteo
- **Assigned Role**: `PRIMARY_OPERATIONAL`.
- **Justification**: Experimentally verified with HTTP 200 on Karnataka coordinates. Delivers current weather, 24-hour hourly history, and 7-day numerical weather forecasts for all required variables (`precipitation`, `rain`, `temperature_2m`, `relative_humidity_2m`, `wind_speed_10m`, `surface_pressure`). Supports SI units (`wind_speed_unit=ms`) matching `DATA_CONTRACT.md`. Fully open, no authentication required for standard volume.
- **Limitations**: Data represents numerical weather prediction model output (ECMWF IFS, GFS, DWD ICON) and ERA5 reanalysis, not physical in-situ rain gauges. Ingestion records must store `source="open_meteo"` and be classified as `MODEL_OUTPUT` or `DERIVED_FROM_REAL`, never presented as direct ground-station observations.

### B. NASA POWER
- **Assigned Role**: `SECONDARY_REFERENCE`.
- **Justification**: Experimentally verified with HTTP 200. Delivers daily precipitation, temperature, humidity, and wind speed. However, its 0.5° spatial grid (~55 km) is coarse, and its 2-to-3 day publication lag makes it unsuitable as an operational zero-day early warning trigger.
- **Operational Use**: Dedicated to retrospective feature validation, climatological baselines, and cross-checking Open-Meteo anomalies. Missing values are encoded as `-999.0` and must be explicitly converted to `NULL`.

### C. NWIC / Karnataka Reservoir Telemetry
- **Assigned Role**: `PRIMARY_HISTORICAL` (with ongoing daily batch ingestion).
- **Justification**: Empirical range testing verified `karnataka_man_reservoir_data.csv` (16.4 MB) updated on 2026-09-17, containing continuous daily records from 1990 to 2026 for major Karnataka reservoirs. Includes water level, storage, inflow, and outflow.
- **Conversion Requirement**: Must strictly apply the mathematical conversion contracts:
  - Level: $\text{Level}_{\text{metres}} = \text{Level}_{\text{feet}} \times 0.3048$
  - Storage: $\text{Storage}_{\text{MCM}} = \text{Storage}_{\text{TMC}} \times 28.3168$
  - Inflow / Outflow: $\text{Discharge}_{\text{m}^3/\text{s}} = \text{Flow}_{\text{cusecs}} \times 0.0283168$

### D. NWIC / CWC River Gauge Water Level
- **Assigned Role**: `PRIMARY_OPERATIONAL`.
- **Justification**: Empirical testing verified `rwl_manual_hr_cwc_009_2026_2030.csv` covering the Cauvery basin (and equivalent Krishna basin tranches) containing in-situ river gauge stations with exact station names (`AKKIHEBBAL`), LGD state code `29`, LGD district code `544`, river name (`Cauvery`), tributary (`Hemavathi`), latitude/longitude, and water level in metres.
- **Limitations**: Computed river discharge (`m3s`) is not available at all stations. The ingestion adapter must ingest `water_level_m` as the primary observed variable and set missing discharge to `NULL` (`missing ≠ zero`).

### E. India Flood Inventory (IFI v3.0)
- **Assigned Role**: `PRIMARY_HISTORICAL` (Ground Truth for ML).
- **Justification**: Verified from official IIT Delhi HydroSense Lab repository (`v3.0/India_Flood_Inventory_v3.csv`). Analysis confirmed **494 documented flood event records for Karnataka** spanning 1969 to 2023. Contains start/end dates, duration, affected district names, LGD district codes, causes, fatalities, and extent of damage.
- **Critical Policy**: IFI provides ground-truth flood observations at the **District** level. It does **not** provide continuous taluk-level or locality-level flood labels. ML models must be trained with District × Day (or District × multi-day window) target definitions. Taluk-level flood labels must **never** be fabricated.

### F. KGIS / KSRSAC Administrative Boundaries
- **Assigned Role**: `PRIMARY_OPERATIONAL`.
- **Justification**: KSRSAC is the sole statutory authority for Karnataka administrative boundaries (State, 31 Districts, ~240 Taluks, Hoblis).
- **Operational Reality**: Direct automated scraping or headless curl requests against legacy KGIS download links frequently fail with HTTP 404/403 due to portal reconfigurations. Ingestion must proceed via curated offline shapefiles acquired from official KSRSAC releases. Datameet Census 2011 boundaries (verified in EPSG:4326) serve as a secondary geometric validation reference.

### G. Local Government Directory (LGD)
- **Assigned Role**: `SUPPORTING_GEOGRAPHIC`.
- **Justification**: LGD codes are verified as the universal normalization keys present in both CWC hydrological telemetry (`State LGD Code: 29`, `District LGD Code: 544`) and IFI historical flood events (`State_Codes: 29`, `District_LGD_Codes`). The complete directory of Karnataka administrative codes will be ingested as a reference table to enforce referential integrity across heterogeneous datasets.

### H. Copernicus DEM GLO-30
- **Assigned Role**: `PRIMARY_HISTORICAL` / `SUPPORTING_GEOGRAPHIC`.
- **Justification**: Verified on AWS Open Data (`s3://copernicus-dem-30m/`). Test range request on South Karnataka tile (`N12_E076`) confirmed Cloud Optimized GeoTIFF structure, EPSG:4326 horizontal CRS, EGM2008 vertical datum, and 30m resolution with zero authentication requirements.
- **Usage**: Provides baseline elevation rasters from which zonal mean elevation, minimum elevation, slope (degrees), and topographic wetness indicators will be calculated in PostGIS/GeoPandas.

### I. OpenStreetMap / Overpass API
- **Assigned Role**: `SUPPORTING_GEOGRAPHIC`.
- **Justification**: Overpass QL query verified with HTTP 200 (using custom User-Agent). Accurately retrieves point geometries and names for hospitals, clinics, fire stations, and police stations in Karnataka.
- **Absolute Rule**: OSM is **not** an authoritative source for flood evacuation shelters. An OSM node tagged `amenity=shelter` or `building=school` must **never** be imported into FloodPulse as a verified flood evacuation shelter. OSM is strictly confined to general emergency facilities (`hospital`, `fire_station`, `police_station`).

### J. GloFAS via Copernicus CDS
- **Assigned Role**: `CREDENTIAL_BLOCKED`.
- **Justification**: Tested unauthenticated against the modern Copernicus Climate Data Store; access returned HTTP 404/403. Requires user registration, accepting terms of use on the CDS web portal, and placing an API token in `~/.cdsapirc`.
- **Policy**: Excluded from Phase 2 blocking dependencies. If credentials are provided in a later phase, GloFAS will serve as a secondary hydrological forecast source (`RiverForecast`).

---

## Shelter & Evacuation Data Policy

The inspection across all Phase 1 tasks confirms that **no open, machine-readable, authoritative live shelter API or database exists** for Karnataka.

### Strict Shelter Ingestion Strategy for Phase 2

1. **No Fabricated Shelters**: Under no circumstances will synthetic shelters, mock capacities, or arbitrary Google Maps / OSM places be imported as official evacuation shelters.
2. **Official DDMP PDF Extraction**:
   - For high-risk flood districts (Belagavi, Bagalkote, Kodagu, Dakshina Kannada, Udupi), official designated flood relief centers and cyclone shelters will be extracted directly from published District Disaster Management Plan (DDMP) PDF annexures.
   - Each extracted shelter will be verified, geocoded against official village/town centroids, and stored in a versioned seed dataset (`data/raw/shelters/verified_karnataka_ddmp_shelters.csv`) with full provenance metadata (District DDMP edition, page number, nodal officer contact).
3. **OSM Healthcare / Emergency Facilities**:
   - Hospitals, Community Health Centres (CHCs), and fire stations retrieved from OSM / ABDM will be ingested into `emergency_facilities` with explicit types (`facility_type="hospital"`, `facility_type="fire_station"`), retaining `source="openstreetmap"`. They will **never** be labeled as evacuation shelters.
4. **Mandatory Null Occupancy**:
   - Because real-time shelter occupancy telemetry is non-existent, `shelter_occupancy` and `available_capacity` must remain explicitly `NULL` ("unknown").
   - In the API and frontend, unknown occupancy must be displayed honestly as `"Occupancy: Unknown"` and must **never** be assumed to indicate full availability.
