# Phase 3.7B — Gate 4 Meteorological Value Semantics & Extraction Feasibility

## Objective

Validate the physical meaning, numerical consistency, multi-run reproducibility, spatial validity, multi-location batching feasibility, and request latency of Open-Meteo Historical Weather API `models=era5` data before any historical dataset is extracted or ingested into FloodPulse.

This is a validation-only phase. No PostgreSQL records are modified, no database migrations are created, no production ingestion pipelines are written, and no ML datasets are generated.

---

## Official Documentation Evidence

### Precipitation Semantics
- **Parameter Definition:** According to Open-Meteo API documentation, `hourly=precipitation` represents the total precipitation (rain, showers, snow) accumulated during the preceding one-hour interval.
- **Units:** When queried with `precipitation_unit=mm`, values are returned in millimeters ($mm$, equivalent to $kg/m^2$).
- **Accumulation Semantics:** The variable is **interval-based** (hourly accumulation of the preceding hour), **not** a continuous running cumulative counter from the start of the year or simulation.
- **Aggregation Validity:** Because each hourly value represents an interval depth, summing hourly values over a 24-hour period ($00:00$ to $23:00$) is physically and mathematically valid to calculate daily cumulative rainfall ($mm/day$).
- **Missing Value Representation:** Missing or unavailable measurements are represented as JSON `null`.
- **Value Bounds:** Precipitation is strictly non-negative ($\ge 0.0\text{ mm}$).

### Timestamp Semantics
- **Format:** Timestamps are formatted as ISO 8601 strings without an inline timezone offset (e.g., `YYYY-MM-DDTHH:MM`).
- **Timezone Parameter:**
  - `timezone=UTC`: Timestamps reflect Coordinated Universal Time ($UTC+0$), and `utc_offset_seconds` returns `0`.
  - `timezone=Asia/Kolkata`: Timestamps are shifted by $+5.5\text{ hours}$ ($UTC+05:30$), and `utc_offset_seconds` returns `19800`.
- **Calendar Window Shift:** Changing the timezone does not alter the underlying physical value at any given instant in time, but it **shifts the 24-hour calendar window** by the timezone offset. Querying `1994-10-04` in IST retrieves the 24 hours between `1994-10-03T18:30 UTC` and `1994-10-04T17:30 UTC`.
- **Normalization Rule:** To prevent calendar-boundary distortion, time-shift artifacts, and daylight-saving ambiguity, FloodPulse ingestion pipelines must strictly enforce `timezone=UTC` for all historical extraction and database storage.

### Request/Batch Constraints
- **Documented Rate Limits:**
  - Open-Meteo non-commercial tier permits up to **10,000 daily API requests** and up to **10 concurrent requests**.
  - Hourly rate limit: up to 5,000 requests per hour.
  - Minute rate limit: up to 600 requests per minute.
- **Multi-Location Batching:** The API documentation states that multiple coordinates can be passed as comma-separated lists in the `latitude` and `longitude` query parameters (e.g., `latitude=12.5,13.0&longitude=76.0,76.5`), returning a JSON array of location objects.

---

## Empirical Probes

### Precipitation Probe
- **Query:** Bengaluru Urban `(12.9716°N, 77.5946°E)` for `1994-10-04` (24 hourly records) with `models=era5`.
- **Observations:**
  - Minimum hourly value: `0.0 mm`
  - Maximum hourly value: `1.0 mm`
  - 24-hour cumulative sum: `8.00 mm`
  - Negative values: `0`
  - Null values: `0`

### UTC vs IST Probe
- **Query:** Identical coordinate `(12.9716°N, 77.5946°E)` and date `1994-10-04` queried with `timezone=UTC` vs. `timezone=Asia/Kolkata`.
- **Results:**
  - **UTC Query:** `utc_offset_seconds: 0`, timestamps `1994-10-04T00:00` to `23:00`. Cumulative rainfall = `8.00 mm`.
  - **IST Query:** `utc_offset_seconds: 19800`, timestamps `1994-10-04T00:00` to `23:00`. Cumulative rainfall = `8.20 mm`.
  - **Explanation:** The 0.20 mm difference is caused entirely by the 5.5-hour calendar window offset between IST and UTC (rainfall that fell between 18:30 and 23:59 UTC on 1994-10-03 is included in the 1994-10-04 IST window, while rainfall between 18:30 and 23:59 UTC on 1994-10-04 is excluded).
  - **Normalization Decision:** Store all timestamps and aggregations strictly in UTC.

### Reproducibility Probe
- **Setup:** 3 different Karnataka grid cells across 2 historical dates (`1969-07-14` and `1994-10-04`), repeated 3 times each with a 200 ms delay (18 total requests).
  1. Interior Cell: `(14.25°N, 76.50°E)`
  2. North-West Cell: `(15.75°N, 74.50°E)`
  3. Southern Cell: `(12.50°N, 76.75°E)`
