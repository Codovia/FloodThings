# Phase 3.7B — Gate 2 Temporal Completeness

## Objective

Determine whether explicitly requested Open-Meteo `models=era5` historical data can be retrieved continuously across the complete historical flood-label period (1969-07-14 through 1994-10-06), evaluate boundary transitions (year-end, decade, era, and leap-year days), and detect any missing timestamps, duplicate records, or null/missing values in the core meteorological variables.

This is a validation task only. No database modifications, migrations, ingestion pipelines, or ML datasets are created.

---

## Sampling Method

To rigorously assess temporal continuity without overloading the Open-Meteo public API or downloading unnecessary multi-decade payloads, a stratified multi-era sampling strategy was implemented across the 26-year target interval (1969–1994):

1. **Stratification by Historical Eras:**
   - **Era 1 (1969–1975):** Earliest target flood event (`1969-07-14`), mid-monsoon and post-monsoon samples, year-end transition (`1970->1971`), and era boundary (`1975->1976`).
   - **Era 2 (1976–1985):** Monsoon samples, year-end transition (`1979->1980`), leap-year continuity (`1980-02-28` to `1980-03-01` including February 29), mid-monsoon, post-monsoon, and era boundary (`1985->1986`).
   - **Era 3 (1986–1994):** Monsoon onset/peak samples, leap-year continuity (`1988-02-28` to `1988-03-01`), decade boundary (`1989->1990`), and latest target flood event (`1994-10-04` to `1994-10-06`).
2. **Boundary Stress Testing:**
   - Every transition window spanned multiple days (3 to 4 days, 72 to 96 hours) across calendar year boundaries (Dec 30 to Jan 2) to test for index discontinuities or date-wrapping errors.
   - Leap day continuity was specifically tested for 1980 and 1988 to verify correct handling of February 29 in reanalysis indexing.
3. **Hourly Continuity Verification:**
   - For every probe, expected hours were computed strictly as `(end_date - start_date + 1) * 24`.
   - Timestamps were checked for strict hourly progression ($t_{i+1} - t_i = 1\text{ hour}$).
   - Set difference between expected timestamp sequence and returned sequence was computed to detect missing hours.
   - Duplicate timestamp detection checked `len(timestamps) == len(set(timestamps))`.

---

## Exact API Parameters

All probes were executed against the Open-Meteo Historical Weather API endpoint:
- **Base URL:** `https://archive-api.open-meteo.com/v1/archive`
- **Model:** `models=era5` (Explicitly selected)
- **Timezone:** `timezone=UTC`
- **Units:** `precipitation_unit=mm`, `temperature_unit=celsius`
- **Variables:** `hourly=precipitation,temperature_2m,relative_humidity_2m`
- **Coordinates:** Bengaluru Urban `(latitude=12.9716, longitude=77.5946)`

---

## Tested Periods

Seventeen (17) representative temporal windows were probed:

| Probe ID | Era | Description / Target Event | Requested Start | Requested End | Expected Days | Expected Hours |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P01** | Era 1 (1969–1975) | Earliest IFI flood event in Karnataka | 1969-07-14 | 1969-07-16 | 3 | 72 |
| **P02** | Era 1 (1969–1975) | Year-end boundary transition (1970->1971) | 1970-12-30 | 1971-01-02 | 4 | 96 |
| **P03** | Era 1 (1969–1975) | Mid-monsoon seasonal sample (1972) | 1972-07-15 | 1972-07-17 | 3 | 72 |
| **P04** | Era 1 (1969–1975) | Post-monsoon seasonal sample (1974) | 1974-10-10 | 1974-10-12 | 3 | 72 |
| **P05** | Era 1 (1969–1975) | Era boundary transition (1975->1976) | 1975-12-30 | 1976-01-02 | 4 | 96 |
| **P06** | Era 2 (1976–1985) | Monsoon seasonal sample (1977) | 1977-08-15 | 1977-08-17 | 3 | 72 |
| **P07** | Era 2 (1976–1985) | Year-end boundary transition (1979->1980) | 1979-12-30 | 1980-01-02 | 4 | 96 |
| **P08** | Era 2 (1976–1985) | Leap-year February 29 continuity (1980) | 1980-02-28 | 1980-03-01 | 3 | 72 |
| **P09** | Era 2 (1976–1985) | Mid-monsoon seasonal sample (1982) | 1982-07-20 | 1982-07-22 | 3 | 72 |
| **P10** | Era 2 (1976–1985) | Post-monsoon seasonal sample (1984) | 1984-10-05 | 1984-10-07 | 3 | 72 |
| **P11** | Era 2 (1976–1985) | Era boundary transition (1985->1986) | 1985-12-30 | 1986-01-02 | 4 | 96 |
| **P12** | Era 3 (1986–1994) | Monsoon seasonal sample (1987) | 1987-07-12 | 1987-07-14 | 3 | 72 |
| **P13** | Era 3 (1986–1994) | Leap-year February 29 continuity (1988) | 1988-02-28 | 1988-03-01 | 3 | 72 |
| **P14** | Era 3 (1986–1994) | Decade boundary transition (1989->1990) | 1989-12-30 | 1990-01-02 | 4 | 96 |
| **P15** | Era 3 (1986–1994) | Monsoon peak seasonal sample (1991) | 1991-08-01 | 1991-08-03 | 3 | 72 |
| **P16** | Era 3 (1986–1994) | Monsoon onset seasonal sample (1993) | 1993-06-15 | 1993-06-17 | 3 | 72 |
| **P17** | Era 3 (1986–1994) | Latest IFI flood event in Karnataka | 1994-10-04 | 1994-10-06 | 3 | 72 |

---

## Results

| Probe ID | HTTP Status | Returned Start | Returned End | Returned Hours | Expected Hours | Missing Hours | Duplicate Hours |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P01** | `200` | 1969-07-14T00:00 | 1969-07-16T23:00 | 72 | 72 | 0 | 0 |
| **P02** | `200` | 1970-12-30T00:00 | 1971-01-02T23:00 | 96 | 96 | 0 | 0 |
| **P03** | `200` | 1972-07-15T00:00 | 1972-07-17T23:00 | 72 | 72 | 0 | 0 |
| **P04** | `200` | 1974-10-10T00:00 | 1974-10-12T23:00 | 72 | 72 | 0 | 0 |
| **P05** | `200` | 1975-12-30T00:00 | 1976-01-02T23:00 | 96 | 96 | 0 | 0 |
| **P06** | `200` | 1977-08-15T00:00 | 1977-08-17T23:00 | 72 | 72 | 0 | 0 |
| **P07** | `200` | 1979-12-30T00:00 | 1980-01-02T23:00 | 96 | 96 | 0 | 0 |
| **P08** | `200` | 1980-02-28T00:00 | 1980-03-01T23:00 | 72 | 72 | 0 | 0 |
| **P09** | `200` | 1982-07-20T00:00 | 1982-07-22T23:00 | 72 | 72 | 0 | 0 |
| **P10** | `200` | 1984-10-05T00:00 | 1984-10-07T23:00 | 72 | 72 | 0 | 0 |
| **P11** | `200` | 1985-12-30T00:00 | 1986-01-02T23:00 | 96 | 96 | 0 | 0 |
| **P12** | `200` | 1987-07-12T00:00 | 1987-07-14T23:00 | 72 | 72 | 0 | 0 |
| **P13** | `200` | 1988-02-28T00:00 | 1988-03-01T23:00 | 72 | 72 | 0 | 0 |
| **P14** | `200` | 1989-12-30T00:00 | 1990-01-02T23:00 | 96 | 96 | 0 | 0 |
| **P15** | `200` | 1991-08-01T00:00 | 1991-08-03T23:00 | 72 | 72 | 0 | 0 |
| **P16** | `200` | 1993-06-15T00:00 | 1993-06-17T23:00 | 72 | 72 | 0 | 0 |
| **P17** | `200` | 1994-10-04T00:00 | 1994-10-06T23:00 | 72 | 72 | 0 | 0 |
| **TOTAL**| **100% (17/17)** | — | — | **1,344** | **1,344** | **0** | **0** |

