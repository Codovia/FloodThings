# FloodPulse Data Source Inventory

## Research Scope

Karnataka-focused real-data flood intelligence and early-warning system. This inventory compiles verified, authoritative sources across meteorology, hydrology, reservoir monitoring, historical flood occurrences, administrative boundaries, terrain, land cover, surface water, emergency facilities/shelters, and road routing to support FloodPulse without resorting to synthetic or fabricated environmental data.

---

## Source Selection Principles

- **Real data only**: No fabricated daily observations, no synthetic rainfall profiles, and no invented reservoir numbers.
- **Prefer authoritative sources**: Prioritize Tier 1 government agencies (IMD, CWC, KSNDMC, KSRSAC, Survey of India) and Tier 2 established scientific services (ECMWF/Copernicus, NASA, USGS, IIT Delhi HydroSense Lab).
- **Preserve provenance**: Every source must provide clear chain of custody, attribution terms, and verifiable publication channels.
- **No fabricated environmental data**: Environmental observations must be traceable to physical sensors or calibrated reanalysis/forecast models.
- **No unsupported assumptions**: If an API does not exist or requires unobtained credentials, record it honestly as `UNAVAILABLE` or `PARTIALLY_VERIFIED` with credentials blocked. Missing data remains explicitly `NULL`.

---

## Source Summary

| ID | Source | Authority Tier | Category | Karnataka Coverage | API | Historical | Status |
|---|---|---|---|---|---|---|---|
| SRC-MET-01 | IMD API Management Platform | Tier 1 (Govt) | Meteorology / Forecast | Statewide (District/City) | YES (Token/IP) | Limited (Current/Forecast) | PARTIALLY_VERIFIED |
| SRC-MET-02 | IMD Pune Climate Data Services Portal | Tier 1 (Govt) | Meteorology / Gridded | Statewide (0.25° grid) | NO (HTTP direct/`imdlib`) | Extensive (1901–present) | VERIFIED |
| SRC-MET-03 | NASA POWER API | Tier 2 (Scientific) | Meteorology / Solar | Statewide (0.5° grid) | YES (REST open) | Extensive (1981–present) | VERIFIED |
| SRC-MET-04 | Open-Meteo Weather API | Tier 2 (Scientific) | Meteorology / Forecast | Statewide (Point/Grid) | YES (REST open) | Extensive (1940–present) | VERIFIED |
| SRC-MET-05 | ECMWF ERA5-Land (Copernicus CDS) | Tier 2 (Scientific) | Meteorology / Reanalysis | Statewide (0.1° grid) | YES (`cdsapi` token) | Extensive (1950–present) | VERIFIED |
| SRC-RNF-01 | IMD Gridded Daily Rainfall (0.25°) | Tier 1 (Govt) | Rainfall (Observed) | Statewide (0.25° grid) | NO (Binary/NetCDF via `imdlib`) | Extensive (1901–2023+) | VERIFIED |
| SRC-RNF-02 | KSNDMC Telemetric Rain Gauge Network | Tier 1 (Govt) | Rainfall (Observed) | Statewide (~6,000 TRG stations) | NO direct (OpenCity CKAN API) | Extensive (2010–present) | PARTIALLY_VERIFIED |
| SRC-RNF-03 | CHIRPS Daily Precipitation (UCSB/USGS) | Tier 2 (Scientific) | Rainfall (Satellite+Gauges) | Statewide (0.05° ~5km) | YES (HTTP/FTP open) | Extensive (1981–present) | VERIFIED |
| SRC-RNF-04 | GPM IMERG (NASA Earthdata) | Tier 2 (Scientific) | Rainfall (Satellite NRT) | Statewide (0.1° half-hourly) | YES (OPeNDAP/HTTPS auth) | Extensive (2000–present) | VERIFIED |
| SRC-HYD-01 | CWC / NWIC National Water Data Portal | Tier 1 (Govt) | River Hydrology | Major Karnataka Rivers (Cauvery, Krishna) | YES (NWIC API catalog / CSV) | Moderate (Station telemetry) | VERIFIED |
| SRC-HYD-02 | India-WRIS River Monitoring Portal | Tier 1 (Govt) | River Hydrology | Major Basins (Station telemetry) | NO public REST (WebGIS/Exports) | Moderate (Daily/Hourly) | PARTIALLY_VERIFIED |
| SRC-HYD-03 | GloFAS River Discharge (Copernicus CEMS) | Tier 2 (Scientific) | River Hydrology / Forecast | Statewide (0.05° grid) | YES (`cdsapi` token) | Extensive (1979–present) | VERIFIED |
| SRC-HYD-04 | Karnataka Water Resources Dept (WRD) | Tier 1 (Govt) | River Hydrology | State river gauge telemetry | NO public API (Web tables/PDFs) | Moderate (Internal/Reports) | PARTIALLY_VERIFIED |
| SRC-RES-01 | NWIC Karnataka Reservoir Dataset | Tier 1 (Govt) | Reservoir Observations | Major dams (KRS, Almatti, etc.) | YES (Direct CSV download/API) | Long-term (1990–2026) | VERIFIED |
| SRC-RES-02 | KSNDMC Major Reservoirs Daily Bulletin | Tier 1 (Govt) | Reservoir Observations | 14+ Major Karnataka Reservoirs | NO public REST (Daily PDF/Dashboard) | Moderate (Archival PDFs/OpenCity) | PARTIALLY_VERIFIED |
| SRC-RES-03 | CWC Weekly Reservoir Bulletin (India-WRIS) | Tier 1 (Govt) | Reservoir Observations | Key monitored reservoirs | NO public REST (Weekly PDF/Portal) | Moderate (Multi-year) | PARTIALLY_VERIFIED |
| SRC-RES-04 | Karnataka WRD Dam Telemetry Portal | Tier 1 (Govt) | Reservoir Observations | Basin project dams | NO public REST (Web HTML) | Current only | PARTIALLY_VERIFIED |
| SRC-FLD-01 | India Flood Inventory (IFI - IIT Delhi) | Tier 1/2 (Scientific) | Historical Flood Events | Statewide (District-level) | NO (CSV/Zenodo open) | Extensive (1967–2023) | VERIFIED |
| SRC-FLD-02 | Dartmouth Flood Observatory (DFO) | Tier 2 (Scientific) | Historical Flood Events | Major flood events in Karnataka | NO (Web GIS/Shapefile open) | Long-term (1985–present) | VERIFIED |
| SRC-FLD-03 | Copernicus EMS Rapid Mapping | Tier 2 (Scientific) | Satellite Flood Extent | Severe event activations | YES (Open vector download) | Event-driven (2012–present) | PARTIALLY_VERIFIED |
| SRC-FLD-04 | NRSC Bhuvan Flood Hazard Atlas & NDEM | Tier 1 (Govt) | Flood Hazard Zoning | Flood-prone districts (Belagavi, etc.) | NO open REST (Bhuvan WebGIS) | Multi-year cumulative | PARTIALLY_VERIFIED |
| SRC-FLD-05 | EM-DAT Disaster Database (CRED) | Tier 2 (Scientific) | Historical Disaster Events | State-level aggregates | YES (API requires license) | Long-term (1900–present) | PARTIALLY_VERIFIED |
| SRC-ADM-01 | KGIS / KSRSAC Administrative Boundaries | Tier 1 (Govt) | Administrative Geography | Statewide (State, District, Taluk, Hobli) | NO direct (Portal ZIP/WMS) | Official current releases | VERIFIED |
| SRC-ADM-02 | Local Government Directory (LGD - MoPR) | Tier 1 (Govt) | Administrative Geography | Statewide (31 Districts, Taluks, GPs) | YES (Gated) / CSV open | Authoritative current codes | VERIFIED |
| SRC-ADM-03 | Survey of India Open Series / Bharat Maps | Tier 1 (Govt) | Administrative Geography | Statewide | NO public REST (Portal download) | Official reference | PARTIALLY_VERIFIED |
| SRC-ADM-04 | Datameet Karnataka Maps (Open Community) | Tier 3 (Community) | Administrative Geography | Statewide (Districts, Taluks) | NO (GitHub GeoJSON/TopoJSON) | Census 2011 + Updates | VERIFIED |
| SRC-DEM-01 | Copernicus DEM GLO-30 (AWS Open Data) | Tier 2 (Scientific) | Terrain / Elevation | Statewide (30m resolution) | YES (AWS S3 open CLI/HTTP) | 2011–2015 acquisition (v2021) | VERIFIED |
| SRC-DEM-02 | SRTM 30m (SRTMGL1 - NASA/USGS) | Tier 2 (Scientific) | Terrain / Elevation | Statewide (30m resolution) | YES (OpenTopography API) | Feb 2000 acquisition | VERIFIED |
| SRC-DEM-03 | CartoDEM 30m (ISRO NRSC / Bhuvan) | Tier 1 (Govt) | Terrain / Elevation | Statewide (30m resolution) | NO open API (Bhuvan login required) | Cartosat-1 derived | PARTIALLY_VERIFIED |
| SRC-DEM-04 | ALOS AW3D30 (JAXA) | Tier 2 (Scientific) | Terrain / Elevation | Statewide (30m resolution) | NO public REST (FTP/Registration) | 2006–2011 PRISM | PARTIALLY_VERIFIED |
| SRC-LNC-01 | ESA WorldCover 10m | Tier 2 (Scientific) | Land Cover Classification | Statewide (10m resolution) | YES (AWS S3 open COG) | 2020, 2021 epochs | VERIFIED |
| SRC-LNC-02 | ESRI 10m Sentinel-2 Land Cover | Tier 2 (Scientific) | Land Cover Classification | Statewide (10m resolution) | YES (AWS Open Data COG) | Annual time series (2017–2023) | VERIFIED |
| SRC-LNC-03 | NRSC Bhuvan LULC (1:50k / 1:250k) | Tier 1 (Govt) | Land Cover Classification | Statewide | NO public REST (Bhuvan WebGIS) | Multi-year cyclic epochs | PARTIALLY_VERIFIED |
| SRC-WAT-01 | JRC Global Surface Water (GSW) | Tier 2 (Scientific) | Water Bodies & Occurrence | Statewide (30m resolution) | YES (Direct tile HTTP/GEE) | Extensive (1984–2021) | VERIFIED |
| SRC-WAT-02 | HydroSHEDS / HydroRIVERS / HydroLAKES | Tier 2 (Scientific) | River Network & Lakes | Statewide (Vector lines/polygons) | NO (Direct shapefile download) | Global baseline | VERIFIED |
| SRC-WAT-03 | India-WRIS Water Bodies Layer | Tier 1 (Govt) | Water Bodies (Ponds, Tanks) | Statewide (1st Water Bodies Census) | NO public REST (WebGIS view) | 2023 Census release | PARTIALLY_VERIFIED |
| SRC-WAT-04 | OpenStreetMap Water Features | Tier 3 (Community) | Waterways & Reservoirs | Statewide (Vector features) | YES (Overpass API / Geofabrik) | Continuously updated | VERIFIED |
| SRC-EMG-01 | Karnataka SDMA / DDMA Relief Plans (DDMP) | Tier 1 (Govt) | Emergency Facilities / Shelters | District-specific (Flood relief camps) | NO (Static PDF Annexures) | Annual disaster plans | PARTIALLY_VERIFIED |
| SRC-EMG-02 | India Disaster Resource Network (IDRN) | Tier 1 (Govt) | Emergency Resources / Shelters | District inventory across Karnataka | NO public API (Restricted DC login) | Official government register | UNAVAILABLE |
| SRC-EMG-03 | ABDM Health Facility Registry (HFR) | Tier 1 (Govt) | Hospitals / Healthcare Facilities | Statewide (Hospitals, CHCs, PHCs) | YES (Gated / Developer portal) | Live national registry | PARTIALLY_VERIFIED |
| SRC-EMG-04 | OpenStreetMap Amenities (Health, Fire, Police) | Tier 3 (Community) | Emergency Facilities | Statewide (Hospitals, Stations) | YES (Overpass API / Geofabrik) | Continuously updated | VERIFIED |
| SRC-ROU-01 | OSRM (Open Source Routing Machine) | Tier 3 (Engine/OSM) | Road Routing & Navigation | Statewide (Karnataka OSM extract) | YES (Self-hostable HTTP / Demo) | Current OSM road network | VERIFIED |
| SRC-ROU-02 | GraphHopper Routing Engine | Tier 3 (Engine/OSM) | Road Routing & Navigation | Statewide (Karnataka OSM extract) | YES (Self-hostable HTTP / SaaS) | Current OSM road network | VERIFIED |
| SRC-ROU-03 | OpenRouteService (HeiGIT) | Tier 2/3 (Engine/OSM)| Road Routing & Isochrones | Statewide (OSM data) | YES (API key / Self-hostable) | Current OSM road network | VERIFIED |

