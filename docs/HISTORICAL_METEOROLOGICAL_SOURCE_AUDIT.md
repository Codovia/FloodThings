# Historical Meteorological Data Source Validation (Phase 3.7A)

## Objective

Identify and empirically validate legitimate historical meteorological and reanalysis sources capable of providing machine-readable environmental data that overlap the audited historical flood evidence (1969–1994) across the State of Karnataka.

This audit establishes whether real, reproducible meteorological records exist to support future flood-ML feature engineering without relying on synthetic generation, imputation, or unverifiable proxies.

---

## Required Historical Coverage

- **Target Period:** 1969-07-14 to 1994-10-05 (25 years, 83 days / 9,215 calendar days).
- **Earliest Documented IFI Flood Event:** `1969-07-14` (Bengaluru Urban / statewide monsoon surges).
- **Latest Documented IFI Flood Event:** `1994-10-04` (Statewide post-monsoon flood episodes).
- **Target Geography:** Karnataka (11.5°N to 18.5°N, 74.0°E to 78.5°E), covering all 31 districts.
- **Required Variables:**
  - Precipitation / Rainfall (`mm` or `kg/m²`)
  - Surface Temperature (`°C` or `K`)
  - Relative Humidity (`%`)
  - Surface Pressure (`hPa` or `Pa`)

---

## Candidate Sources

The following seven candidate sources and data platforms were investigated:

| Source Name | Provider | Declared Category | Declared Historical Span | Stated Spatial Resolution | Stated Temporal Resolution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Open-Meteo Historical Weather Archive API** | Open-Meteo GmbH / ECMWF reanalysis products | REANALYSIS | 1940-01-01 to present | 0.1° (~11 km) / 0.25° (~28 km) | Hourly, Daily |
| **ECMWF Copernicus Climate Data Store (CDS)** | Copernicus / ECMWF (ERA5 Reanalysis) | REANALYSIS | 1940-01-01 to present | 0.25° (~28 km ERA5) / 0.1° (~11 km ERA5-Land) | Hourly, Monthly |
| **NASA POWER (MERRA-2)** | NASA Langley Research Center | REANALYSIS | 1981-01-01 to present | 0.5° × 0.625° (~50 km) | Hourly, Daily |
| **NOAA PSL / CPC Global Unified Precipitation** | NOAA Physical Sciences Laboratory / CPC | OBSERVATION (Gridded Gauge) | 1979-01-01 to present | 0.5° (~50 km) | Daily |
| **IMD Gridded Rainfall (0.25° × 0.25°)** | India Meteorological Department (IMD Pune) | OBSERVATION (Interpolated Gauges) | 1901-01-01 to present | 0.25° (~25 km) | Daily |
| **IMD National Data Centre API (`api.imd.gov.in`)** | India Meteorological Department | OBSERVATION | Variable (station-dependent) | Point / Station | Daily / Sub-daily |
| **OpenCity / KSNDMC Historical Rainfall** | KSNDMC / OpenCity.in | OBSERVATION | 2015 to 2025 | District / Taluk summaries | Annual / Monthly aggregates |

---

## Empirical Validation

Empirical lightweight network and data probes were executed from the local project environment to verify machine-readable accessibility, data availability, coordinate querying, and schema structure.

### 1. Open-Meteo Historical Archive API (`https://archive-api.open-meteo.com/v1/archive`)
- **Probe 1 (Earliest Target Date — Bengaluru Urban: 12.9716°N, 77.5946°E, 1969-07-14 to 1969-07-15):**
  - **HTTP Status:** `200 OK`
  - **Payload Structure:** JSON containing `latitude`, `longitude`, `generationtime_ms`, `utc_offset_seconds`, `timezone`, `elevation`, `hourly_units`, `hourly`.
  - **Hourly Units:**
    - `precipitation`: `mm`
    - `temperature_2m`: `°C`
    - `relative_humidity_2m`: `%`
    - `surface_pressure`: `hPa`
  - **Returned Dimensions:** 48 hourly timesteps.
  - **Values Sample:**
    - `time`: `["1969-07-14T00:00", ... "1969-07-15T23:00"]`
    - `precipitation`: `0.4 mm` (total 48-hr cumulative = `1.30 mm`)
    - `temperature_2m`: `19.8 °C` (range: `18.5 °C` to `24.2 °C`)
    - `relative_humidity_2m`: `95%` (range: `76%` to `97%`)
    - `surface_pressure`: `905.4 hPa` (range: `904.2 hPa` to `908.1 hPa`)
