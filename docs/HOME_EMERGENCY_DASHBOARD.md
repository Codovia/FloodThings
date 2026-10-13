# Home emergency dashboard

Current behavior after Sprint 13, 13 October 2026. `/` keeps FloodPulse branding,
all five navigation routes and the approved 40% information / 60% map workspace.
Weather & AI, Shelters, Admin and Flood Map retain their own functionality.
See the [Sprint 13 evidence/access report](SPRINT_13_HOME_LOCATION_RIVER_OUTLOOK.md)
and [validated weather contract](OPEN_METEO_WEATHER.md).

## Location and privacy

On the first Home visit in a tab, the existing browser permission flow makes one
bounded high-accuracy request, `maximumAge: 0`, with a ten-second timeout and
independent deadline. No continuous watcher is created. The existing tab-session
attempt flag contains no location. React retains accepted coordinates in memory;
reload does not persist them or automatically repeat permission prompts.
**Use my location** retries explicitly. Permission denial, insecure context,
unsupported API, stale/invalid fix or timeout keeps manual search and statewide
framing available.

A reported GPS radius above **100 m**, or unknown accuracy, cannot establish local
Home weather, a town label or river focus. This is an application acceptance
policy, not certified positional accuracy. Home displays **Approximate location —
select your town**, starts no point weather/naming/river request for that fix and
keeps the state view. This also applies when a coarse GPS point was selected on
another route. A reviewed manual locality supplies its own mapped point instead.

Precise GPS uses its **actual coordinates** for weather and map focus. It is
never snapped to a nearest directory locality. Optional reverse geocoding changes
only the displayed name. Manual selection always takes precedence over late GPS
or naming replies; revision checks and cancellation protect it. Leaving Home
cancels pending work. Changing only the name does not repeat weather requests.
District filter, weather point and source/provider geographic context remain
separate identities; naming never silently assigns a canonical district ID.

MapTiler naming is **disabled** in the verified configuration: no authorized key,
rights/quota confirmation was available. No Nominatim endpoint is activated.
Manual locality names remain available. The opt-in server adapter requires an
explicit reported radius, reviewed access, a request budget and a full matched
locality polygon covering the accuracy circle plus a 20 m policy margin. Point
centroids, bounding boxes, ambiguous results and incomplete geometry cannot
approve names. Full source geometry stays transient; names cache in memory for
60 seconds. Provider attribution follows any accepted name.

New Home source calls POST coordinates with no-store responses; no location
archive/database write occurs. Provider logging omits private key/location paths,
and Uvicorn coordinate-bearing weather/shelter queries are omitted from access
logs. Existing logs are preserved rather than rewritten. Native headless Chrome
cannot prove device GPS hardware accuracy; controlled GPS/name fixtures are
separate from unmocked Chrome/provider checks. The user's successful precise fix
after reloading is a user report, not a newly measured hardware result.

## Geographic context and rights