---

## 1. Meteorological Sources

### Source: IMD API Management Platform
- **Authority**: India Meteorological Department (IMD), Ministry of Earth Sciences, Govt of India
- **Official URL**: `https://api.imd.gov.in/public/index.php`
- **Variables**: City weather forecast (7-day), district-wise nowcasts, weather warnings, heavy rainfall warnings, station observations, subdivision bulletins.
- **Coverage**: All-India; covers all 31 districts of Karnataka.
- **Historical depth**: Real-time current observations and short-term forecasts (nowcast up to 3 hours; forecast up to 7 days). No multi-decadal historical archive via this API.
- **Resolution**: Station-level and district-level aggregations.
- **API**: YES. Documented on `https://api.imd.gov.in/public/api_reference.html`.
- **Authentication**: Required. Registration on portal, API Key + JWT Bearer Token. Server static public IP binding required.
- **Rate limits**: Controlled per registered key. Client caching explicitly mandated.
- **License/access**: Official Government of India Open Data / IMD terms of service. Free for registered governmental and authorized applications.
- **FloodPulse mapping**: `WeatherObservation`, `WeatherForecast`.
- **Limitations**: Requires portal registration and a static public IP address for token issuance. Not currently open to anonymous development machines.
- **Status**: `PARTIALLY_VERIFIED` (API structure and documentation verified; credentials and IP binding unobtained).

### Source: IMD Pune Climate Data Services Portal
- **Authority**: National Climate Reference Centre, IMD Pune, Govt of India
- **Official URL**: `https://cdsp.imdpune.gov.in/home_gridded_data.php`
- **Variables**: Daily gridded rainfall (0.25° x 0.25°), daily maximum temperature (0.5° and 1.0°), daily minimum temperature (0.5° and 1.0°).
- **Coverage**: All-India landmass (6.5°N–38.5°N, 66.5°E–100.0°E); covers entire Karnataka state.
- **Historical depth**: 1901 to 2023+ (over 120 years of daily gridded data).
- **Resolution**: 0.25° (~27 km) for rainfall; 0.5° for temperature.
- **API**: NO direct REST API. Direct file download (binary `.grd`) or programmatic automated retrieval using open-source Python wrapper `imdlib`.
- **Authentication**: None required for direct web download or `imdlib` retrieval.
- **Rate limits**: Web server connection limits; batch downloads should be staggered.
- **License/access**: Free for educational, research, and non-commercial public interest with mandatory IMD attribution.
- **FloodPulse mapping**: `WeatherObservation`, `RainfallObservation`.
- **Limitations**: Binary format requires decoding; spatial resolution of 0.25° is coarse for local taluk-level microclimates but ideal for district-level aggregation.
- **Status**: `VERIFIED`.

### Source: NASA POWER API
- **Authority**: NASA Langley Research Center (POWER Project)
- **Official URL**: `https://power.larc.nasa.gov`
- **Variables**: `PRECTOTCORR` (corrected precipitation, mm/day), `T2M` (temperature at 2m, °C), `RH2M` (relative humidity, %), `WS10M` (wind speed, m/s), `PS` (surface pressure, kPa).
- **Coverage**: Global; point-level and regional bounding box queries across Karnataka.
- **Historical depth**: 1981-01-01 to near-present (2–3 days latency).
- **Resolution**: 0.5° x 0.5° (~55 km) grid (MERRA-2 reanalysis / GEOS-FP).
- **API**: YES. Endpoint: `https://power.larc.nasa.gov/api/temporal/daily/point`.
- **Authentication**: None required. Open public REST API.
- **Rate limits**: 30 requests/second; max 20 parameters per call.
- **License/access**: NASA Open Data Policy (public domain).
- **FloodPulse mapping**: `WeatherObservation` (supplementary / validation).
- **Limitations**: Model-derived reanalysis, not ground weather station measurements. 2–3 day publication lag prevents zero-day operational warning.
- **Status**: `VERIFIED`.

### Source: Open-Meteo Weather API
- **Authority**: Open-Meteo GmbH (incorporating DWD, ECMWF IFS, GFS, and JMA models)
- **Official URL**: `https://open-meteo.com`
- **Variables**: `temperature_2m`, `relative_humidity_2m`, `precipitation`, `rain`, `showers`, `wind_speed_10m`, `surface_pressure`, `precipitation_probability`.
- **Coverage**: Global; seamless point queries across Karnataka.
- **Historical depth**: Forecast (1–16 days ahead); Historical Archive (1940 to present via ERA5/ERA5-Land).
- **Resolution**: ~1 km to 11 km depending on underlying model blend (ECMWF 9 km, DWD ICON 2 km).
- **API**: YES. Forecast: `https://api.open-meteo.com/v1/forecast`; Archive: `https://archive-api.open-meteo.com/v1/archive`.
- **Authentication**: None required for non-commercial open tier.
- **Rate limits**: 10,000 requests/day, max 600/minute.
- **License/access**: Attribution required (CC-BY 4.0).
- **FloodPulse mapping**: `WeatherObservation`, `WeatherForecast`.
- **Limitations**: Numerical Weather Prediction (NWP) model output and reanalysis; not in-situ physical rain gauges. Must be labeled as model/reanalysis output.
- **Status**: `VERIFIED`.

### Source: ECMWF ERA5-Land (Copernicus Climate Data Store)
- **Authority**: European Centre for Medium-Range Weather Forecasts (ECMWF) / Copernicus Climate Change Service (C3S)
- **Official URL**: `https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land`
- **Variables**: Total precipitation (`tp`), 2m temperature (`2t`), volumetric soil water layers (`swvl1`, `swvl2`, `swvl3`), surface runoff (`sro`), sub-surface runoff (`ssro`).
- **Coverage**: Global land surface; full Karnataka coverage.
- **Historical depth**: 1950 to present (updated monthly with 2–3 months latency; ERA5T has 5 days latency).
- **Resolution**: 0.1° x 0.1° (~9 km).
- **API**: YES. CDS API (`cdsapi` Python client) querying `https://cds.climate.copernicus.eu/api`.
- **Authentication**: Required. Personal CDS API UID and API Key configured in `~/.cdsapirc`. User must accept terms of use on web portal first.
- **Rate limits**: Queue-based retrieval system.
- **License/access**: Copernicus open access license (free for commercial and non-commercial use with citation).
- **FloodPulse mapping**: `WeatherObservation`, `FeatureSnapshot` (soil moisture, runoff features).
- **Limitations**: Latency makes it an offline ML training/feature engineering dataset rather than a real-time warning source.
- **Status**: `VERIFIED`.

---

## 2. Rainfall Sources

### Source: IMD Gridded Daily Rainfall (0.25° x 0.25°)
- **Authority**: India Meteorological Department (IMD), Pune
- **Official URL**: `https://cdsp.imdpune.gov.in/home_gridded_data.php`
- **Variables**: Daily accumulated rainfall in millimetres (`rain_mm`).
- **Coverage**: All-India (0.25° x 0.25° regular grid); Karnataka state boundary spans ~140 grid points.
- **Historical depth**: 1901 to 2023+.
- **Resolution**: 0.25° (~27 km).
- **API**: Direct binary download or Python `imdlib.get_data("rain", start_yr, end_yr, dir)`.
- **Authentication**: None for public portal files.
- **Rate limits**: None specified; respect server bandwidth.
- **License/access**: Free for research/public safety with attribution.
- **FloodPulse mapping**: `RainfallObservation`.
- **Limitations**: Gridded interpolation from station records; interpolation error increases in mountainous Western Ghats (Kodagu/Chikkamagaluru) where gauge density varies.
- **Status**: `VERIFIED`.