- **Results:**
  - In all 18 runs, repeated requests returned **identical** values.
  - Exact floating-point equality was observed across all 3 repeats for both precipitation and temperature:
    - Interior 1969: `run0 == run1 == run2` (True)
    - Interior 1994: `run0 == run1 == run2` (True)
    - North-West 1969: `run0 == run1 == run2` (True)
    - North-West 1994: `run0 == run1 == run2` (True)
    - South 1969: `run0 == run1 == run2` (True)
    - South 1994: `run0 == run1 == run2` (True)

### Spatial Value Probe
- **Setup:** Probed 5 representative spatial regimes for `1994-10-04` to `1994-10-05` (48 hours) across 4 variables (`precipitation`, `temperature_2m`, `relative_humidity_2m`, `surface_pressure`):

| Spatial Regime | Coords (Lat, Lon) | Precip Range ($mm$) | Temp Range ($^\circ\text{C}$) | RH Range ($\%$) | Surface Pressure ($hPa$) | Elevation ($m$) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interior Karnataka** | (14.25, 76.50) | [0.0, 1.2] | [20.7, 27.5] | [69, 96] | [934.9, 939.5] | 647 |
| **Northern Karnataka** | (18.25, 77.25) | [0.0, 1.1] | [22.2, 28.7] | [64, 96] | [941.3, 947.3] | 568 |
| **Southern Karnataka** | (11.75, 76.75) | [0.0, 1.7] | [19.0, 27.1] | [62, 95] | [914.4, 918.3] | 857 |
| **Coastal Karnataka** | (13.25, 74.75) | [0.0, 3.5] | [24.4, 28.2] | [79, 94] | [1005.1, 1009.1] | 16 |
| **District Boundary** | (12.50, 76.75) | [0.0, 5.5] | [20.6, 27.6] | [63, 93] | [927.1, 931.0] | 730 |

- **Physical Plausibility Observations:**
  - Surface pressure accurately reflects topographic elevation: sea-level coastal cell shows $\sim 1005\text{--}1009\text{ hPa}$, while high-elevation southern plateau (857 m) shows $\sim 914\text{--}918\text{ hPa}$.
  - Relative humidity stays strictly within physical bounds ($62\%\text{ to }96\%$).
  - Precipitation values are strictly non-negative ($\ge 0.0\text{ mm}$).
  - Temperature shows realistic diurnal cycles ($19.0^\circ\text{C to }28.7^\circ\text{C}$).

### Multi-location Probe
- **Batch 1 (5 Locations):** Queried 5 coordinates in a single HTTP GET request.
  - HTTP Status: `200 OK`
  - Latency: `1.220 s`
  - Response Structure: A JSON **array of 5 objects**, each containing its own coordinates, elevation, units, and hourly arrays.
  - Coordinate Preservation: All 5 locations were correctly returned with distinct elevation and time series.
- **Batch 2 (10 Locations):** Queried 10 coordinates in a single HTTP GET request.
  - HTTP Status: `200 OK`
  - Latency: `1.224 s`
  - Response Structure: A JSON **array of 10 objects**.
  - Payload Size: 10,090 bytes.

### Request Feasibility Probe
- **Workload:** 12 sequential requests with 100 ms spacing across different Karnataka coordinates.
- **Metrics:**
  - Total requests: 12
  - HTTP failures: **0**
  - Timeouts / Retries: **0**
  - Minimum latency: **0.793 s**
  - Maximum latency: **1.435 s**
  - Average latency: **1.060 s**
  - Average payload size: **1,688 bytes** (1-day, 2 variables)

### Independent Cross-Check
- **Candidate Sources Investigated:**
  - IMD Gridded 0.25° Daily Rainfall (`imdpune.gov.in`)
  - CWC River Station Precipitation Records
  - NOAA CPC Global Precipitation
- **Access Findings:**
  - IMD Pune portal is network-gated from cloud/datacenter IP ranges (`ConnectTimeout`).
  - NOAA CPC catalog timed out (`ConnectTimeout`).
  - Existing CWC database records in FloodPulse contain stage/discharge for 2018–2024 only; no historical precipitation records exist in the database for 1969–1994.
- **Finding:**
  > *"Independent cross-check could not be completed from an accessible authoritative dataset during this gate."*

---

## Results Summary

