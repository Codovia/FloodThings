# Home emergency dashboard

Implemented on `/` only, following the approved photographed sketch 01 and the
Home Emergency Dashboard request. The shared navigation and four detail pages
retain their existing workflows. The weather response now adds validated current
fields and hourly precipitation as documented below; endpoint paths, database
schema, models, operational Flood Map layers, administrator permissions and
Telegram workflows are preserved.

## Location and privacy

Home immediately mounts Leaflet with the publication-permitted Karnataka state
context and existing historical observations. Its first visit in a tab session
requests browser geolocation in a secure context, using `getCurrentPosition`,
`maximumAge: 0`, a 10-second timeout and an independent timeout guard. Permission,
policy errors, unsupported APIs, invalid/stale positions and timeouts leave the
statewide view available with name search. No continuous watcher is created.

Only a non-location `floodpulse-home-location-attempted=1` flag enters
`sessionStorage`; coordinates and accuracy remain in React memory. Reloading
clears coordinates without prompting again. Explicit **Use my location** remains
available. Blocked storage falls back to the App-lifetime initialization guard.
Leaving Home cancels callbacks; manual locality or district selection invalidates
pending GPS before it can replace the selection. Successful GPS is never snapped
to one of the reviewed locality points. Browser accuracy and source timing are
checked; recent fixes must have finite, nonnegative accuracy and timestamps no
more than 60 seconds old or one second ahead of the browser clock.

GPS/weather point, reviewed locality, selected district filter and inspected
historical cell retain separate meanings. A district alone produces no weather
point on Home. Name search uses the existing verified directory. GPS has no
inferred district association. A minimal `kind: gps` source tag on the existing
opt-in selector preserves GPS meaning when returning from Weather & AI.

Browser requirements were checked against
[MDN geolocation documentation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition).
Native headless Chrome cannot establish the device's actual GPS location; grant,
timeout and delayed-result cases are controlled browser/unit tests.

## Geographic context and rights

The retained district research includes restricted Survey of India geometry.
None is copied, reconstructed or published here. Home instead uses the Karnataka
`IN-KA` feature from the pinned geoBoundaries gbOpen India ADM1 simplified product,
commit `9469f09`, boundary `IND-ADM1-1811400`, represented year 2011. Publisher:
geoBoundaries; source attribution: DataMeet India community / Election Commission
of India; licence: **CC BY 2.5 IN**, not the other directory's ADM2 licence.