### Source: KSNDMC Telemetric Rain Gauge Network (via OpenCity CKAN)
- **Authority**: Karnataka State Natural Disaster Monitoring Centre (KSNDMC), Govt of Karnataka / OpenCity Portal
- **Official URL**: `https://www.ksndmc.org` / `https://data.opencity.in`
- **Variables**: Daily, monthly, and annual rainfall (mm) at Hobli and Gram Panchayat levels, rain gauge station coordinates, station status.
- **Coverage**: Karnataka statewide (~6,000+ telemetric rain gauges; highest gauge density in India).
- **Historical depth**: ~2010 to 2023 across various published reports on OpenCity.
- **Resolution**: Gram Panchayat / Hobli level (point coordinates and administrative unit averages).
- **API**: OpenCity CKAN Action API (`https://data.opencity.in/api/3/action/package_search?q=KSNDMC`).
- **Authentication**: None for public CKAN data search and download. Direct KSNDMC internal API requires departmental credentials.
- **Rate limits**: Standard CKAN web API limits.
- **License/access**: Public government reports published under National Data Sharing and Accessibility Policy (NDSAP).
- **FloodPulse mapping**: `RainfallObservation`.
- **Limitations**: KSNDMC does not host a direct public authenticated REST API for real-time automated streaming to third parties. Live data is published on web dashboards and daily PDF bulletins. Structured historical data must be extracted via OpenCity datasets.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: CHIRPS Daily Precipitation (Climate Hazards Center)
- **Authority**: University of California Santa Barbara (UCSB) / USGS Earth Resources Observation and Science (EROS)
- **Official URL**: `https://www.chc.ucsb.edu/data/chirps`
- **Variables**: Daily rainfall (`precip`, mm).
- **Coverage**: 50°S–50°N global quasi-global; full Karnataka coverage.
- **Historical depth**: 1981 to near-present (preliminary daily available with 1–2 days latency).
- **Resolution**: 0.05° x 0.05° (~5.3 km).
- **API**: HTTP/FTP directory downloads (`https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/netcdf/p05/`) and Google Earth Engine image collection.
- **Authentication**: None required. Open access.
- **Rate limits**: Standard web download bandwidth.
- **License/access**: Public domain / Open access (USGS/UCSB).
- **FloodPulse mapping**: `RainfallObservation` (high-resolution spatial baseline).
- **Limitations**: Blended satellite-station product; calibration relies on available reporting stations.
- **Status**: `VERIFIED`.

### Source: GPM IMERG (Global Precipitation Measurement)
- **Authority**: NASA Goddard Space Flight Center / JAXA
- **Official URL**: `https://gpm.nasa.gov/data/imerg`
- **Variables**: Precipitation rate (`precipitationCal`, mm/hr), accumulation.
- **Coverage**: Global (60°N–60°S); full Karnataka coverage.
- **Historical depth**: 2000 to present (Early run: 4 hours latency; Late run: 14 hours; Final calibrated run: 3.5 months).
- **Resolution**: 0.1° x 0.1° (~10 km), half-hourly and daily.
- **API**: NASA Earthdata GES DISC (HTTPS / OPeNDAP).
- **Authentication**: Required. Free NASA Earthdata login account.
- **Rate limits**: Standard NASA Earthdata connection limits.
- **License/access**: NASA Open Data Policy (unrestricted).
- **FloodPulse mapping**: `RainfallObservation` (near-real-time validation).
- **Limitations**: Requires Earthdata token authentication; file formats are HDF5/NetCDF4 requiring spatial subsetting.
- **Status**: `VERIFIED`.

---

## 3. River/Hydrology Sources

### Source: CWC / NWIC National Water Data Portal
- **Authority**: Central Water Commission (CWC) / National Water Informatics Centre (NWIC), Ministry of Jal Shakti, Govt of India
- **Official URL**: `https://nwdp.nwic.gov.in`
- **Variables**: River water level (m), danger level (m), warning level (m), discharge (m³/s), station location, river name, basin name.
- **Coverage**: Monitored CWC hydrological stations across Karnataka (Cauvery, Krishna, Tungabhadra, Ghataprabha, Malaprabha, Netravati basins).
- **Historical depth**: Multi-year daily and hourly records (telemetry and manual).
- **Resolution**: In-situ river gauge stations.
- **API**: YES. Available via NWIC API catalog on `https://nwdp.nwic.gov.in`. Datasets also downloadable as CSV.
- **Authentication**: Open access for public datasets; registration on NWIC portal for developer key catalog.
- **Rate limits**: Managed by NWIC gateway.
- **License/access**: Government of India Open Data / NDSAP.
- **FloodPulse mapping**: `RiverStation`, `RiverObservation`.
- **Limitations**: Discharge measurements are often restricted or withheld during interstate disputes or flood peaks; water levels are more reliably reported than computed discharge.
- **Status**: `VERIFIED`.

### Source: India-WRIS River Monitoring
- **Authority**: National Water Informatics Centre (NWIC) / Central Water Commission
- **Official URL**: `https://indiawris.gov.in/wris/`
- **Variables**: Surface water level, river discharge, basin/sub-basin geometries, telemetry timeseries.
- **Coverage**: Pan-India, including all major Karnataka river gauge stations.
- **Historical depth**: Daily and hourly timeseries across operational stations.
- **Resolution**: Monitoring station point locations.
- **API**: WebGIS backend API (Swagger UI documented at NWIC internal developer pages). Public access primarily through portal export interfaces.
- **Authentication**: Captcha / session tokens on portal; full REST API requires NWIC registration.
- **Rate limits**: Web interface rate-limited.
- **License/access**: Government of India public data.
- **FloodPulse mapping**: `RiverBasin`, `SubBasin`, `River`, `RiverStation`, `RiverObservation`.
- **Limitations**: Portal UI undergoes periodic structural revamps; automated scraping without official API credentials breaks easily.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: GloFAS River Discharge (Copernicus CEMS)
- **Authority**: Copernicus Emergency Management Service (CEMS) / ECMWF
- **Official URL**: `https://www.globalfloods.eu`
- **Variables**: `river_discharge_in_the_last_24_hours` (m³/s), flood hazard alert thresholds (2-year, 5-year, 20-year return periods).
- **Coverage**: Global gridded drainage network; covers major river channels in Karnataka (Krishna, Cauvery, Tungabhadra).
- **Historical depth**: Reanalysis (1979 to present) via `cems-glofas-historical`; forecasts (up to 30 days ahead) via `cems-glofas-forecast`.
- **Resolution**: 0.05° (~5 km) gridded LISFLOOD hydrological routing model.
- **API**: YES. Copernicus Climate Data Store API (`cdsapi` client). Endpoint: `https://cds.climate.copernicus.eu/api`.
- **Authentication**: Required. Personal CDS API token in `~/.cdsapirc` and accepted portal license agreement.
- **Rate limits**: Batch asynchronous queueing.
- **License/access**: Copernicus Open Access (free for commercial and non-commercial use with citation).
- **FloodPulse mapping**: `RiverForecast`, `RiverObservation` (model-simulated).
- **Limitations**: It is a simulated hydrological model driven by IFS/ERA5 meteorological forcing, NOT a physical gauge measurement. Small streams and urban drains are unrepresented at 0.05° grid.
- **Status**: `VERIFIED`.

### Source: Karnataka Water Resources Department (WRD)
- **Authority**: Water Resources Department, Government of Karnataka (Krishna Bhagya Jala Nigam Ltd / Cauvery Neeravari Nigama Ltd)
- **Official URL**: `https://waterresources.karnataka.gov.in`
- **Variables**: River gauge water level, river flow status, canal discharges.
- **Coverage**: Intra-state river monitoring points across Karnataka.
- **Historical depth**: Published in seasonal departmental annual reports.
- **Resolution**: Gauge station level.
- **API**: NO public automated REST API.
- **Authentication**: N/A.
- **Rate limits**: N/A.
- **License/access**: State government departmental reports.
- **FloodPulse mapping**: `RiverStation`, `RiverObservation`.
- **Limitations**: No machine-readable automated streaming interface; data is trapped in tabular HTML or scanned seasonal PDF bulletins.
- **Status**: `PARTIALLY_VERIFIED`.

---

## 4. Reservoir Sources

### Source: NWIC Karnataka Reservoir Dataset
- **Authority**: National Water Informatics Centre (NWIC), Ministry of Jal Shakti, Govt of India
- **Official URL**: `https://nwdp.nwic.gov.in`
- **Dataset Resource**: `https://nwdp.nwic.gov.in/dataset/e35dc28a-6f9c-486d-b598-87a21397018e/resource/26800982-045c-41de-821d-b1ca080a79a8/download/karnataka_man_reservoir_data.csv`
- **Variables**: Reservoir name, date, water level (m / ft), live storage (MCM / TMC), gross storage, inflow (cumecs / cusecs), outflow/release (cumecs / cusecs).
- **Coverage**: Major reservoirs in Karnataka (KRS, Kabini, Harangi, Hemavathi, Almatti, Narayanpur, Tungabhadra, Bhadra, Ghataprabha, Malaprabha, Linganamakki, Supa).
- **Historical depth**: 1990 to 2026 (daily historical records).
- **Resolution**: Dam / reservoir point entities.
- **API**: Direct authenticated/unauthenticated CSV download link on NWIC portal and CKAN-compatible dataset API.
- **Authentication**: Publicly downloadable URL; developer API catalog requires NWIC registration.
- **Rate limits**: Standard web limits.
- **License/access**: Open Government Data License - India (OGDL).
- **FloodPulse mapping**: `Reservoir`, `ReservoirObservation`.
- **Limitations**: Contains historical manual telemetry reports; real-time intraday live release data requires CWC/KSNDMC daily sync.
- **Status**: `VERIFIED`.

