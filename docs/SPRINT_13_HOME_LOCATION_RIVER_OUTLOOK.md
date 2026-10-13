# Sprint 13: Home location and nearby river outlook

Baseline: `923a06dc5ee440caf18a0d1a598f00a38957ae9a`, branch
`feature/karnataka-data-foundation`. Reviewed 13 October 2026.

**Delivered:** accuracy-aware GPS, a disabled-by-default reverse-geocoding
adapter, simplified Home, and a read-only, geographically gated GloFAS adapter.
**Live automatic names: unavailable. Approved Home river associations: zero.**
Current weather/hourly rainfall remain real model output at accepted coordinates.
Official warnings remain **Not connected**. Scientific training remains **NO-GO**.

## GPS finding and behavior

The user confirmed that reloading produced a precise position. The prior hook
always called accepted positions “GPS-selected point”; it had no reverse-geocoder.
It requested `enableHighAccuracy: false` and accepted any finite nonnegative
accuracy, including approximately 279,949 m, for weather/map focus. Coordinates
were never replaced by the nearest directory town. Generic naming was not proof
that GPS acquisition failed.

The existing browser permission flow now requests high accuracy, `maximumAge: 0`,
and a ten-second timeout with a separate deadline guard. No watcher is created.
Old/invalid timestamps and invalid coordinates/radii still fail closed. Only the
existing non-location tab-session attempt flag is stored. Accepted coordinates
stay in React memory; automatic prompts do not repeat on every render/reload.
An explicit **Use my location** remains available.

**100 m is an application acceptance policy, not measured survey accuracy.**
A wider or unknown GPS radius cannot establish local Home weather or river focus.
Home shows **Approximate location — select your town**, retains statewide framing
and starts neither weather nor reverse/river requests for that rejected fix.
Manual directory selection supplies its own reviewed mapped point. Coarse GPS
chosen on Weather & AI also cannot silently become precise Home weather.
The current sprint leaves that separate page's controls unchanged.

Precise GPS selects the actual coordinates immediately for model weather, then
attempts optional naming. The name never moves the point. Naming failure leaves
the accepted GPS point and a manual-name fallback. Manual town/district selection
increments the existing revision and aborts pending naming; late GPS or geocoder
responses cannot replace it. Leaving Home cancels pending work. Renaming the same
coordinate pair does not create another weather or river request.

The simplified 2011 state outline and its 2 km caution margin remain approximate
map-coverage context. They do not establish a district, current legal boundary
or river exposure. Clear outside fixes explain coverage limitations. Provider
context names are separate from canonical public directory identities/filter IDs.

## Reverse-geocoding access and validation

Inspected the existing `adminMapProvider.js`, administrator MapTiler documentation,
repository `.env` locations and request environment without printing values.
No MapTiler key/activation setting was found in the examined configuration;
authorized account quota was not established. The actual local reverse endpoint
returns **disabled**. Existing Admin imagery/search adapters are unchanged.