- **Probe 2 (Latest Target Date — Statewide Spatial Test across 4 Quadrants, 1994-10-04 to 1994-10-05):**
  - **North-West (Belagavi: 15.85°N, 74.50°E):** Status `200 OK`, 48 hourly records, 48-hr total precip `37.30 mm`, temp `19.9 °C`.
  - **North-East (Kalaburagi: 17.33°N, 76.83°E):** Status `200 OK`, 48 hourly records, 48-hr total precip `20.70 mm`, temp `22.6 °C`.
  - **Coast / South-West (Mangaluru: 12.87°N, 75.25°E):** Status `200 OK`, 48 hourly records, 48-hr total precip `18.00 mm`, temp `21.8 °C`.
  - **South-Interior (Mandya: 12.52°N, 76.90°E):** Status `200 OK`, 48 hourly records, 48-hr total precip `10.00 mm`, temp `21.1 °C`.
- **Verdict & Scope of Evidence:**
  - Historical availability was empirically confirmed at the tested dates within the required period, including `1969-07-14` and `1994-10-04/05`.
  - **Continuous day-by-day completeness across the entire 1969–1994 interval has NOT yet been independently verified.**
  - **Dataset Identity:** The Open-Meteo documentation lists ERA5 (0.25°) and ERA5-Land (0.1°) as underlying reanalysis sources. However, the generic archive query does not explicitly declare the model variant in the response payload. Historical reanalysis dataset identity requires confirmation from the API response/model metadata before production ingestion.

### 2. NASA POWER API (`https://power.larc.nasa.gov/api/temporal/daily/point`)
- **Probe:** Queried `12.9716°N, 77.5946°E` for `1981-01-01` to `1981-01-02` (earliest known MERRA-2 date).
- **Result:** Connection timed out (`ConnectTimeout`).
- **Official Dataset Baseline:** NASA POWER meteorological parameters are derived from GMAO MERRA-2 assimilation, which strictly begins on **1981-01-01**.
- **Target Overlap Deficit:** Completely absent for `1969-07-14` through `1980-12-31` (11.5 years missing).
- **Verdict:** **BLOCKED** due to missing historical coverage for 1969–1980 and network timeout.

### 3. NOAA PSL / CPC Global Unified Precipitation
- **Probe:** Queried NOAA PSL HTTP catalog endpoints (`https://psl.noaa.gov/thredds/dodsC/Datasets/cpc_global_precip/`).
- **Result:** Connection timed out (`ConnectTimeout`).
- **Official Dataset Baseline:** NOAA CPC Global Daily Precipitation analysis begins in **1979-01-01**.
- **Target Overlap Deficit:** Completely absent for `1969-07-14` through `1978-12-31` (9.5 years missing). Contains precipitation only; temperature, humidity, and pressure are absent from the CPC precipitation product.
- **Verdict:** **BLOCKED** due to missing historical coverage for 1969–1978 and network timeout.

### 4. Copernicus Climate Data Store (CDS API)
- **Probe:** Evaluated direct access via `cdsapi`.
- **Result:**
  - `cds.climate.copernicus.eu` connection timed out (`ConnectTimeout`).
  - Access requires mandatory user registration, agreement to ECMWF/Copernicus license terms, and deployment of user-specific API keys (`~/.cdsapirc`).
  - Without interactive user credentials, automated machine-readable access is `CREDENTIAL_BLOCKED`.
- **Verdict:** **BLOCKED** for automated pipeline execution without external user credential provisioning.

### 5. IMD Historical Gridded Rainfall (0.25° × 0.25°)
- **Probe:** Queried IMD Pune gridded portal (`https://imdpune.gov.in`).
- **Result:** Connection timed out (`ConnectTimeout`), consistent with documented IP geolocation/firewall gating noted in `docs/DATA_SOURCES.md`.
- **Alternative Access:** The open-source Python library `imdlib` allows offline reading of IMD binary grid files (`.grd`) if downloaded out-of-band.
- **Documented Archive Availability:** 1901 to present.
- **Tested Availability:** Direct endpoint was unreachable; documented archive availability exists, but **continuous 1969–1994 completeness has not yet been independently verified**.
- **Variable Deficit:** Rainfall only. High-resolution surface pressure and relative humidity are not available at 0.25° resolution from IMD historical grids.
- **Verdict:** **FALLBACK CANDIDATE** (rainfall-only, requires offline batch transfer and completeness verification).

### 6. IMD National Data Centre API (`api.imd.gov.in`)
- **Probe:** Evaluated API endpoints.
- **Result:** Requires official government API tokens and organizational approvals (`CREDENTIAL_BLOCKED`).
- **Verdict:** **BLOCKED**.