### Source: KSNDMC Major Reservoirs Daily Bulletin
- **Authority**: Karnataka State Natural Disaster Monitoring Centre (KSNDMC), Govt of Karnataka
- **Official URL**: `https://www.ksndmc.org`
- **Variables**: Reservoir Full Reservoir Level (FRL), Current Water Level (ft), Total Capacity (TMC), Current Storage (TMC), Inflow (cusecs), Outflow (cusecs), same-day last year comparison.
- **Coverage**: 14 major reservoirs across Cauvery and Krishna basins in Karnataka.
- **Historical depth**: Published daily during monsoon; historical archives available on OpenCity (`data.opencity.in`) and Kaggle archives.
- **Resolution**: Specific reservoir facilities.
- **API**: NO direct official public REST API. Available via daily PDF bulletins on `ksndmc.org` and mirrored datasets on OpenCity CKAN API.
- **Authentication**: None for public PDF bulletins.
- **Rate limits**: N/A.
- **License/access**: Public government disaster monitoring data.
- **FloodPulse mapping**: `ReservoirObservation`.
- **Limitations**: Requires PDF parsing or CKAN ingestion from OpenCity mirrors. No direct web-hook or streaming API.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: Central Water Commission (CWC) Major Reservoirs Bulletin
- **Authority**: Central Water Commission (CWC), Govt of India
- **Official URL**: `http://cwc.gov.in` / `https://indiawris.gov.in/wris/#/reservoir`
- **Variables**: Weekly live storage status, percentage of normal storage, FRL, capacity.
- **Coverage**: 150+ major reservoirs nationally, including 16 major reservoirs in Karnataka.
- **Historical depth**: Multi-year weekly bulletins (every Thursday).
- **Resolution**: Reservoir facility level.
- **API**: India-WRIS backend API; public access via weekly PDF bulletins and portal charts.
- **Authentication**: None for public bulletin downloads.
- **Rate limits**: N/A.
- **License/access**: Govt of India public reporting.
- **FloodPulse mapping**: `Reservoir`, `ReservoirObservation`.
- **Limitations**: Weekly temporal resolution is too coarse for real-time flash flood or rapid reservoir release warning.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: Karnataka WRD Dam Telemetry Portal
- **Authority**: Water Resources Department, Government of Karnataka
- **Official URL**: `https://waterresources.karnataka.gov.in` / Nigam portals
- **Variables**: Live reservoir levels and dam outflows (cusecs).
- **Coverage**: Key dams in Karnataka.
- **Historical depth**: Current day only on public web tables.
- **Resolution**: Dam structure.
- **API**: NO public API.
- **Authentication**: N/A.
- **Rate limits**: N/A.
- **License/access**: Public state portal display.
- **FloodPulse mapping**: `ReservoirObservation`.
- **Limitations**: Transient HTML tables with no archival access or structured export mechanism.
- **Status**: `PARTIALLY_VERIFIED`.

---

## 5. Historical Flood Sources

### Source: India Flood Inventory (IFI) — IIT Delhi HydroSense Lab
- **Authority**: HydroSense Lab, Department of Civil Engineering, Indian Institute of Technology Delhi (Dr. Manabendra Saharia)
- **Official URL**: `https://github.com/hydrosenselab/India-Flood-Inventory` / Zenodo repository (`10.5281/zenodo.10892285` / related impacts v2.0/v4.0)
- **Variables**: `UEI_ID` (Unique Event ID), `State`, `District`, `Start_Date`, `End_Date`, `Duration_Days`, `Main_Cause`, `Latitude`, `Longitude`, `Fatalities`, `Economic_Damage`, `DFSI` (District Flood Severity Index).
- **Coverage**: All-India (covers all documented flood events in Karnataka across all districts).
- **Historical depth**: 1967 to 2023 (56 continuous years of recorded events).
- **Resolution**: District-level spatial attribution with event centroid coordinates and temporal start/end dates.
- **API**: NO REST API. Distributed as analysis-ready CSV and geospatial Shapefile via GitHub and Zenodo.
- **Authentication**: None required. Open scientific repository.
- **Rate limits**: Standard GitHub / Zenodo download limits.
- **License/access**: Creative Commons Attribution 4.0 International (CC-BY 4.0).
- **FloodPulse mapping**: `FloodObservation`, `FloodEvent`. Primary ground-truth candidate for ML training target.
- **Limitations**: Spatial attribution is at the district level, not individual taluks or villages. Reports represent documented severe flood events; mild localized waterlogging may not be captured.
- **Status**: `VERIFIED`.

### Source: Dartmouth Flood Observatory (DFO)
- **Authority**: University of Colorado / CSDMS (originally Dartmouth College)
- **Official URL**: `https://floodobservatory.colorado.edu`
- **Variables**: Event ID, Country, Began, Ended, Duration, Main Cause, Severity (Class 1, 1.5, 2), Centroid coordinates, Inundation outline polygon.
- **Coverage**: Global; includes major catastrophic flood events in Karnataka (e.g. 2009 North Karnataka floods, 2018 Kodagu floods, 2019 Belagavi floods).
- **Historical depth**: 1985 to present.
- **Resolution**: Event polygon extents and centroid coordinates.
- **API**: Web download (Shapefile, GeoJSON, MapInfo, Excel sheet).
- **Authentication**: None required. Open academic access.
- **Rate limits**: None.
- **License/access**: CC-BY 4.0 / Open Access.
- **FloodPulse mapping**: `FloodObservation`, `FloodEvent` (supplementary cross-validation).
- **Limitations**: Only captures large, news-reported or satellite-detectable flood disasters; small-to-moderate district floods are omitted.
- **Status**: `VERIFIED`.