Chosen optional provider: [MapTiler reverse geocoding](https://docs.maptiler.com/cloud/api/geocoding/).
Its [Cloud terms](https://www.maptiler.com/terms/cloud/),
[account quotas](https://www.maptiler.com/cloud/pricing/) and
[attribution](https://www.maptiler.com/copyright/) require an authorized account
and suitable access. It is not a blanket open-data licence. No account, terms
acceptance, key purchase, live geocoding request or public Nominatim activation
occurred. A browser-restricted Admin key is not silently reused as server access.

`POST /api/location/reverse` requires explicit latitude, longitude and reported
accuracy. Missing accuracy is HTTP 422, not perfect precision. Enabling the
single-worker pilot requires operator-reviewed server access and an allocated
budget, configured privately:

```text
MAPTILER_REVERSE_ENABLED=true
MAPTILER_GEOCODING_RIGHTS_REVIEWED=true
MAPTILER_GEOCODING_KEY=<AUTHORIZED_SERVER_REQUEST_KEY>
MAPTILER_GEOCODING_HOURLY_BUDGET=<REVIEWED_BUDGET_1_TO_600>
```

These are configuration gates, not evidence that this sprint obtained permission.
Do not put the server key in Vite, source control, screenshots or logs. Operator
review must verify actual key validity, permitted use and account-wide quota
before enabling. Multiple server workers need a shared limiter or separate
properly allocated budgets; this implementation is one-process scoped.

The adapter reserves two requests per job, limits new jobs to one every two
seconds and the configured hourly budget, coalesces through a lock, and keeps at
most 64 name receipts in memory with a 60-second reuse TTL. Keys are process-salted
opaque hashes, not retained raw GPS coordinates; expiry cleanup happens on the
next request. Provider Retry-After imposes a
cooldown across different points. There is no automatic geocoding retry loop.
Reverse JSON is capped at 64 KiB, full geometry at 1 MiB, with a total ten-second
job deadline. Neither raw geometry nor precise positions are archived.

Only one unambiguous municipality/locality candidate is considered. The feature
ID's original full polygon must match the reverse result, cover the whole
reported accuracy circle plus a 20 m policy caution margin, respect holes and
carry India/Karnataka provider context. Point centroids, bounding boxes, nearest
reviewed towns, ambiguous results or unsupported geometry cannot approve a name.
The local distance screen is not certified boundary accuracy. Labels retain
MapTiler/OSM attribution and provider context; they do not assign a canonical
NIC/LGD district or alter requested weather coordinates.

New source routes POST location data and send `Cache-Control: no-store`. Provider
logs omit MapTiler keys/location paths and weather coordinates; the standard
Uvicorn access tuple omits coordinate-bearing weather/shelter query strings.
Application logging retains route/status information. Existing runtime logs are
preserved rather than rewritten. Operational code never reads test fixtures.

**Tests versus live:** accepted names/polygons and delayed replies are explicitly
isolated test fixtures. Live automatic naming was not possible without authorized
configuration. Real Chrome selected **Kundapur, Udupi** through the existing
reviewed directory; that is manual directory naming, not a live reverse-geocode.
Device GPS hardware was not independently validated by headless Chrome. The
user's reported precise reload result is retained as a user report.

## Home changes

Removed Home's shelter hook/list/map markers, Refresh Shelters control, historical
fetch/count/details/56 polygons and Show historical evidence control. No data,
research provenance or dedicated route was removed. `/shelters`, Admin management,
verification expiry/security and `/flood-map` source/geometry inspection still pass
regressions. The historical observations remain research evidence, not approved
operational flood-training labels.

The three cards remain Current Weather, Rainfall Forecast, Flood Forecast.
The left information region now contains compact weather and river outlook.
Flood availability, the complete nearby-assessment message and official warning
status are pinned outside internal scrolling. Repeated current/rainfall prose
was removed; attribution and calculation explanations use accessible details.
GPS/manual location, optional reviewed model cells and state context are the only
Home geographic layers. No warning source/geometry is connected.

## Live GloFAS parameter check

Official endpoint: `https://flood-api.open-meteo.com/v1/flood`.
The tiny requests reused retained, channel/area-screened **v5 research cell
centres**, not newly invented or canonical dated CWC gauge coordinates. Requested
points/URLs/original bytes remain ignored in `data/recovery/sprint13_home_v1/`.
These candidates do not become approved v4 river locations.

```text
latitude=<retained research model-cell latitude>
longitude=<retained research model-cell longitude>
daily=river_discharge,river_discharge_mean,river_discharge_p25,river_discharge_p75
models=forecast_v4
forecast_days=7
timezone=GMT
```

| Existing research area | HTTP / bytes | Original dates | First model rate | First mean | First p25–p75 | Requested/returned centre difference |
|---|---|---|---:|---:|---:|---|
| Sadalga candidate area | 200 / 662 | 13–19 Oct 2026 GMT | 4.22 m³/s | 4.22 | 4.21–4.22 | approximately 1 m; not channel verification |
| Huvinhedgi candidate area | 200 / 663 | 13–19 Oct 2026 GMT | 0.10 m³/s | 0.10 | 0.10–0.10 | approximately 2 m; not channel verification |

Retrieved at approximately **16:32 IST on 13 October**. All four requested arrays
had seven finite nonnegative values and units `m³/s`; dates used `iso8601`, GMT,
UTC offset 0. A separately identified invalid-model control returned HTTP 400 /
128-byte error, confirming that the provider processes the model selector.
It is parameter-test evidence, not a forecast observation. No historical series,
weights, large rasters or account-authenticated native archive was downloaded.

The official [Flood API documentation](https://open-meteo.com/en/docs/flood-api)
warns that a different river may be selected at approximately 5 km resolution.
GMT preserves original model dates; timezone changes do not recompute local-day
flow. The API data licence is [CC BY 4.0](https://open-meteo.com/en/licence);
free access has [non-commercial service terms](https://open-meteo.com/en/terms).
Copernicus GloFAS attribution remains explicit. Daily rates are not water level,
measured CWC discharge or a rainfall total. Ensemble p25–p75 is an interquartile
range, not a flood probability or guaranteed range; the mean can lie outside it.

## Geographic gate and exact blockers

**Approved v4 reaches: 0. Activated Home associations: 0. Verified districts: 0.**
The two successfully queried cells remain **unverified**, not proven incorrect.
The existing Gokak mapping remains ambiguous/deferred and was not queried.
Incorrect returned cells and ambiguous mappings are rejected by isolated tests.

The response has no river/reach ID, native model release or forecast issue clock.
Coordinate agreement alone cannot establish channel identity/topology. Only
retained v5 static channel/upstream-area/direction products were found; v5 historical
screening is not proof of v4 forecast parity. Existing dated gauge coordinate
conflicts and public district joins remain unresolved. Small discharge values
are not used to classify a cell as right/wrong or any place as safe/dangerous.

To activate a pilot, obtain a rights-cleared native **forecast-v4 channel/grid/
upstream-area/topology reference**, a verified named reach line and a reviewed,
licensed viewing-area association. Record actual provider query/returned cell,
source/version/hash, review time, reuse rights and geographical meaning. Independently
review the association and any model issue/age limitations. No straight-line
nearest-reach or district-wide flow assignment can substitute. GPS proximity alone
does not establish upstream/downstream exposure or inundation.

`RiverOutlook` currently has an empty approved register. User coordinates never
become unchecked Flood API query points. Zero or multiple reviewed area matches,
coarse GPS, missing reviews/rights, incompatible v5 metadata or wrong returned
cells produce unsupported/unavailable without a source forecast or marker.
The register is internal code, not something a public request can supply.

Validated future records would preserve seven GMT dates, mm-free m³/s units,
null values, optional unsupported ensemble fields, original response hash,
requested model and original grid. Duplicate/reversed/missing dates, negative/
non-finite values, bad units, inverted quantiles or conflicting model metadata
fail closed. Source identity is request-pinned; native release/issuance are unknown
when absent, not inferred from generation milliseconds or retrieval time.

Source requests have a total ten-second deadline, at most two transient attempts
with short backoff, no immediate 429 retry, and respect longer Retry-After.
A per-reach lock coalesces concurrent calls. Successful receipts cache for at most
one hour or until GMT midnight; failed responses impose at least 30 seconds of
cooldown or longer guidance. Cache age is retrieval age, **not forecast issuance
age or forecast validity**. Frontend hides expired/mismatched receipts and offers
explicit refresh. Unsupported areas trigger no upstream request. No dataset,
station record, model artifact or administrative geometry is rewritten.

## Nearby flood possibility and scientific decision

Home pins exactly:

> Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.

Official feed status stays **Not connected**, never “No warnings.” No authorized
feed exists in the retained integration evidence, so no official warning or
warning geometry is invented. A future verified external river outlook can show
labelled rates and scope, but changing flow cannot identify flooded villages.
No probabilities, low/medium/high categories, discharge-percentile thresholds,
flow-derived inundation polygons or rainfall-derived flood inference are created.

Phase 12G **training NO-GO remains unchanged**. Eligible measured forecast pairs
remain zero. Pending CWC station/timezone/datum/method/QC/release and effective
threshold clarification remains the named prerequisite; the prepared request is
unsent. Modelled API output is not new measured targets, flood-positive/negative
labels or proof of local predictive skill. No baseline or AI model was fitted.

## Actual Chrome and validation

Installed **Google Chrome 155.0.8059.39**, fresh context/default zoom: DPR 1,
visual-viewport scale 1 and CSS zoom 1. No API mocking in the final capture.

| Viewport | Document height / width | Map | Information panel | Weather cards |
|---|---|---|---|---|
|1366×768|768 / 1366 px|764×353.55 px|524×445.73 px|434×83.08 px|
|1600×900|900 / 1600 px|904.39×485.55 px|617.59×577.73 px|512×83.08 px|
|1920×1080|1080 / 1920 px|1096.39×665.55 px|745.59×757.73 px|~618.67×83.08 px|
|390×844|2223 / 390 px, natural scrolling|332×380 px|358×569.58 px|current358×92.38; rain358×89.88 px|

No page errors/horizontal overflow. Actual OSM tiles loaded 12/15/20/20.
At 1366, keyboard internal scrolling moved 55 px while page scroll stayed 0;
critical statuses remained fixed. All essential rows/cards, map and footer are
inside the desktop viewport. Source details, mobile navigation, short screens,
zoom-equivalent size and 200% text scaling retain accessible scrolling.

Real Kundapur weather at **17:15:10.807 IST**: HTTP 200, current valid 17:15 IST,
31.1 °C, WMO 0/Clear sky, humidity 76%, wind 9.9 km/h, precipitation 0 mm over
17:00–17:15. At reference 17:15:15 IST, 24 full forecast hours totaled 0 mm for
13 October18:00–14 October18:00 IST. One weather request served all four resizes.
Home made no historical/shelter request and displayed zero historical/river
markers. An intermediate recapture's success-only wait timed out; the final
capture records available or unavailable states explicitly and succeeded with
real data. No provider failure cause is invented for that incomplete attempt.

Viewport/full-page screenshots, DOM measurements, live receipts and validation
logs are ignored under `data/recovery/sprint13_home_v1/`. Exact test counts and
protected-file results are appended to root `update.md` before scoped delivery.