### 7. OpenCity / KSNDMC Historical Rainfall
- **Inspection:** Inspected local repository tranches and OpenCity archives.
- **Result:** Data available only from 2015 to 2025 as monthly/annual administrative aggregates.
- **Verdict:** **BLOCKED** (zero overlap with 1969–1994).

---

## Temporal Coverage

| Source | Documented Archive Availability | Tested Dates Available | Continuous 1969–1994 Completeness Verified? | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Open-Meteo Historical Archive** | 1940-01-01 to Present | `1969-07-14/15`, `1994-10-04/05` | **NO** (Not yet independently tested day-by-day) | Empirically verified at test dates; continuous completeness unverified |
| **IMD 0.25° Gridded Rainfall** | 1901-01-01 to Present | None (Direct portal timed out) | **NO** (Not yet independently tested day-by-day) | Documented 1901–present; continuous 1969–1994 completeness unverified |
| **NOAA CPC Global Precipitation** | 1979-01-01 to Present | None (Timed out) | **NO** (Incomplete baseline, starts 1979) | Missing 1969–1978 (10 years) |
| **NASA POWER (MERRA-2)** | 1981-01-01 to Present | None (Timed out) | **NO** (Incomplete baseline, starts 1981) | Missing 1969–1980 (12 years) |
| **OpenCity / KSNDMC** | 2015-01-01 to 2025-12-31 | 2015–2025 summaries | **NO** (Starts 2015) | Zero overlap with target period |

---

## Spatial Coverage

### Open-Meteo Reanalysis (Documented Resolution)
- **Spatial Domain:** Global coverage, including Karnataka (11.5°N to 18.5°N, 74.0°E to 78.5°E).
- **Documented Grid Resolution:** 0.1° (~11 km) for ERA5-Land; 0.25° (~28 km) for atmospheric ERA5.
- **Intersection with Karnataka:**
  - Expected/theoretical coverage based on documented grid resolution; exact cell count and district intersection have not yet been computed.
  - At theoretical 0.1° resolution, the bounding box encompasses approximately 1,500 to 1,900 potential grid points, but actual intersection with the official Karnataka state polygon boundary has not been run in PostGIS.
- **District Representation:**
  - Expected/theoretical coverage suggests all 31 districts should intersect multiple grid points.
  - Point-sampling at district centroids, taluk centroids, or river gauge coordinates is technically supported by the API query mechanism, but actual spatial coverage across all 31 districts has not yet been computed via PostGIS intersection.

### IMD Gridded Rainfall
- **Spatial Domain:** Continental India (6.5°N to 38.5°N, 66.5°E to 100.0°E).
- **Documented Grid Resolution:** 0.25° × 0.25° (~27 km × 27 km).
- **Intersection with Karnataka:** Expected/theoretical coverage based on documented grid resolution; exact cell count and district intersection have not yet been computed.

---

## Variable Coverage

| Variable Required | Open-Meteo Archive | IMD Gridded | NASA POWER | NOAA CPC |
| :--- | :--- | :--- | :--- | :--- |
| **Precipitation** | Yes (`precipitation` in `mm`) | Yes (`rain` in `mm`) | Yes (`PRECTOTCORR` in `mm/day`) | Yes (`precip` in `mm/day`) |
| **Temperature** | Yes (`temperature_2m` in `°C`) | Separate 1.0° grid only | Yes (`T2M` in `°C`) | No |
| **Relative Humidity**| Yes (`relative_humidity_2m` in `%`) | No | Yes (`RH2M` in `%`) | No |
| **Surface Pressure** | Yes (`surface_pressure` in `hPa`)| No | Yes (`PS` in `kPa`) | No |
| **Wind Speed / Dir** | Yes (`wind_speed_10m`, `wind_direction_10m`) | No | Yes | No |

Open-Meteo is the only candidate whose API response demonstrated retrieval of **all four required variables** at a single endpoint for the tested historical dates.

---

## Data Semantics

In adherence to project architectural rules, data sources are explicitly classified:

1. **`OBSERVATION`**: Direct in-situ physical measurements recorded by instruments (e.g., CWC river stage gauges, KSNDMC telemetric rain gauges, IMD manual rain gauges).
2. **`REANALYSIS`**: Spatially and physically consistent global or regional numerical modeling reconstructions constrained by historical observational data assimilation (e.g., ECMWF ERA5, MERRA-2).
3. **`MODEL_OUTPUT`**: Numerical weather prediction (NWP) model runs or simulations that are not constrained by retrospective global reanalysis assimilation (e.g., GFS forecast runs, operational ECMWF past 7-day model runs).
4. **`FORECAST`**: Prospective forward-looking atmospheric model projections (e.g., Open-Meteo 7-day or 16-day forecast feeds).