Home retains the publication-permitted Karnataka `IN-KA` feature from pinned
geoBoundaries gbOpen India ADM1, commit `9469f09`, boundary
`IND-ADM1-1811400`, represented year **2011**. Attribution: geoBoundaries /
DataMeet India community / Election Commission of India; **CC BY 2.5 IN**.
[Publisher metadata](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM1/)
and [licence](https://creativecommons.org/licenses/by/2.5/in/) accompany
`frontend/src/data/karnatakaHomeBoundary.source.json`. Its bytes/geometry and
source checksum are unchanged. Original transfer evidence stays in ignored
`data/recovery/home_emergency_v1/geography/`.

The simplified outline is map context, not a certified current legal boundary,
district lookup, hazard or inundation extent. The original 2 km policy caution
margin plus GPS radius still identifies border uncertainty. No district is
inferred from it. Retained Survey of India polygons and derivatives remain
restricted/local, never copied or reconstructed here. The existing public place
directory and geographic provenance remain intact.

## Weather and precipitation

Home uses the single App `useWeatherSession` and validated FastAPI/Open-Meteo
current/hourly/seven-day request at an accepted point. It fetches no default
Bengaluru weather when Home has no point. Missing optional fields retain other
valid readings. Current WMO condition never comes from daily severity codes.
Wind has returned units; precipitation retains its real preceding interval.
These are model-grid estimates, not certified station observations.

The top cards remain **Current Weather**, **Rainfall Forecast**, **Flood Forecast**.
Temperature/condition/valid time and the full-hour precipitation window are shown
compactly. Humidity, wind and current precipitation appear in the information
panel; repeated temperature/rainfall prose is removed. Accessible details retain
source, freshness, missing-hour reason and scientific limitations. Current valid
time expires after 90 minutes; existing six-hour retrieval cadence and explicit
manual refresh remain. Failed or stale cached data are not presented as current.

**Next 24 full forecast hours: X mm** selects exactly 24 ordered consecutive
one-hour precipitation intervals beginning at the next full IST hour. Provider
timestamps end the preceding hour. At 10:20, the window is 11:00 today–11:00
tomorrow; selected ends are 12:00 today–11:00 tomorrow. Both endpoints are shown.
Missing/null/non-finite/negative values, unsupported units/clocks, duplicates,
reverse ordering, overlap, gaps or non-hourly intervals reject the entire total.
No interpolation or daily substitution, even at midnight. The pure calculation,
source timestamp distinctions, cancellation and backoff are preserved.

## Simplified content and availability

Home no longer fetches or displays the shelter list, Refresh Shelters button,
historical section, 56-cell count, historical/shelter markers or Show historical
evidence control. These data/workflows remain on `/shelters`, Admin and
`/flood-map`. Historical GFD observations remain attributed research evidence,
not approved operational flood-training labels; no dataset is deleted.

The exact flood card remains **Validated flood forecast unavailable for this
location.** The pinned information area also displays:

> Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.

Official warning feed remains **Not connected**. None of these unavailable states
means no flood risk. Rainfall alone cannot confirm flooding. All three critical
statuses stay outside internal scrolling; long explanations use native details.

A small Global Flood API pilot returned actual modelled GloFAS v4 discharge, but
no native river/reach identity or issue timestamp. Retained v5 screening cannot
verify v4 topology or a user's hydrological association. **Zero Home river
associations are approved**, so the actual panel is unsupported and shows no
model cell marker. Query coordinates come only from internal independently
reviewed reach records, never arbitrary nearest-user points. Full details,
request/response samples and exact blockers are in the Sprint 13 report.

For a future verified association the read-only service/panel can preserve daily
GMT dates, m³/s discharge, optional mean/p25–p75, source/hash, reviewed viewing
scope and cache age. Cache expiry is not forecast validity or issuance. Missing
values stay unavailable. Changing modelled discharge alone cannot identify
flooded villages, danger categories or probabilities. Modelled river discharge
is not measured CWC level/discharge, a FloodPulse AI prediction or an official
warning. No flow-derived inundation polygon is constructed.

## Map and responsive layout

Home renders an accepted GPS point and its supported radius, or the selected
manual locality, plus the state context. Only a verified fresh river association
could add a model point; actual production currently has none. No authorized
warning geometry exists. Detailed historical geography stays on Flood Map.
**Show Karnataka**, **Show selected point** and the existing Full map link retain
keyboard/pointer navigation. Changing a label does not move the actual point.

Existing OSM viewport requests, attribution, origin-only identification,
cache behavior and stop-on-first-tile-error are preserved. No tile proxy, bulk
fetch, retry or provider substitution. [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/).
Failed tiles retain location/context and do not establish flood absence.
Leaflet's ResizeObserver still invalidates changing container dimensions.

Home-scoped 100vh/100dvh flex/grid accounts for header/footer and reserved rows.
Shrinkable children use min-height: 0; only the lower information region scrolls
internally when needed. Nothing globally hides body overflow or shrinks fonts.
Measured essential content must fit before viewport mode activates. Narrow/short
screens, zoom-equivalent viewports and enlarged text keep natural scrolling;
mobile stacks the panel and 380 px map. Other pages retain their own layouts.

Unmocked installed **Chrome 155.0.8059.39**, DPR 1, visual-viewport scale 1 and CSS
zoom 1, inspected the retained manually selected **Kundapur, Udupi** point:

| Viewport | Document height | Map | Information panel |
|---|---:|---:|---:|
|1366×768|768 px|764×353.55 px|524×445.73 px|
|1600×900|900 px|904.39×485.55 px|617.59×577.73 px|
|1920×1080|1080 px|1096.39×665.55 px|745.59×757.73 px|
|390×844|2223 px, natural scrolling|332×380 px|358×569.58 px|

Document widths equal viewport widths; no page errors. At 1366, internal keyboard
scroll moved 55 px while the document stayed at 0. Essential statuses/cards,
location, map and footer stayed visible. Actual tiles loaded at all sizes.
Real fullPage:false/fullPage:true captures, DOM measurements and API receipts are
in ignored `data/recovery/sprint13_home_v1/`; older sprint evidence is unchanged.
Controlled tests additionally exercise names/coarse GPS/delayed responses,
verified/ambiguous river fixtures, short screens and 200% text scaling. Native
GPS hardware and live MapTiler naming remain unverified, not falsely claimed.

Phase 12G scientific **NO-GO** and pending CWC clarification are preserved. No
model, dataset, flood-risk claim, administrator permission or Telegram workflow
was changed. Exact tests and protection/delivery results are appended to root
`update.md`. Previous Home iterations remain documented in its chronological
entries and their original recovery directories.
