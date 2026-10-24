# Open-Meteo weather contract and Home hourly forecast

This is point weather-model output. It does not establish station observations,
flood predictions, flood thresholds or warnings. The public provider is
[Open-Meteo](https://open-meteo.com/en/docs), attributed CC BY 4.0; requested
coordinates and returned model-grid coordinates retain separate meanings.

## Diagnosis, before editing

Baseline branch `feature/karnataka-data-foundation`, HEAD
`8e26fa965338eeff5e84847efa733c96f38e077d`. Unrelated modified
`backend/.env.example` and untracked `QandA.md` were preserved.

The retained earlier HTTP 503 body said “Weather provider returned incomplete or
invalid data.” Inspection of the old handler places that message in the JSON
decoding/validation exception path: FastAPI generated that 503. It does not
prove an Open-Meteo HTTP 503 or provider outage. The old upstream response and
specific validator exception were not retained. The precise offending field and
whether an intermediary returned invalid content remain **unresolved**; a
midnight/cache explanation would be speculation.

On 2026-10-13, the original request and original parser succeeded for the reviewed
Kundapur point, followed by HTTP 200 from the unchanged internal backend. The
extended documented request also returned HTTP 200. No legacy-name mismatch was
observed: `temperature_2m`, `relative_humidity_2m`, `precipitation`, `weather_code`
and `wind_speed_10m` were all present and non-null. Existing code requested only
the first three and supplied no hourly series. Its strict indexing rejected
omitted current fields and its generic error messages concealed precise causes.
Home depended on daily totals and required temperature before showing any current
field. These demonstrated contract/presentation limitations are repaired;
an unknown historical failure is not asserted to be reproduced or solved.

## Parameters actually tested

Official endpoint: `https://api.open-meteo.com/v1/forecast`.
Coordinates were read from retained verified directory row
`udupi-admin:municipality:kundapur`, not newly geocoded or guessed:
latitude **13.6250993**, longitude **74.6915722**. Source:
[OpenStreetMap node 245623778](https://www.openstreetmap.org/node/245623778),
version 17; mapped settlement point, not a station or municipal boundary.

```text
latitude=13.6250993
longitude=74.6915722
current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m
hourly=precipitation
daily=precipitation_sum,temperature_2m_max,temperature_2m_min,weather_code
timezone=Asia/Kolkata
forecast_days=7
temperature_unit=celsius
precipitation_unit=mm
```

The original request omitted `hourly` and the last two current variables. Both
requests used ISO 8601 timestamps, the default; unixtime was not requested. Seven
days preserve Weather & AI compatibility. Returned grid: **13.602812, 74.73877**.
Original/extended bodies: **892 / 5108 bytes**. HTTP headers showed JSON and
successful response dates; no 429/503/intermediary failure occurred during these
live checks. Returned objects: `current`, `current_units`, `hourly`, `hourly_units`,
`daily`, `daily_units`. All 168 hourly precipitation entries and seven daily rows
were present. Units: current time `iso8601`, interval `seconds`, temperature `°C`,
humidity `%`, precipitation `mm`, weather code `wmo code`, wind `km/h`; hourly
time `iso8601` and precipitation `mm`; daily precipitation `mm` and temperatures
`°C`. No current field was missing/null in the live extended sample. Forecast
issuance and station-observation times are not supplied by this endpoint.

## Validation and failures

`backend/app/weather.py` normalizes current fields and the seven daily rows;
`fetch_weather` owns the single bounded provider call for default and selected
points. The selected-point wrapper preserves requested position and unavailable
flood prediction. Requests have a ten-second deadline; no backend automatic retry
or archive/database side effect is added.

Supported current fields may be omitted/null without erasing other valid fields;
normalized missing values stay null and `current.field_status` records them.
Present values require compatible units, numeric ranges and finite numbers.
Current valid time and preceding precipitation start/end retain explicit IST
offsets. Current WMO condition is separate from the daily most-severe code.
No unsupported field is silently mapped to a different variable. An omitted
requested field means missing, not proven unsupported. Invalid timing, units or
values remain response-validation failures. Existing daily ordering/week,
coordinate and all-unavailable checks remain intact.

`hourly_precipitation` carries `status`, `message`, IST timezone, millimetres,
3600-second duration, `preceding_hour` semantics, source and explicit interval
start/end records. The parser bounds the series at 168 entries, validates array
length, local-hour alignment and strict timestamp ordering, and preserves nulls.
A missing/invalid hourly series has a separate unavailable reason and no invented
intervals; it does not discard independently valid current or daily values.
A gap or null can remain in normalized evidence but fails any window containing
it. The general response status retains the existing current/daily coverage
meaning; hourly and optional-current availability must be inspected separately.

Failures preserve the public HTTP 503 unavailable contract while adding
`failure_kind`, `upstream_status`, `retry_after_seconds` and the validation reason:

| Evidence | Category | Automatic session retry |
| --- | --- | --- |
| Connection/transport failure | `network_failure` | bounded |
| Ten-second backend / fifteen-second browser deadline | `timeout` | bounded |
| Upstream HTTP 429 | `rate_limited` | bounded, respect Retry-After |
| Upstream HTTP 5xx, including 503 | `provider_unavailable` | bounded, respect Retry-After |
| Other rejected upstream HTTP request | `provider_http_error` | manual |
| Successful HTTP, invalid JSON/schema/units/timing | `invalid_response` | manual |
| Optional requested field omitted/null | field `missing` | retain other values |
| Old/failed cached retrieval | frontend `stale` | never show as live Home current |

An upstream HTTP status reports what the client received at the configured
endpoint; it cannot by itself establish whether an intermediary or publisher
originated the response. Failures have no successful retrieval clock or fallback
measurements. Retry-After supports seconds and HTTP dates and propagates through
FastAPI. The shared browser session makes at most three consecutive transient
attempts with 30/60-minute backoff or longer source guidance. Rerenders, route
changes at unchanged coordinates and simultaneous manual/automatic triggers do
not duplicate requests. Coordinate changes cancel and discard old-location data.
Hidden/offline sessions pause. Existing six-hour retrieval cadence and 90-minute
current-validity cutoff remain; use manual refresh when current estimates expire.
Weather & AI can retain explicitly stale prior readings; Home suppresses them.

## Deterministic 24-full-hour calculation

The [official variable table](https://open-meteo.com/en/docs) defines hourly
`precipitation` as a preceding-hour sum. `assessNext24Rainfall(data, referenceMs)`
in `frontend/src/homeEvidence.js` is pure and independent of React:

1. Round the explicit reference upward to a full Asia/Kolkata clock hour; an
   already exact boundary starts the window there.
2. Require declared mm, IST and preceding-hour/3600-second semantics.
3. Reject unknown clocks, duplicates, out-of-order or non-hourly intervals.
4. Require exactly 24 intervals covering `[start, start + 24 hours]`, with provider
   END timestamps `start + 1 hour` through `start + 24 hours`.
5. Reject gaps/overlaps and every missing/null/non-finite/negative selected value
   or incompatible unit. Sum only a complete valid window; never interpolate or
   substitute daily precipitation, even when the window starts at midnight.
6. Return total mm, both endpoints, count 24, source, retrieval clock and absent
   issuance time; otherwise return unavailable with a reason and null total.

For **10:20 IST**, the displayed window is **11:00 today–11:00 tomorrow**;
provider END entries are **12:00 today–11:00 tomorrow**. This is not a rolling
10:20–10:20 total. The session updates the reference at full IST hours without
an extra fetch. Home displays **Next 24 full forecast hours: X mm** and both
local endpoints. No precipitation value triggers flood-risk inference.

## Live result and browser evidence

Independent installed Chrome **154.0.8037.57**, no API mocking, selected Kundapur
through the actual directory and made **one** weather request across four resizes.
FastAPI returned HTTP 200 at **2026-10-13 11:58:19.614 IST**. Current model valid
**11:45 IST**: **35.8 °C**, **Clear sky (WMO 0)**, humidity **33%**, wind **13 km/h**,
precipitation **0 mm for 11:30–11:45 IST**. At reference **11:58:26 IST**, exactly
24 intervals totaled **0 mm** from **13 October 12:00 IST** to
**14 October 12:00 IST**. This is a timestamped sample, not guaranteed future
availability or evidence of no flooding. Forecast issue time remains unknown.

See Home browser measurements (archived in tag `archive/research-2026-10-16`). Real viewport and
full-page PNGs, raw responses, request URLs/parameters, baseline and post-change
backend receipts are in ignored `data/recovery/home_weather_hourly_v1/`.
The committed small recorded API-shaped fixture is explicitly test-only and
uses a fixed clock; operational code never reads it. Focused backend/current/
hourly/error tests, independent aggregation tests, session/cache/location tests
and populated Home browser checks complement the unchanged application suites.
Exact executed results are appended chronologically to root `update.md`.