---

## Missing/Null Analysis

For all 1,344 retrieved hourly records across the 17 probe periods:

| Variable | Total Expected Values | Populated Values | Null / Missing Count | Null Rate (%) |
| :--- | :--- | :--- | :--- | :--- |
| `precipitation` | 1,344 | 1,344 | **0** | **0.00%** |
| `temperature_2m` | 1,344 | 1,344 | **0** | **0.00%** |
| `relative_humidity_2m` | 1,344 | 1,344 | **0** | **0.00%** |

### Boundary Transition Findings:
1. **Year-End Transitions:** All five tested year-end boundaries (1970/1971, 1975/1976, 1979/1980, 1985/1986, 1989/1990) returned continuous 96-hour series from `12-30T00:00` to `01-02T23:00` without any timestamp dropouts or indexing artifacts.
2. **Leap-Year Continuity:** Both leap-year transitions (1980 and 1988) correctly included all 24 hours of February 29 (`1980-02-29T00:00` through `23:00`, `1988-02-29T00:00` through `23:00`) before advancing to March 1.
3. **Monsoon Peaks & Extremes:** Monsoon queries consistently yielded physically plausible rainfall pulses (e.g., up to 4.2 mm/hr in active monsoon windows) and realistic diurnal temperature and relative humidity cycles (humidity ranging from 65% to 99% during monsoon periods).

---

## Continuity Assessment

> [!IMPORTANT]
> **Scope of Verification:**
> Sampled temporal availability was successfully verified across all 17 representative probe windows spanning 1969 through 1994 (1,344 hourly records with zero missing hours, zero duplicate hours, and zero null values).
> **Full day-by-day completeness across all 9,215 days of the entire 1969–1994 interval remains unverified.**

The empirical findings confirm that:
- The Open-Meteo `era5` backend reliably maintains historical data indexing across the late 1960s, 1970s, 1980s, and 1990s.
- No systematic temporal barriers exist at decade boundaries, year-end boundaries, or leap days.
- When explicitly requested with `models=era5`, precipitation, temperature, and relative humidity can be consistently retrieved across these historical eras.

---

## Limitations

1. **Unprobed Days:** The 17 probe windows encompass 56 total calendar days (1,344 hours), representing approximately 0.6% of the 9,215 calendar days in the 1969–1994 target period. While no structural gaps were detected at major calendar transitions, intermittent single-day outages or localized missing hours on unprobed dates cannot be ruled out without a full-period completeness scan.
2. **Single Spatial Location:** These continuity probes were executed at a single representative coordinate (Bengaluru Urban). Spatial variation in missingness across other Karnataka coordinates was not evaluated in this gate.
3. **Rate Limits & Batch Scaling:** Probes were run sequentially with small delays. Full multi-decade batch extraction will require rate-limit handling (staying within the 10,000 requests/day free tier) and robust exponential backoff.

---

## Gate 3 Prerequisites

Before proceeding to any production ingestion pipeline design, Gate 3 must perform:

1. **Karnataka Spatial Coverage & PostGIS Grid Intersection:**
   - Construct the theoretical 0.25° ERA5 grid in PostGIS across the Karnataka bounding box (11.5°N–18.5°N, 74.0°E–78.5°E).
   - Intersect the grid with official Karnataka state and district boundaries (`admin_boundaries`).
   - Determine the exact number of intersecting grid cells per district across all 31 districts.
2. **Spatial Missingness Check:**
   - Verify that ERA5 grid points along coastal (Arabian Sea) and state boundary edges return valid terrestrial values without offshore null masks.
3. **Unit and Timestamp Validation:**
   - Confirm UTC vs. IST timestamp alignment against local diurnal cycles.
   - Verify precipitation accumulation semantics (hourly flux vs. cumulative).
4. **Reproducible Extraction & Batch Sizing:**
   - Test multi-location extraction batching to establish optimal chunk sizes and request concurrency.