### Source: Copernicus Emergency Management Service (CEMS) Rapid Mapping
- **Authority**: European Commission / Copernicus
- **Official URL**: `https://emergency.copernicus.eu/mapping/list-of-activations-rapid`
- **Variables**: Delineation maps, observed flood water extent polygons (vector GeoJSON/Shapefile), affected infrastructure, monitored area.
- **Coverage**: Specific activated disaster zones in Karnataka (e.g. Activation EMSR304 for August 2018 Kodagu floods, EMSR374 for August 2019 Karnataka floods).
- **Historical depth**: 2012 to present (activation-dependent only).
- **Resolution**: Very high spatial resolution (10m–20m derived from Sentinel-1 SAR and optical satellite imagery).
- **API**: Open HTTP download per activation portal.
- **Authentication**: None required for published vector layers.
- **Rate limits**: Standard web limits.
- **License/access**: Copernicus Open Access Policy.
- **FloodPulse mapping**: `FloodObservation`, `FloodHazardZone` (spatial ground-truth validation).
- **Limitations**: Event-driven only; only activated for catastrophic events where international assistance or civil protection activation is triggered. Cannot provide continuous yearly time-series.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: NRSC Bhuvan Flood Hazard Atlas & NDEM
- **Authority**: National Remote Sensing Centre (NRSC), Indian Space Research Organisation (ISRO), Govt of India
- **Official URL**: `https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=flood`
- **Variables**: Cumulative flood inundation extent (1998–2022), flood inundation frequency layers, district flood hazard categorization.
- **Coverage**: Flood-prone districts of Karnataka (Belagavi, Bagalkote, Vijayapura, Raichur, Yadgir, Kodagu, Dakshina Kannada).
- **Historical depth**: Multi-satellite historical synthesis over 20+ years.
- **Resolution**: Sub-district / floodplain scale (~30m to 50m).
- **API**: NO open public REST API. Layers are accessible through Bhuvan WebGIS map viewer and published static Atlas reports.
- **Authentication**: National Database for Emergency Management (NDEM) requires authorized government login.
- **Rate limits**: N/A.
- **License/access**: Government of India / ISRO proprietary public viewing.
- **FloodPulse mapping**: `FloodHazardZone`.
- **Limitations**: Static cumulative hazard mapping, not dynamic daily event records. Cannot serve as a dynamic temporal ML target.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: EM-DAT International Disaster Database
- **Authority**: Centre for Research on the Epidemiology of Disasters (CRED), UCLouvain
- **Official URL**: `https://www.emdat.be`
- **Variables**: Disaster number, start date, end date, disaster type ("Hydrological - Flood"), total deaths, total affected, total damage ('000 US$).
- **Coverage**: Global / National / State-level events in India.
- **Historical depth**: 1900 to present.
- **Resolution**: State or multi-state level; rarely disaggregated to district.
- **API**: Available for registered researchers via EM-DAT API.
- **Authentication**: Required (academic/non-commercial registration).
- **Rate limits**: Standard API limits.
- **License/access**: Non-commercial research license.
- **FloodPulse mapping**: Supplementary state-level validation.
- **Limitations**: Coarse spatial resolution (State/Country); inclusion threshold requires at least 10 deaths or 100 people affected or state of emergency declaration.
- **Status**: `PARTIALLY_VERIFIED`.

---

## 6. Administrative Boundary Sources

### Source: KGIS / KSRSAC Administrative Boundaries
- **Authority**: Karnataka State Remote Sensing Applications Centre (KSRSAC), Department of Electronics, IT, BT and S&T, Govt of Karnataka
- **Official URL**: `https://kgis.ksrsac.in/kgis/downloads.aspx`
- **Variables**: State boundary, 31 District boundaries, Taluk boundaries (~240 taluks), Hobli boundaries, Gram Panchayat and Village polygons.
- **Coverage**: Entire Karnataka State with complete administrative hierarchy.
- **Historical depth**: Official current gazetted boundaries.
- **Resolution**: Polygon boundaries at survey and revenue map scales.
- **API**: Portal download (.zip shapefiles) and WMS/WFS map services.
- **Authentication**: Free public download on KGIS portal.
- **Rate limits**: Standard HTTP download.
- **License/access**: Official Karnataka Government spatial data.
- **Format**: Shapefile (`.shp`, `.shx`, `.dbf`, `.prj`).
- **CRS**: EPSG:4326 (WGS 84).
- **FloodPulse mapping**: `State`, `District`, `Taluk`, `Locality`.
- **Limitations**: Shapefile downloads are grouped in archive bundles; must be uncompressed and ingested into PostGIS via GeoPandas/GDAL.
- **Status**: `VERIFIED`.

### Source: Local Government Directory (LGD)
- **Authority**: Ministry of Panchayati Raj, Government of India
- **Official URL**: `https://lgdirectory.gov.in`
- **Variables**: LGD State Code (`29` for Karnataka), LGD District Codes (31 districts), Sub-district/Taluk Codes, Block Codes, Village Codes, local administrative name spellings (English and Kannada).
- **Coverage**: All administrative units in Karnataka.
- **Historical depth**: Authoritative live directory reflecting recent administrative reorganizations (e.g., creation of Vijayanagara district from Ballari in 2021).
- **Resolution**: Administrative code and name directory.
- **API**: Web service available; open CSV/XLS directory download via "Download Directory" section on portal.
- **Authentication**: Web services require government registration and IP whitelisting; CSV directory download is open to public without authentication.
- **Rate limits**: N/A for CSV download.
- **License/access**: Official Government of India standard code directory.
- **Format**: CSV / XLS.
- **CRS**: Non-spatial attribute registry.
- **FloodPulse mapping**: Standardized codes and primary keys across `State`, `District`, `Taluk`.
- **Limitations**: Non-spatial attribute table; must be joined to KGIS/Survey of India boundary geometries using LGD codes or normalized names.
- **Status**: `VERIFIED`.

### Source: Survey of India Open Series / Bharat Maps
- **Authority**: Survey of India (SOI) / National Informatics Centre (NIC), Govt of India
- **Official URL**: `https://onlinemaps.surveyofindia.gov.in` / `https://bharatmaps.gov.in`
- **Variables**: State, District, and Sub-division boundaries of India.
- **Coverage**: All-India; official national cartographic standard.
- **Historical depth**: Current cartographic editions.
- **Resolution**: 1:50,000 / 1:250,000 scale.
- **API**: Bharat Maps WMS services (login-gated for government departments).
- **Authentication**: Portal registration with mobile OTP required for downloading SOI open sheets.
- **Rate limits**: Download quotas per user account.
- **License/access**: National Map Policy (free for Indian citizens for personal/educational use).
- **Format**: PDF / GeoTIFF / Shapefile (via Bharat Maps).
- **CRS**: WGS 84 / UTM.
- **FloodPulse mapping**: `State`, `District` boundary validation.
- **Limitations**: Download gating (OTP/registration) prevents automated machine pipelines without manual intervention.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: Datameet Karnataka Maps (Open Community Data)
- **Authority**: Datameet Community (curated from Survey of India, Census 2011, and official gazettes)
- **Official URL**: `https://github.com/datameet/maps`
- **Variables**: Karnataka state boundary, district boundaries, taluk boundaries.
- **Coverage**: Entire Karnataka state.
- **Historical depth**: Census 2011 baseline with community-maintained district splits.
- **Resolution**: Cleaned vector geometries.
- **API**: GitHub repository / Raw CDN access.
- **Authentication**: None.
- **Rate limits**: Standard GitHub bandwidth.
- **License/access**: Creative Commons Attribution 2.5 India (CC-BY 2.5 IN).
- **Format**: GeoJSON, TopoJSON, Shapefile.
- **CRS**: EPSG:4326 (WGS 84).
- **FloodPulse mapping**: `State`, `District`, `Taluk` (development and rapid verification).
- **Limitations**: Community dataset; while derived from Census/SOI, official legal disputes or newest taluk bifurcations must be checked against KGIS.
- **Status**: `VERIFIED`.

---

## 7. DEM/Terrain Sources

### Source: Copernicus DEM GLO-30 (AWS Open Data)
- **Authority**: European Space Agency (ESA) / Airbus Defence and Space / DLR
- **Official URL**: `https://registry.opendata.aws/copernicus-dem/`
- **Variables**: Elevation above sea level in metres (`elevation_m`).
- **Coverage**: Global landmass between 84°N and 60°S; 100% coverage of Karnataka.
- **Historical depth**: TanDEM-X radar acquisition (2011–2015), released 2021.
- **Resolution**: 1 arc-second (~30 metres at equator).
- **API**: YES. Direct AWS S3 access (`s3://copernicus-dem-30m/`) via AWS CLI (`--no-sign-request`) or HTTPS tile downloads.
- **Authentication**: None required for public S3 bucket access.
- **Rate limits**: Standard AWS S3 egress.
- **License/access**: Free open access under Copernicus WorldDEM-30 terms with attribution.
- **Format**: Cloud Optimized GeoTIFF (COG).
- **CRS**: EPSG:4326 (WGS 84 horizontal), EGM2008 geoid (vertical).
- **FloodPulse mapping**: `TerrainDataset`, slope calculation, district zonal elevation statistics.
- **Limitations**: Surface model (DSM) reflects vegetation canopy and tall structures; superior vertical accuracy (<2m relative vertical error) compared to SRTM.
- **Status**: `VERIFIED`.

### Source: SRTM 30m (SRTMGL1) — NASA / USGS via OpenTopography
- **Authority**: NASA Jet Propulsion Laboratory / USGS EROS / OpenTopography
- **Official URL**: `https://opentopography.org` / `https://earthexplorer.usgs.gov`
- **Variables**: Elevation above sea level in metres (`elevation_m`).
- **Coverage**: 60°N to 56°S; full Karnataka coverage.
- **Historical depth**: February 2000 mission baseline.
- **Resolution**: 1 arc-second (~30 metres).
- **API**: YES. OpenTopography Global DEM API: `https://portal.opentopography.org/API/globaldem?demtype=SRTMGL1&south=11.5&north=18.5&west=74.0&east=78.5&outputFormat=GTiff&API_Key=...`.
- **Authentication**: Free API Key required for OpenTopography API. Direct USGS EarthExplorer requires login.
- **Rate limits**: 1 call per second, batch volume quotas on OpenTopography.
- **License/access**: Open data / Public domain (NASA/USGS).
- **Format**: GeoTIFF.
- **CRS**: EPSG:4326 (WGS 84 horizontal), EGM96 (vertical).
- **FloodPulse mapping**: `TerrainDataset`, slope calculation.
- **Limitations**: Acquired in 2000; does not reflect subsequent major civil infrastructure, quarrying, or reservoir impoundments created post-2000.
- **Status**: `VERIFIED`.

### Source: CartoDEM 30m (ISRO NRSC / Bhuvan)
- **Authority**: National Remote Sensing Centre (NRSC), ISRO, Govt of India
- **Official URL**: `https://bhuvan-app3.nrsc.gov.in/data/download/index.php`
- **Variables**: Elevation in metres (derived from Cartosat-1 stereo imagery).
- **Coverage**: Indian landmass, including all Karnataka tiles.
- **Historical depth**: Cartosat-1 operational lifespan (2005–2019).
- **Resolution**: 1 arc-second (~30 metres).
- **API**: NO direct automated API. Download via Bhuvan tile selection.
- **Authentication**: Required. Free Bhuvan user registration login.
- **Rate limits**: 10 tile downloads per day per account.
- **License/access**: ISRO Open Data policy for Indian users.
- **Format**: GeoTIFF.
- **CRS**: WGS 84 / UTM.
- **FloodPulse mapping**: `TerrainDataset`.
- **Limitations**: Login requirement and tile-per-day rate limit hinder automated containerized deployment compared to open AWS S3 Copernicus DEM.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: ALOS AW3D30 (JAXA)
- **Authority**: Japan Aerospace Exploration Agency (JAXA)
- **Official URL**: `https://www.eorc.jaxa.jp/ALOS/en/aw3d30/`
- **Variables**: Elevation in metres (PRISM stereo optical DSM).
- **Coverage**: Global landmass; complete Karnataka coverage.
- **Historical depth**: 2006–2011 acquisition.
- **Resolution**: 30 metres.
- **API**: Direct HTTP/FTP download after user registration.
- **Authentication**: Required (free user registration).
- **Rate limits**: Standard FTP/HTTP limits.
- **License/access**: Free for research/commercial with attribution.
- **Format**: GeoTIFF.
- **CRS**: EPSG:4326.
- **FloodPulse mapping**: `TerrainDataset`.
- **Limitations**: Registration requirement; Copernicus DEM GLO-30 provides simpler, unauthenticated COG streaming.
- **Status**: `PARTIALLY_VERIFIED`.

---

## 8. Land Cover Sources

### Source: ESA WorldCover 10m
- **Authority**: European Space Agency (ESA) / VITO Remote Sensing
- **Official URL**: `https://esa-worldcover.org`
- **Variables**: 11 discrete land cover classes: Tree cover (10), Shrubland (20), Grassland (30), Cropland (40), Built-up (50), Bare/sparse vegetation (60), Snow and ice (70), Permanent water bodies (80), Herbaceous wetland (90), Mangroves (95), Moss and lichen (100).
- **Coverage**: Global; 100% coverage of Karnataka.
- **Historical depth**: 2020 (v100) and 2021 (v200) annual products.
- **Resolution**: 10 metres (derived from Sentinel-1 SAR and Sentinel-2 optical).
- **API**: YES. Direct AWS S3 access (`s3://esa-worldcover/`) via AWS CLI (`--no-sign-request`) and Terrascope.
- **Authentication**: None required for public S3 bucket access.
- **Rate limits**: Standard AWS S3 egress.
- **License/access**: Creative Commons Attribution 4.0 International (CC-BY 4.0).
- **Format**: Cloud Optimized GeoTIFF (COG).
- **CRS**: EPSG:4326 (WGS 84).
- **FloodPulse mapping**: `LandCover`, infiltration capacity feature calculation, urban vs rural risk weighting.
- **Limitations**: Discrete annual snapshots (2020, 2021); does not capture intra-annual seasonal crop rotations.
- **Status**: `VERIFIED`.

### Source: ESRI 10m Sentinel-2 Land Cover Time Series
- **Authority**: Impact Observatory / Esri / Microsoft Planetary Computer
- **Official URL**: `https://livingatlas.arcgis.com/landcover/`
- **Variables**: 9 land use / land cover classes: Water, Trees, Flooded Vegetation, Crops, Built Area, Bare Ground, Snow/Ice, Clouds, Rangeland.
- **Coverage**: Global; complete Karnataka coverage.
- **Historical depth**: Annual continuous maps from 2017 to 2023.
- **Resolution**: 10 metres.
- **API**: YES. AWS Open Data (`s3://io-lulc/`) and Microsoft Planetary Computer STAC API.
- **Authentication**: None for public S3 bucket access.
- **Rate limits**: Standard cloud storage bandwidth.
- **License/access**: Creative Commons Attribution 4.0 International (CC-BY 4.0).
- **Format**: Cloud Optimized GeoTIFF (COG).
- **CRS**: EPSG:4326.
- **FloodPulse mapping**: `LandCover`, historical urban expansion and land use change features.
- **Limitations**: Deep learning model occasionally confuses dry bare agricultural fields with built-up surfaces in semi-arid North Karnataka.
- **Status**: `VERIFIED`.

### Source: NRSC Bhuvan LULC (1:50,000 / 1:250,000)
- **Authority**: National Remote Sensing Centre (NRSC), ISRO, Govt of India
- **Official URL**: `https://bhuvan-app1.nrsc.gov.in/thematic/thematic.php`
- **Variables**: National Land Use / Land Cover classification system (19 classes / 33 classes).
- **Coverage**: All-India; complete Karnataka coverage.
- **Historical depth**: Cyclic epochs (2005–06, 2011–12, 2015–16, 2019–20).
- **Resolution**: 1:50,000 scale (derived from Resourcesat LISS-III / LISS-IV).
- **API**: NO open REST API. WebGIS visualization; download gated for authorized users.
- **Authentication**: Login required for map downloads.
- **Rate limits**: Gated.
- **License/access**: Govt of India / ISRO data policy.
- **Format**: GeoTIFF / Vector.
- **CRS**: LCC / WGS 84.
- **FloodPulse mapping**: `LandCover`.
- **Limitations**: Download access is restricted; ESA WorldCover 10m provides higher spatial resolution (10m vs ~24m) with open unauthenticated S3 access.
- **Status**: `PARTIALLY_VERIFIED`.

---

## 9. Water Body Sources

### Source: JRC Global Surface Water (GSW)
- **Authority**: European Commission Joint Research Centre (JRC)
- **Official URL**: `https://global-surface-water.appspot.com`
- **Variables**: Water Occurrence (%), Water Recurrence (%), Seasonality, Water Transition, Maximum Water Extent.
- **Coverage**: Global inland water bodies; complete Karnataka coverage.
- **Historical depth**: 1984 to 2021 (38 years of Landsat 5, 7, 8 observations).
- **Resolution**: 30 metres.
- **API**: YES. Direct tile HTTPS downloads (`https://storage.googleapis.com/global-surface-water/downloads/`) and Google Earth Engine asset.
- **Authentication**: None required for direct tile downloads.
- **Rate limits**: Standard Google Cloud Storage egress.
- **License/access**: European Commission open data (free reuse with citation).
- **Format**: GeoTIFF tiles (10° x 10°).
- **CRS**: EPSG:4326.
- **FloodPulse mapping**: `WaterBody`, baseline permanent water vs flood inundation discrimination.
- **Limitations**: 30m resolution may miss small rural irrigation tanks under 1000 m²; cloud cover during peak monsoon creates occasional optical gaps.
- **Status**: `VERIFIED`.

### Source: HydroSHEDS / HydroRIVERS / HydroLAKES
- **Authority**: World Wildlife Fund (WWF) / USGS / McGill University
- **Official URL**: `https://www.hydrosheds.org`
- **Variables**: River network centerlines, stream order, upstream catchment area (`cum_area`), river discharge estimate, lake surface area, shoreline geometry.
- **Coverage**: Global; covers all river basins draining Karnataka (Krishna, Cauvery, Godavari, West Flowing Rivers).
- **Historical depth**: Geomorphic baseline.
- **Resolution**: High-resolution hydrographic vector lines and lake polygons (lakes ≥ 10 hectares).
- **API**: NO REST API. Direct file downloads (Shapefile, Geopackage) via official portal.
- **Authentication**: Free registration form.
- **Rate limits**: None.
- **License/access**: Free for scientific, educational, and conservation applications.
- **Format**: Shapefile / Geopackage.
- **CRS**: EPSG:4326.
- **FloodPulse mapping**: `River`, `WaterBody`, distance-to-river spatial metric calculations (`ST_Distance`).
- **Limitations**: Lakes under 10 hectares are omitted; urban stormwater drainage channels are absent.
- **Status**: `VERIFIED`.

### Source: India-WRIS Water Bodies Layer (1st Census of Water Bodies)
- **Authority**: Ministry of Jal Shakti, Department of Water Resources, Govt of India
- **Official URL**: `https://indiawris.gov.in/wris/#/waterbodies`
- **Variables**: Water body type (Pond, Tank, Reservoir, Water Conservation Structure/Check Dam), water spread area, storage capacity, utilization status.
- **Coverage**: Over 26,000 enumerated water bodies across Karnataka.
- **Historical depth**: 1st All-India Census of Water Bodies (published 2023).
- **Resolution**: Census point and area attributes.
- **API**: NO public REST API. Portal visualization and summary state reports.
- **Authentication**: None for viewing.
- **Rate limits**: N/A.
- **License/access**: Govt of India public census.
- **Format**: Web display / PDF reports.
- **CRS**: Non-spatial attribute tables with location references.
- **FloodPulse mapping**: `WaterBody`.
- **Limitations**: No bulk GIS vector geometry download is exposed on the public portal; attributes must be cross-referenced with KGIS water layers.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: OpenStreetMap Water Features
- **Authority**: OpenStreetMap Community
- **Official URL**: `https://www.openstreetmap.org`
- **Variables**: `waterway=river`, `waterway=stream`, `waterway=canal`, `waterway=drain`, `natural=water`, `water=reservoir`, `water=lake`, `water=pond`.
- **Coverage**: Entire Karnataka state.
- **Historical depth**: Continuously updated community map.
- **Resolution**: Detailed vector lines and polygons.
- **API**: YES. Overpass API (`https://overpass-api.de/api/interpreter`) and Geofabrik Karnataka regional extract (`karnataka-latest.osm.pbf`).
- **Authentication**: None.
- **Rate limits**: Overpass rate limits (fair use, 2 concurrent queries per IP).
- **License/access**: Open Database License (ODbL). Attribution required.
- **Format**: OSM PBF, GeoJSON, Shapefile.
- **CRS**: EPSG:4326.
- **FloodPulse mapping**: `River`, `WaterBody` (local drains and canals).
- **Limitations**: Tier 3 community data; attribute completeness and spatial precision vary between urban centers (high completeness) and remote rural tracts.
- **Status**: `VERIFIED`.

---

## 10. Emergency/Shelter Sources

### Source: Karnataka SDMA / DDMA District Disaster Management Plans (DDMP)
- **Authority**: Karnataka State Disaster Management Authority (KSDMA) / District Disaster Management Authorities (DDMA), Revenue Dept, Govt of Karnataka
- **Official URL**: `https://revenue.karnataka.gov.in` / District portals (`https://s3waas.gov.in/`)
- **Variables**: Designated cyclone/flood relief shelters, relief centers, community halls, government schools/hostels identified for evacuation, shelter capacity (persons), nodal officer contact numbers.
- **Coverage**: Flood-prone districts (Belagavi, Bagalkote, Kodagu, Dakshina Kannada, Udupi, Uttara Kannada, Raichur).
- **Historical depth**: Annual / periodic DDMP editions (e.g., DDMP 2020–2024).
- **Resolution**: Village / Taluk facility lists.
- **API**: NO machine-readable API. Published exclusively in static PDF annexures of District Disaster Management Plans.
- **Authentication**: None for public district portal PDF downloads.
- **Rate limits**: N/A.
- **License/access**: Public government administrative publications.
- **FloodPulse mapping**: `EmergencyFacility` (type: `shelter`).
- **Limitations**: **Critical project gap**. There is no live, centralized, machine-readable database or API for flood shelters or relief camp occupancy. Data exists only in static PDF tables requiring manual extraction, address geocoding, and field verification.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: India Disaster Resource Network (IDRN)
- **Authority**: National Institute of Disaster Management (NIDM) / National Disaster Management Authority (NDMA), Govt of India
- **Official URL**: `https://idrn.nidm.gov.in`
- **Variables**: Inventory of disaster relief equipment, relief camps/shelters, medical supplies, transport vehicles, warehouse capacities by district.
- **Coverage**: All districts of Karnataka.
- **Historical depth**: Regularly updated by District Emergency Operation Centres (DEOCs).
- **Resolution**: Facility and equipment level per district.
- **API**: NO public API.
- **Authentication**: **Restricted**. Access is strictly limited to authorized District Magistrates, Deputy Commissioners, and disaster management officers.
- **Rate limits**: Strictly gated.
- **License/access**: Confidential / Restricted government portal.
- **FloodPulse mapping**: `EmergencyFacility`.
- **Limitations**: Inaccessible to public applications and independent developers. Cannot be used for FloodPulse production ingestion.
- **Status**: `UNAVAILABLE`.

### Source: Ayushman Bharat Digital Mission (ABDM) Health Facility Registry (HFR)
- **Authority**: National Health Authority (NHA), Ministry of Health & Family Welfare, Govt of India
- **Official URL**: `https://hfr.abdm.gov.in`
- **Variables**: Registered health facilities (Hospitals, Community Health Centres, Primary Health Centres), facility name, address, latitude, longitude, bed capacity, public/private status.
- **Coverage**: Statewide across all Karnataka districts.
- **Historical depth**: Active national registry.
- **Resolution**: Point facility coordinates.
- **API**: YES. ABDM HFR Developer APIs (`https://sandbox.abdm.gov.in/`).
- **Authentication**: Required (ABDM Developer account, Client ID and Client Secret).
- **Rate limits**: Sandbox / production quotas.
- **License/access**: Government of India digital public infrastructure.
- **FloodPulse mapping**: `EmergencyFacility` (type: `hospital`).
- **Limitations**: Requires developer onboarding and consent flows for full production endpoints; basic portal listing is publicly searchable.
- **Status**: `PARTIALLY_VERIFIED`.

### Source: OpenStreetMap Emergency & Healthcare Facilities
- **Authority**: OpenStreetMap Community
- **Official URL**: `https://www.openstreetmap.org`
- **Variables**: `amenity=hospital`, `amenity=clinic`, `amenity=fire_station`, `amenity=police`, `amenity=community_centre`, `building=school`, `social_facility=shelter`.
- **Coverage**: Statewide; dense in urban areas (Bengaluru, Mysuru, Hubballi, Belagavi, Mangaluru), moderate in rural taluks.
- **Historical depth**: Continuously updated.
- **Resolution**: Point coordinates and building polygon footprints.
- **API**: YES. Overpass API (`https://overpass-api.de/api/interpreter`) or regional extract filtering via Osmium/Python.
- **Authentication**: None.
- **Rate limits**: Standard Overpass limits.
- **License/access**: Open Database License (ODbL).
- **FloodPulse mapping**: `EmergencyFacility` (`hospital`, `fire_station`, `police_station`).
- **Limitations**: **Rule violation risk if misused**: An OSM feature tagged `amenity=shelter` or `building=school` does NOT mean it is an officially designated, operating flood evacuation shelter. OSM can supply verified hospitals, fire stations, and police stations, but cannot be presented as official government flood relief camps.
- **Status**: `VERIFIED` (for hospitals, police, and fire stations; NOT for official flood evacuation shelters).

---

## 11. Routing Sources

### Source: Open Source Routing Machine (OSRM)
- **Authority**: Project OSRM (Open Source Community / Luxen / Mapbox)
- **Official URL**: `http://project-osrm.org` / GitHub: `Project-OSRM/osrm-backend`
- **Variables**: Turn-by-turn driving and walking directions, route duration (seconds), distance (metres), route geometry (GeoJSON LineString).
- **Coverage**: Karnataka road network (built from Geofabrik Karnataka OSM PBF extract).
- **Historical depth**: Live calculation based on supplied road network graph.
- **Resolution**: High-precision road network graph.
- **API**: YES. Standard REST API: `GET /route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson`.
- **Self-hosting**: YES. High-performance C++ engine easily deployable via official Docker image (`osrm/osrm-backend`). Preprocessing Karnataka PBF (~150 MB) takes ~3 minutes and consumes <1 GB RAM.
- **Authentication**: None (when self-hosted). Demo public server (`router.project-osrm.org`) has strict rate limits.
- **Rate limits**: Unlimited when self-hosted.
- **License/access**: Simplified 2-Clause BSD License (software) + ODbL (OSM map data).
- **FloodPulse mapping**: Route calculation from user coordinate to `EmergencyFacility` (`/api/v1/routing/to-shelter`).
- **Limitations**: Standard car/foot profile does not automatically avoid active flood inundation zones unless custom edge-weighting scripts or dynamic barrier penalties are applied during graph preparation.
- **Status**: `VERIFIED`.

### Source: GraphHopper Routing Engine
- **Authority**: GraphHopper GmbH (Open Source Community)
- **Official URL**: `https://www.graphhopper.com` / GitHub: `graphhopper/graphhopper`
- **Variables**: Route geometry, distance, travel time, elevation profile, custom road avoidance areas.
- **Coverage**: Karnataka road network (from OSM PBF).
- **Historical depth**: Dynamic.
- **Resolution**: Road graph.
- **API**: YES. REST API: `/route?point={lat1},{lon1}&point={lat2},{lon2}&vehicle=car`.
- **Self-hosting**: YES. Java-based engine (`graphhopper/graphhopper` Docker).
- **Authentication**: None for self-hosted; API key required for GraphHopper Directions API SaaS (free tier: 500 requests/day).
- **Rate limits**: Unlimited when self-hosted.
- **License/access**: Apache License 2.0 (engine).
- **FloodPulse mapping**: Evacuation routing with custom polygon avoidance (avoiding predicted flood hazard zones).
- **Limitations**: Slightly higher memory requirement for Java heap compared to C++ OSRM for large networks.
- **Status**: `VERIFIED`.

### Source: Valhalla Routing Engine
- **Authority**: Open-source community / Mapbox / FOSSGIS
- **Official URL**: `https://github.com/valhalla/valhalla`
- **Variables**: Multi-modal routing, dynamic costing, polygon avoidance, isochrones.
- **Coverage**: Global / Karnataka OSM.
- **API**: YES. REST API.
- **Self-hosting**: YES. Docker container.
- **Authentication**: None when self-hosted.
- **Rate limits**: Unlimited when self-hosted.
- **License/access**: MIT License.
- **FloodPulse mapping**: Evacuation routing and isochrone calculation.
- **Limitations**: More complex tile build pipeline than OSRM.
- **Status**: `VERIFIED`.

### Source: OpenRouteService (HeiGIT)
- **Authority**: Heidelberg Institute for Geoinformation Technology (HeiGIT)
- **Official URL**: `https://openrouteservice.org`
- **Variables**: Routing, isochrones, time-distance matrices.
- **Coverage**: Global / Karnataka.
- **API**: YES. `https://api.openrouteservice.org/v2/directions/driving-car`.
- **Self-hosting**: YES. Docker container.
- **Authentication**: Free API Key required for hosted API (free tier: 2,000 requests/day).
- **Rate limits**: 40 requests/minute on public API.
- **License/access**: LGPL 3.0.
- **FloodPulse mapping**: Evacuation routing and accessibility isochrones.
- **Limitations**: Public hosted API requires API key registration and has strict daily quotas.
- **Status**: `VERIFIED`.

---

## Flood Label Candidates

The machine learning component of FloodPulse requires a defensible ground-truth target for flood occurrence. A critical architectural and scientific constraint is:
**Do NOT confuse rainfall with flood labels. A rainfall threshold or weather forecast is not an observed flood event.**

| Source | Represents Observed Flooding? | Spatial Resolution | Temporal Resolution | Independent Target? | Status |
|---|---|---|---|---|---|
| **India Flood Inventory (IFI)** (IIT Delhi HydroSense Lab) | **YES**. Documented historical flood events with reported loss/damage compiled from IMD Disastrous Weather Reports, EM-DAT, and DFO. | District-level (District names and coordinates). | Daily start and end dates (1967–2023). | **YES**. Independent of rainfall features; captures real reported impact and inundation. | `VERIFIED` (Primary ML Target) |
| **Dartmouth Flood Observatory (DFO)** | **YES**. Satellite-observed and news-verified large flood events. | Event inundation polygon extents and centroid coordinates. | Daily start and end dates (1985–present). | **YES**. Independent of rainfall features. | `VERIFIED` (Secondary Target / Validation) |
| **Copernicus EMS Rapid Mapping** | **YES**. High-resolution satellite SAR (Sentinel-1) flood water delineation. | 10m–20m vector flood extent polygons. | Acquisition timestamps for activated disasters. | **YES**. Physically observed satellite flood water. | `PARTIALLY_VERIFIED` (Event-driven only; too sparse for continuous multi-year target) |
| **NRSC Bhuvan Flood Hazard Atlas** | **NO**. Modeled cumulative inundation frequency over 1998–2022. | Sub-district / floodplain hazard zone polygons. | Static cumulative reference map (no event timestamps). | **NO**. Static hazard classification, not a discrete temporal event observation. | `PARTIALLY_VERIFIED` (Spatial prior / feature only) |
| **EM-DAT Disaster Database** | **YES**. Documented disaster events meeting humanitarian criteria (deaths/affected). | National and State-level aggregates. | Event start and end dates. | **YES**. Independent impact record. | `PARTIALLY_VERIFIED` (Too coarse spatially for district-level ML) |
| **IMD Heavy Rainfall Warnings (Red Alerts)** | **NO**. Meteorological forecast thresholds (>204.4 mm rain). | Meteorological subdivisions / districts. | Daily forecasts. | **NO**. Weather warning, NOT observed ground inundation. | `REJECTED` (Feature only, never target) |
| **Heuristic Formula (`rainfall * slope`)** | **NO**. Synthetic rule invented by human developer. | Arbitrary. | Arbitrary. | **NO**. Violation of CONSTRAINTS.md. | `REJECTED` (Prohibited) |

---

## Data Contract Mapping

| FloodPulse Database Entity | Candidate Source(s) | Status | Contract Compliance Notes |
|---|---|---|---|
| `State` | KGIS / LGD / Datameet | `VERIFIED` | Karnataka State polygon, EPSG:4326, LGD State Code `29`. |
| `District` | KGIS / LGD / Datameet | `VERIFIED` | 31 Karnataka districts, EPSG:4326 MultiPolygons, LGD codes. |
| `Taluk` | KGIS / LGD | `VERIFIED` | ~240 sub-district taluk polygons, EPSG:4326. |
| `Locality` | KGIS Hobli / OSM Villages | `PARTIALLY_VERIFIED` | Hobli polygons available via KGIS; village points via OSM/LGD. |
| `RiverBasin` | HydroSHEDS / India-WRIS | `VERIFIED` | Major river basin polygons (Cauvery, Krishna, Godavari, West Flowing Rivers). |
| `SubBasin` | India-WRIS / HydroSHEDS | `VERIFIED` | Sub-catchment polygons. |
| `River` | HydroRIVERS / OSM Waterways | `VERIFIED` | River centerline LineStrings, stream order, name. |
| `RiverStation` | CWC / NWIC Portal | `VERIFIED` | In-situ monitoring stations with Point coordinates (EPSG:4326). |
| `RiverObservation` | NWIC Portal (`nwdp.nwic.gov.in`) | `VERIFIED` | `water_level_m`, `discharge_m3s` (where available), `observed_at` (UTC). |
| `RiverForecast` | GloFAS (`cems-glofas-forecast`) | `VERIFIED` | `discharge_m3s`, `forecast_for` (UTC), `model="GloFAS v4"`. |
| `Reservoir` | NWIC / India-WRIS / KSNDMC | `VERIFIED` | 14+ major dams in Karnataka with Point location, FRL, capacity. |
| `ReservoirObservation` | NWIC Karnataka Dataset / KSNDMC | `VERIFIED` | `storage_mcm`, `level_m`, `inflow_m3s`, `outflow_m3s`, `observed_at`. |
| `WeatherObservation` | IMD Gridded / NASA POWER / Open-Meteo | `VERIFIED` | Temperature, humidity, wind speed, pressure, observed timestamps. |
| `RainfallObservation` | IMD 0.25° Gridded / KSNDMC (OpenCity) | `VERIFIED` | `rainfall_mm`, observation date, provenance tagged. |
| `WeatherForecast` | IMD API / Open-Meteo Forecast | `VERIFIED` | Forecast precipitation, temperature, wind, `issued_at`, `forecast_for`. |
| `FloodObservation` | India Flood Inventory (IFI) / DFO | `VERIFIED` | Event dates, affected district, duration, fatalities, source ID. |
| `FloodEvent` | IFI Aggregations / Normalization | `VERIFIED` | Normalized multi-district flood occurrences with provenance. |
| `FloodHazardZone` | NRSC Bhuvan Flood Atlas | `PARTIALLY_VERIFIED` | Multi-year cumulative hazard zone polygons. |
| `TerrainDataset` | Copernicus DEM GLO-30 (AWS Open Data) | `VERIFIED` | 30m Cloud Optimized GeoTIFF, EPSG:4326, elevation & slope features. |
| `LandCover` | ESA WorldCover 10m / ESRI 10m | `VERIFIED` | 10m raster classification, impervious surface / cropland ratios. |
| `WaterBody` | JRC Surface Water / HydroLAKES / OSM | `VERIFIED` | Waterbody polygons and historical surface water recurrence. |
| `EmergencyFacility` | KSDMA DDMP (Shelters) + OSM (Hospitals/Fire/Police) | `PARTIALLY_VERIFIED` | Shelters extracted from DDMP PDFs; Hospitals & Fire from OSM. |
| `CommunityReport` | Citizen submissions | `N/A` (Internal) | Starts as `UNVERIFIED` per CONSTRAINTS.md. |
| `Alert` | FloodPulse Alert Engine | `N/A` (Internal) | Distinguishes `AI_PREDICTION` vs `OFFICIAL_WARNING`. |
| `TelegramSubscription` | Telegram Bot Integration | `N/A` (Internal) | User chat IDs and subscribed district scopes. |
| `DataSource` / `DataIngestionRun` | Ingestion framework | `N/A` (Internal) | Provenance tracking for every retrieved record. |

---

## Unresolved Data Gaps

| Requirement | Finding | Impact | Next Action / Recommendation |
|---|---|---|---|
| **Authoritative Live Shelter Registry & Real-Time Occupancy** | KSDMA and district authorities do not operate an open, machine-readable shelter API. Designated relief camps are documented in static PDF annexures of District Disaster Management Plans (DDMP) or created dynamically during active floods by DEOCs. IDRN exists but is restricted to government logins. | Cannot automatically ingest live shelter lists or real-time occupancy over the internet. | 1. Ingest official designated relief centers by extracting and geocoding verified tables from published DDMPs for high-risk flood districts (Belagavi, Kodagu, Dakshina Kannada).<br>2. Supplement with OSM/ABDM hospitals and fire stations.<br>3. Keep shelter occupancy explicitly `NULL` ("unknown") per CONSTRAINTS.md until administrative reporting is entered. |
| **Locality / Taluk-Level Dynamic Flood Labels** | India Flood Inventory (IFI) records flood impacts at the **district** level. High-resolution taluk-level or village-level historical inundation labels are not systematically compiled in any open dataset across 50 years. | The primary ML prediction unit must be at the **District** level for the 30-day scope. Taluk-level prediction cannot have defensible continuous ML ground truth without fabricating labels. | Anchor the primary ML prediction model at the **District** level, where IFI ground truth is rigorously defensible. For taluk-level visualization, display disaggregated rainfall and terrain features clearly labeled as risk indicators, not ML targets. |
| **Real-Time Live Automated Reservoir Release API** | Karnataka WRD and dam authorities do not publish a public webhook or high-frequency automated streaming REST API for gate openings / discharge. Data is posted to public dashboards, daily bulletins (KSNDMC), and NWIC historical files. | Intraday dam release spikes cannot be streamed on a sub-hourly basis via an open API. | Schedule daily ingestion jobs against NWIC and KSNDMC daily reports during active monsoon months. Mark telemetry freshness explicitly in the UI (`FRESH` vs `STALE`). |
| **In-Situ River Discharge (CWC Gauges)** | While CWC river gauge water levels are widely reported on NWIC, computed river discharge (m³/s) is often withheld or irregularly updated at interstate sensitive stations in Karnataka. | Direct in-situ discharge timeseries will have missing values at specific stations. | 1. Use water level (`water_level_m`) as the primary in-situ hydrological feature.<br>2. Use GloFAS 0.05° gridded discharge as a secondary modeled feature.<br>3. Follow DATA_CONTRACT.md: `missing ≠ zero`; do not impute zero for missing discharge. |

---

## Sources Requiring Credentials

| Source | Credential Type | Status | Action Required for Integration |
|---|---|---|---|
| **IMD API Management Platform** | API Key + JWT Bearer Token + Static Public IP Binding | `BLOCKED` | Requires formal departmental registration and server static public IP whitelisting. Use IMD Gridded (`imdlib`) and Open-Meteo for development. |
| **Copernicus CDS (GloFAS & ERA5-Land)** | User Account UID + API Key in `~/.cdsapirc` + Portal License Acceptance | `PENDING_SETUP` | Requires free developer account registration at `cds.climate.copernicus.eu` and accepting GloFAS terms of use on web form. |
| **NASA Earthdata (GPM IMERG)** | Username & Password (HTTP Basic Auth / Bearer Token) | `PENDING_SETUP` | Free account on `urs.earthdata.nasa.gov`. |
| **OpenTopography (SRTM 30m API)** | OpenTopography API Key | `PENDING_SETUP` | Free registration on `opentopography.org`. Alternatively, use unauthenticated AWS S3 Copernicus DEM GLO-30. |
| **India Disaster Resource Network (IDRN)** | Government Administrative Credentials (DC/DM login) | `BLOCKED / UNAVAILABLE` | Restricted to official government authorities. Do not attempt to access. |
| **National Water Informatics Centre (NWIC API)** | Portal Developer Key | `PENDING_SETUP` | Free registration on `nwdp.nwic.gov.in` for API catalog keys; direct CSV downloads do not require keys. |
| **ABDM Health Facility Registry (HFR)** | Client ID + Client Secret (OAuth 2.0) | `PENDING_SETUP` | Requires developer sandbox registration at `sandbox.abdm.gov.in`. |

---

## Sources Not Suitable

| Source | Reason |
|---|---|
| **Synthetic Environmental Generators** (`np.random`, sine-wave rainfall) | **Violates CONSTRAINTS.md**. Fabricated environmental data is strictly forbidden. |
| **Heuristic Risk Formula as ML Label** (`risk = rain*0.4 + slope*0.2`) | **Violates CONSTRAINTS.md and ML_SPEC.md**. A formula is not ground-truth observed flooding. |
| **Unverified Weather Scrapers** (Unofficial IMD web scrapers on GitHub) | Fragile, violates IMD terms of service, breaks on HTML layout updates, and lacks official provenance. |
| **OSM `amenity=shelter` as Official Evacuation Shelters** | In OpenStreetMap, `amenity=shelter` commonly denotes a gazebo, bus stop shelter, or picnic canopy. Conflating this with a government-managed flood relief center creates acute safety hazards. |
| **Static Hardcoded District Risk Lookup Tables** | Violates CONSTRAINTS.md. Features must be derived dynamically from valid spatial and environmental datasets. |

---

## Research Notes

1. **ML Feasibility & Target Strategy**: The IIT Delhi India Flood Inventory (IFI) is the most defensible dataset discovered for training a supervised flood occurrence model in India. It covers 1967–2023, provides explicit start and end dates, attributes affected districts, and derives from official IMD Disastrous Weather Reports. Its limitation is district-level spatial aggregation. Therefore, the ML problem formulation must be:
   - **Unit of Analysis**: District × Day (or multi-day window).
   - **Label**: $1$ if district experienced a documented flood event on that day/window in IFI; $0$ otherwise.
   - **Evaluation**: Time-based holdout split (e.g. train on 1980–2018, test on 2019–2023).

2. **Terrain & GIS Foundation**: The combination of **Copernicus DEM GLO-30** (via AWS Open Data) and **KGIS administrative boundary shapefiles** provides a high-resolution, unencumbered foundation for terrain analysis. Both datasets use EPSG:4326, have verified coverage of Karnataka, and require no proprietary licenses or gated access. Slope and elevation can be extracted dynamically per district and taluk via raster zonal statistics in PostGIS or GeoPandas.

3. **Hydrological Strategy**: NWIC's newly published Karnataka manual reservoir dataset (`karnataka_man_reservoir_data.csv`) covers major dams back to 1990 with daily level, storage, inflow, and outflow. This resolves the historical reservoir feature requirement without needing synthetic values. For river discharge, since CWC gauge discharge is often gated, coupling CWC in-situ river gauge water levels with GloFAS 0.05° gridded discharge estimates provides a resilient dual-source approach.

4. **Next Step (Phase 1.2 — Targeted API Verification)**:
   In the next task, a focused subset of open, high-value endpoints will be tested using reproducible test scripts / Postman requests to verify schema compliance against `DATA_CONTRACT.md`:
   - Open-Meteo Weather & Archive API (Meteorology / Forecast)
   - Copernicus DEM GLO-30 S3 access (Terrain)
   - NWIC Karnataka Reservoir Dataset (Hydrology / Reservoir)
   - IIT Delhi India Flood Inventory extraction for Karnataka (ML Target)
   - OSRM Karnataka Routing endpoint (Emergency navigation)
