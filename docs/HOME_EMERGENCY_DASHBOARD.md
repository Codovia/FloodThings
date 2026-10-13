# Home emergency dashboard

Implemented on `/` only, following the approved photographed sketch 01 and the
Home Emergency Dashboard request. The shared navigation and four detail pages
retain their existing workflows. No backend endpoint, database schema, model,
operational Flood Map layer, administrator permission or Telegram workflow changes.

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

Home uses App's existing `useWeatherSession`, with its exact-coordinate validation,
six-hour retrieval freshness, bounded requests, cancellation and inactive-route
pause. It creates no second weather lifecycle and requests no default Bengaluru
weather when Home has no selected point. The current card requires a fresh model
receipt, finite temperature and a valid estimate timestamp at most 90 minutes
old. Precipitation is described as the model's preceding measurement interval;
a current conditions description is unavailable when that information is absent.
Daily WMO codes are not presented as the current condition.

The existing API supplies **IST calendar-day totals**, with units and coverage
metadata. It supplies no hourly intervals or forecast issue timestamp. Those
facts were inspected in `backend/app/weather.py` and checked against the
[Open-Meteo documentation](https://open-meteo.com/en/docs).

The displayed 24-hour forecast window starts at the next complete IST hour and
states both timestamps. Whole intervals must tile it exactly, without a gap,
overlap, duplicate, unknown clock, negative/missing value or incompatible unit.
Daily totals are never prorated. A daily total can serve this window only when it
starts at local midnight and ends at the following midnight. At other times the
card says **Next-24-hour total unavailable** and links to the calendar-day
forecasts on Weather & AI. This is a precipitation forecast, never a flood label,
flood probability or warning. Consistently timestamped hourly forecast intervals
would be needed for general next-24-hour availability; no backend expansion was
performed to fill the card.

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