[Publisher metadata](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM1/)
and [licence](https://creativecommons.org/licenses/by/2.5/in/) accompany
`frontend/src/data/karnatakaHomeBoundary.source.json`. The 5,103,747-byte original
is retained only under ignored `data/recovery/home_emergency_v1/geography/`.
Its SHA-256 matches the publisher Git LFS pointer:
`4c63fe43294a391e8f2de4e9f86f3edb60f8688275b9fee90c61fb2aa0c26061`.
Only the 189,831-byte, separately hashed Karnataka feature and small receipt are
published. Geometry coordinates are unchanged; extraction selects one feature
and serializes it separately. An initial 2 MiB preview exceeded its cap and was
discarded before the full bounded transfer and successful checksum verification.

Point-in-polygon screening respects holes. Positions within the browser accuracy
radius plus a **2 km application caution margin** of any boundary are uncertain.
This margin is a conservative display policy, not a measured positional accuracy.
The simplified 2011 outline is context, not a certified current legal boundary,
district lookup, hazard zone or inundation extent. Clear outside-state fixes,
including Goa, receive an out-of-coverage explanation; point weather can still be
requested independently. The existing public geographic directory is unchanged.

## Weather and rainfall

Home uses App's existing `useWeatherSession` and one FastAPI/provider request for
current, hourly and seven-day daily data at the exact selected coordinates. It
creates no second lifecycle and requests no default Bengaluru weather when Home
has no selected point. Current temperature, current WMO condition, humidity,
wind with returned units, preceding-interval precipitation, valid time and source
come from validated Open-Meteo model output. A missing temperature does not hide
other valid fields; a daily WMO code never substitutes for the current code.

The current card requires a fresh receipt and a valid current estimate no older
than 90 minutes. Six-hour session retrieval cadence remains; current estimates
that age out are unavailable until a successful refresh. Failed refreshes mark
cached data stale. A manually initiated refresh is always available at a selected
point. Backend network/timeout, upstream HTTP 429/503 and malformed-response
categories remain distinct; retries are bounded, respect Retry-After and apply
only to transient failures. Unsupported provider requests are HTTP errors;
absence of a requested field alone does not establish that it is unsupported.

**Next 24 full forecast hours: X mm** uses exactly 24 consecutive one-hour
precipitation intervals beginning at the next full IST hour (at an exact hour,
that boundary starts the window). Open-Meteo timestamps END the preceding hour:
a reference of 10:20 means a window 11:00 today to 11:00 tomorrow and selected
provider timestamps 12:00 today through 11:00 tomorrow. Both local endpoints are
shown. The pure calculation accepts an explicit reference clock and returns
interval count, source, retrieval time and unavailable forecast-issuance time.
The browser updates its window clock at hourly boundaries without fetching again.

Unknown clocks, duplicate or out-of-order timestamps, gaps, overlapping or
non-hourly intervals, missing/null/non-finite/negative values and incompatible
units make the entire total unavailable, with its reason in the information
panel. No interpolation, daily substitution (including midnight windows) or
synthetic fallback is allowed. Independently valid current weather remains
available when hourly coverage fails. Source, freshness and extended limitations
are accessible in native expandable details. Seven-day calendar forecasts on
Weather & AI retain their existing contract and presentation.

See [weather contract and diagnostic evidence](OPEN_METEO_WEATHER.md) and the
[official variable definitions](https://open-meteo.com/en/docs). Weather-model
estimates are not certified local station observations, flood labels, flood
probabilities or official emergency warnings.

## Evidence and assistance

The flood card uses the exact required phrase:
**Validated flood forecast unavailable for this location.** No AI rainfall
inference runs on Home. Official warnings are **Not connected** and published
hazard polygons are unavailable. Missing coverage does not mean no flood risk.

Home reuses `/api/flood-map/historical` and accepts only attributed,
observation-qualified CRS84 polygon cells with source dates and geometry hashes.
The current collection has 56 Udupi cells from two historical GFD event-window
products, not 56 independent floods or current inundation boundaries. Unsupported
geometry is excluded. Historical map popups link to Flood Map details and keep
weather coordinates unchanged. General map clicks link to complete evidence
without creating a forecast or weather location.

One `useShelterDirectory` receipt feeds Home's list and map. Only live, fresh,
verified Open entrances with reported capacity are shown; optional district
filtering does not assign GPS to that district. Test/demonstration assignments
are excluded from emergency markers. The hook's one-minute revalidation and
verification expiry remove destinations during rechecking or failure. Directions
remain on the existing Shelters workflow with its explicit revalidation; capacity
is not a reservation and routes are not verified flood-safe.

OSM uses the existing origin-referrer tile configuration, ordinary viewport
requests and stop-on-first-failure behavior. No tile proxy, prefetch or retry is
added. [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/).
Missing background tiles retain evidence overlays and do not establish flood
absence. Leaflet's existing ResizeObserver invalidates size without moving the
selected point.

## Validation and limits

Home uses a 40% information / 60% map grid on desktop with three compact cards
above it. The desktop follow-up replaces the earlier tall, page-scrolling layout
with a Home-scoped 100vh/100dvh flex/grid workspace. Header, footer and content
rows reserve their actual heights; shrinkable children have min-height: 0.
The left panel pins forecast availability and official warning status above a
keyboard-focusable internal scrolling region. Additional provenance uses native,
accessible details controls. The map fills the remaining workspace; a background
failure notice does not shrink its canvas. Leaflet invalidates its size through
the existing ResizeObserver and refreshes initial statewide framing after the
first viewport fit, without moving a selected point.

Viewport fitting requires width >= 1100 px, height >= 740 px and enough remaining
space for a readable workspace and essential statuses. ResizeObserver checks
header/footer, location, cards and essential-content sizes, including font changes.
Short screens, narrower zoom-equivalent viewports and enlarged text that cannot
fit use natural scrolling. No body overflow suppression or global font reduction
is used. Mobile stacks the information and map, with a 380 px map. Other pages
retain their existing layouts and scroll assertions.

Independent installed **Google Chrome 154.0.8037.57** inspected all five routes,
with no API mocking and no page errors. Final Home map rectangles:

| Viewport | Document height | Leaflet map | Left panel |
| --- | --- | --- | --- |
| 1366 × 768 | 768 px | 764 × 352.16 px | 524 × 444.34 px |
| 1920 × 1080 | 1080 px | 1096.39 × 664.16 px | 745.59 × 756.34 px |
| 1600 × 900 | 900 px | 904.39 × 484.16 px | 617.59 × 576.34 px |
| 390 × 844 | 2530 px (natural scrolling) | 332 × 380 px | 358 × 849.55 px |

Current viewport and full-page screenshots, measurements and validation receipts
are in ignored `data/recovery/home_viewport_v1/`. Desktop full-page image heights
match their viewport heights; mobile deliberately remains taller. Current layout
checks also cover keyboard panel scrolling, bounded search, expandable source
notes, pinned statuses, short screens, a 1093 × 614 zoom-equivalent viewport and
200% root text scaling. Weather/GPS/rainfall/history/shelter validation logic and
scientific claims are unchanged.

Full-page screenshots and receipts are retained under ignored
`data/recovery/home_emergency_v1/`. They are actual browser captures, not generated
mockups. The real configured PostgreSQL directory returned HTTP 200, live mode,
zero shelters. The existing database container was stopped initially and started
without creation, migrations or record changes. Real weather returned HTTP 200
before midnight (26.6 °C for reviewed Kundapur); a later real check returned HTTP
503, **Weather provider returned incomplete or invalid data**, and Home displayed
unavailable. The cause of that upstream invalid response is unconfirmed. No
synthetic weather or cached fixture substitutes for the failure.

The complete frontend, Playwright, backend, build and 24 source/provenance checks
are recorded in the chronological `update.md` entry after completion. Controlled
GPS/weather/shelter fixtures are separate from the unmocked Chrome receipts.
The production build's bundle-size advisory remains a packaging limitation.

The initial full browser suite exposed a pre-existing test writing three Admin
fixture screenshots into `data/recovery/wireframe_ui_v1/after/`. Those ignored
PNG artifacts were regenerated and their original hashes no longer match; no
original copies were found. The test now uses Playwright's temporary output path,
preventing further overwrite. This exception is recorded in the protected-file
receipt; scientific datasets, provenance, models and unrelated files are checked
separately and remain unchanged. These fixture screenshots are not research
observations and are not staged.

No scientific training decision changes: validated future-flood prediction
remains unavailable, and the earlier research NO-GO is retained.

## Live weather follow-up, 2026-10-13

Independent installed Chrome, with no API mocks, selected the retained verified
Kundapur directory point. One weather request served all viewport resizes:
HTTP 200, 35.8 °C / Clear sky / humidity 33% / wind 13 km/h, current valid
11:45 IST, precipitation 0 mm for 11:30–11:45 IST. The full forecast-hour total
was 0 mm for 13 October 12:00 to 14 October 12:00 IST, with 24 intervals. Zero
forecast precipitation makes no claim about flood occurrence or safety.

| Viewport | Document height | Leaflet map | Information panel | Each weather card |
| --- | --- | --- | --- | --- |
| 1366 × 768 | 768 px | 764 × 353.55 px | 524 × 445.73 px | 434 × 83.08 px |
| 1600 × 900 | 900 px | 904.39 × 485.55 px | 617.59 × 577.73 px | 512 × 83.08 px |
| 1920 × 1080 | 1080 px | 1096.39 × 665.55 px | 745.59 × 757.73 px | ~618.67 × 83.08 px |
| 390 × 844 | 2685 px, natural scroll | 332 × 380 px | 358 × 990.53 px | current 358 × 92.38; rain 358 × 108.06 px |

Document width equals viewport width throughout; desktop page scroll remains zero
when keyboard-scrolling the information region. Actual OSM tiles loaded at all
four sizes (12/15/20/20); no page errors. Essential statuses, navigation, footer
and all three cards remain visible on desktop. Real viewport and full-page PNGs,
raw provider responses and timestamped measurements are retained in ignored
`data/recovery/home_weather_hourly_v1/`. Previous screenshots remain unchanged.