### Candidate Classifications:
- **Open-Meteo Historical Archive:** **`REANALYSIS`** (ECMWF reanalysis). It must **NEVER** be labeled or stored as `OBSERVATION`.
- **IMD 0.25° Gridded Rainfall:** **`OBSERVATION`** (Objective spatial interpolation of ~6,000 rain gauge stations using Shepard's angular distance weighting method).
- **NASA POWER:** **`REANALYSIS`** (NASA GMAO MERRA-2 assimilation).
- **NOAA CPC:** **`OBSERVATION`** (Optimal interpolation of global rain gauge station network).

---

## Access and Reproducibility

### Open-Meteo Historical Archive API
- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **Protocol:** HTTP GET, JSON or FlatBuffers response.
- **Authentication:** None required for standard rate-limited access (up to 10,000 daily API calls for non-commercial research).
- **Reproducibility:** High for queried points; deterministic reanalysis values.
- **Terms / License:** Re-distributes ECMWF ERA5 data under Copernicus license terms; Open-Meteo API access is governed by CC-BY 4.0.

### IMD Gridded Rainfall
- **Protocol:** Binary file distribution (`.grd` format) or custom HTTP portal.
- **Authentication:** Captcha/portal-gated; direct HTTP from cloud/datacenter IP ranges is frequently timed out or firewalled.
- **Reproducibility:** High once raw binary files are acquired; lower for automated on-demand pipelines.
- **Terms / License:** Non-commercial research use; government data sharing policy.

---

## Access vs. Production Readiness

To avoid overstating empirical validation results, the following concepts are strictly separated:

1. **Public Endpoint Accessibility:** The Open-Meteo historical archive endpoint responds to HTTP requests without API keys or login credentials.
2. **Historical Date Availability:** The documented temporal range of the archive spans 1940 to present.
3. **Empirically Tested Data Retrieval:** Data retrieval was successfully demonstrated for specific sampled coordinates and dates (`1969-07-14` and `1994-10-04/05`).
4. **Continuous Temporal Completeness:** **NOT VERIFIED.** Independent verification of all 9,215 days between 1969 and 1994 has not been performed.
5. **Karnataka Spatial Coverage:** **NOT COMPUTED.** Theoretical coverage exists based on documented grid resolution, but exact PostGIS polygon intersections and district coverage counts have not been executed.
6. **Production-Scale Extraction Feasibility:** **NOT PROVEN.** Large-scale multi-decade batch extraction feasibility (handling rate limits, connection throttling, payload sizing, and retry robustness) has not been tested.

**Crucial Constraint:** Concepts 4, 5, and 6 cannot and must not be inferred solely from Concept 1, 2, or 3.

---

## Source Comparison

| Source | Documented Coverage | Stated Spatial Resolution | Variables | Access Method | Data Category | Tested at Target Dates? | Production Candidate Status | Current Blockers |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Open-Meteo Archive** | 1940–present | 0.1° / 0.25° | Precip, Temp, RH, Pressure, Wind | Open REST API (JSON) | **REANALYSIS** | **YES** (`1969`, `1994`) | **Candidate for further validation** (Not yet approved for ingestion) | Exact dataset variant unconfirmed; continuous completeness unverified. |
| **IMD Gridded Rainfall**| 1901–present | 0.25° (~25 km) | Rainfall only | Binary `.grd` via `imdlib` | **OBSERVATION** | **NO** (Endpoint timed out) | **Fallback for further validation** | Portal network-gated; missing non-precip variables; completeness unverified. |
| **Copernicus CDS** | 1940–present | 0.1° / 0.25° | Precip, Temp, RH, Pressure | Python `cdsapi` | **REANALYSIS** | **NO** (Timed out) | Blocked | Requires user API keys and license agreement; portal timeout. |
| **NASA POWER** | 1981–present | 0.5° (~50 km) | Precip, Temp, RH, Pressure | REST API (JSON) | **REANALYSIS** | **NO** (Timed out) | Blocked | Missing 1969–1980; network timeout. |
| **NOAA CPC Global** | 1979–present | 0.5° (~50 km) | Precip only | OPeNDAP / THREDDS | **OBSERVATION** | **NO** (Timed out) | Blocked | Missing 1969–1978; precip only; network timeout. |
| **IMD NDC API** | Station-specific | Station | Station-dependent | REST API | **OBSERVATION** | **NO** | Blocked | Requires government credentials (`CREDENTIAL_BLOCKED`). |
| **OpenCity / KSNDMC** | 2015–2025 | District-aggregate | Rainfall only | CSV download | **OBSERVATION** | **NO** | Blocked | Zero overlap with target period (starts 2015). |

---

## Primary Candidate

### **Open-Meteo Historical Weather Archive API**

#### Status:
Selected as the **Primary Candidate for further validation** based on preliminary empirical probes.
> [!IMPORTANT]
> Designation as "primary candidate" means this source is currently selected for further technical validation based on the evidence collected. It does **NOT** mean that production ingestion has already been approved.

#### Supporting Evidence:
1. **Preliminary Date Retrieval:** Data retrieval succeeded for the earliest target flood date (`1969-07-14`) and latest target flood date (`1994-10-04/05`).
2. **Variable Availability:** Delivers precipitation (`mm`), surface temperature (`°C`), relative humidity (`%`), and surface pressure (`hPa`) in a single JSON response.
3. **Machine-Readable API:** Public REST API returning structured data without credential gating.
4. **Hourly Resolution:** Allows flexible aggregation to daily and multi-day antecedent windows.

#### Remaining Uncertainties:
- Exact underlying reanalysis model (ERA5 vs. ERA5-Land) must be confirmed.
- Continuous day-by-day completeness across 1969–1994 remains to be verified.
- Production-scale extraction feasibility under rate limits must be tested.

---

## Fallback Candidate

### **IMD 0.25° Gridded Daily Rainfall (`imdlib` / Offline Batch)**

#### Status:
Selected as the **Fallback Candidate for secondary validation and cross-checking**.
> [!NOTE]
> Designation as "fallback candidate" indicates this source is selected for secondary validation or cross-checking against reanalysis precipitation. Continuous 1969–1994 completeness has not yet been independently verified.

#### Supporting Evidence:
1. **Observational Heritage:** Interpolated directly from official IMD rain gauge stations across India.
2. **Documented Span:** Archive documentation spans 1901 to present.
3. **Hydrological Standard:** Widely cited benchmark for Indian monsoon precipitation.

#### Remaining Uncertainties:
- Direct HTTP portal access is network-gated; requires out-of-band binary file staging.
- Lacks surface temperature, humidity, and pressure at 0.25° resolution.
- Continuous completeness across 1969–1994 must be audited.

---

## Blocked Sources

1. **NASA POWER:** Blocked due to historical inception date (1981-01-01), leaving the 1969–1980 period (11.5 years of critical historical flood events) completely unrepresented, plus connection timeout.
2. **NOAA CPC Global Precipitation:** Blocked due to historical inception date (1979-01-01), omitting 1969–1978, and lack of non-precipitation atmospheric variables.
3. **Copernicus CDS Direct API:** Blocked for automated pipelines due to mandatory interactive account registration, user license acceptance, and API key provisioning (`CREDENTIAL_BLOCKED`).
4. **IMD National Data Centre API (`api.imd.gov.in`):** Blocked due to restricted access requiring institutional government credentials.
5. **OpenCity / KSNDMC Rainfall:** Blocked due to zero temporal overlap with the target historical period (records start in 2015).

---

## Phase 3.7B Prerequisites

Before production ingestion can be considered or approved, Phase 3.7B must perform:

1. **Exact dataset/model identity verification:** Confirm whether the Open-Meteo archive API response delivers ERA5 (0.25°) or ERA5-Land (0.1°) for each requested variable.
2. **Continuous temporal completeness test over the required historical period:** Execute systematic temporal sampling across 1969–1994 to verify there are no missing blocks, gaps, or discontinuities.
3. **Karnataka spatial coverage/grid intersection verification:** Compute the actual spatial intersection of the source grid against the official PostGIS Karnataka state and district boundaries (`admin_boundaries`).
4. **Missing-value/null analysis:** Quantify null, missing, or fill-value rates in the returned time series.
5. **Unit and timestamp validation:** Empirically verify timestamp timezone semantics (UTC vs. IST) and ensure units match database schema definitions.
6. **Reproducible extraction test:** Verify that repeated extractions for identical coordinate/time queries produce bitwise or numerical identical outputs.
7. **API/request-volume feasibility test using a small representative workload:** Profile latency, rate limits, and network stability using a small representative batch.
8. **Cross-check of historical precipitation against an independent source where available:** Compare reanalysis precipitation against an independent observational record (e.g. IMD gridded or CWC station logs) for a selected historical storm event.