| Validation Check | Target Metric | Empirical Result | Status |
| :--- | :--- | :--- | :--- |
| **Precipitation Unit** | `precipitation_unit=mm` | Returned in millimeters ($mm$) | **PASS** |
| **Precipitation Bounds**| No negative values | Min value: $0.0\text{ mm}$, zero negative values | **PASS** |
| **Precipitation Accumulation** | Interval-based vs. cumulative | Interval-based (hourly depth of preceding hour) | **PASS** |
| **Timestamp Alignment** | UTC vs. IST consistency | UTC offset = 0s; IST offset = +19800s; values shift with calendar window | **PASS (Enforce UTC)** |
| **Reproducibility** | Repeated identical queries | 100% exact floating-point equality (18/18 tests) | **PASS** |
| **Physical Plausibility** | Values within physical ranges | T: 19–29°C, RH: 62–96%, SP: 914–1009 hPa (elevation-consistent) | **PASS** |
| **Multi-Location Batching** | Multi-point query support | Supported up to 10 points tested, returns JSON array | **PASS** |
| **Request Latency** | Sequential request stability | Avg latency: 1.060s, 0 errors, 0 timeouts | **PASS** |
| **Independent Cross-Check**| Comparison against independent source | External archives network-gated; CWC DB lacks 1969–1994 precip | **PENDING** |

---

## Data Quality Findings

- **Observed:**
  - 100% valid finite floating-point numbers for all probed ERA5 requests.
  - Precipitation $\ge 0.0\text{ mm}$.
  - Surface pressure accurately scales with digital elevation model values returned by the API.
  - Multi-location responses return distinct, uncorrupted arrays per location.
- **Missing / Null:**
  - **Zero** null values observed across all tested `models=era5` variables (`precipitation`, `temperature_2m`, `relative_humidity_2m`, `surface_pressure`).
- **Invalid:**
  - **Zero** invalid, negative, or physically impossible values detected.
- **Not Tested:**
  - Exhaustive day-by-day scanning of all 9,215 days for all 324 Karnataka cells.
  - Large-scale batching beyond 10 locations per request.

---

## Extraction Feasibility

- **Technically Possible:** Multi-location batch extraction (passing up to 10 coordinates per HTTP request) is natively supported by the Open-Meteo archive endpoint and reduces request volume by up to 10x.
- **Empirically Tested:** Batches of 5 and 10 coordinates were empirically tested and confirmed to return correctly formatted JSON arrays with identical per-location time series at $\sim 1.2\text{ s}$ latency.
- **Production-Scale Not Yet Validated:**
  - Extracting 324 Karnataka grid cells across multi-decade windows (e.g. 25 years) will generate substantial data volume.
  - At 10 locations per request, a full-year extraction requires 33 API calls per year ($33 \times 26\text{ years} \approx 858\text{ total API requests}$).
  - 858 requests is well within Open-Meteo's 10,000 daily request limit, but requires client-side rate limiting, retry backoff, and local disk staging to guard against network interruptions.

---

## Gate 4 Decision

### **Decision: CONDITIONALLY VERIFIED**

> [!NOTE]
> **Rationale for Status:**
> All technical, numerical, semantic, reproducibility, and batching criteria for Open-Meteo `models=era5` were successfully verified.
> The status is designated as **CONDITIONALLY VERIFIED** rather than fully verified because the **independent precipitation cross-check against an authoritative ground-truth source (e.g. IMD gridded rainfall) could not be completed** due to network gating of external government data portals from the test environment.

---

## Remaining Risks

1. **Reanalysis vs. Ground-Truth Bias:** ERA5 is an atmospheric numerical reanalysis model, not a direct rain-gauge measurement. While physically consistent, reanalysis precipitation may underestimate localized convective cloudbursts or overestimate light orographic drizzle along the Western Ghats.
2. **Offline Cross-Validation Dependency:** Formal cross-validation against IMD 0.25° gridded rainfall requires out-of-band acquisition of IMD binary `.grd` files.
3. **Public API Service Availability:** Relying on a third-party public API endpoint (`archive-api.open-meteo.com`) exposes historical ingestion pipelines to potential DNS, rate-limit, or endpoint changes if requests are not properly cached and staged locally.

---

## Phase 3.7B Final Prerequisites

Before historical extraction or ingestion code can be written:

1. **Disk Staging Architecture:** Design a local raw data staging directory (e.g. `data/raw/era5/`) to store raw JSON/Parquet payloads before database loading, ensuring extraction is decoupled from database ingestion.
2. **Batch Ingestion Pipeline Design:**
   - Enforce `models=era5`.
   - Enforce `timezone=UTC`.
   - Use multi-location batches of 5 to 10 coordinates per call.
   - Implement rate throttling (maximum 2 requests per second, exponential backoff on HTTP 429/503).
3. **Out-of-Band IMD Cross-Check Plan:** Establish a procedure to cross-validate selected historical flood event rainfall totals against IMD historical daily rainfall data once offline files are available.
4. **Target Schema Definition:** Define the target PostgreSQL table schema (with `source_type = 'REANALYSIS'`) to prevent mixing reanalysis model estimates with real gauge observations.
