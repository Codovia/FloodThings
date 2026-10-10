# Original wireframe implementation

This sprint uses all five JPG photographs under [design/floodpulse_wireframes](design/floodpulse_wireframes/DESIGN_REFERENCE.md), read directly rather than substituted with a generic mockup. The original bytes, sizes, SHA-256 and mtimes are preserved; `MANIFEST.md` identifies each photograph. Header, five direct routes, blue/teal design, history navigation and existing service contracts remain.

| Screen reference | Implementation | Scientific interpretation |
|---|---|---|
| 01 — Home | `App.jsx`: emergency/district coverage cards and compact shared place control left; Karnataka context map right. Assistance and point-weather details remain reachable in one information pane. | Unconnected warning feed is unavailable, not an all-clear. Historical cells are retrospective, hazard zones unregistered. No invented emergency counts. |
| 02 — Weather | Actual current estimates, seven-day cards, rainfall chart and experimental AI left; synchronized point/district geography right. Context can be hidden. | Point-specific weather; model only exact Kundapur/Mangaluru points. Heavy rainfall ≥64.5 mm/24 h, not flood occurrence or calibrated probability. Source/grid/retrieval metadata retained. |
| Dedicated Flood Map | Existing dominant map, 31-district filter, independent layer controls and source-labelled feature details. | Exactly 56 historical Udupi cells; zero verified hazard polygons. Mechanisms remain Unknown where unsupported. Drainage context is not overflow risk. |
| 03 — Shelters | Directory/facilities/available capacity/verification/directions left; fresh entrance map right, including an honest empty map context. | One validated directory response supplies both sides. Failure/expiry removes destinations. Latest explicit directions recheck remains required; no route is claimed flood-safe. |
| 04 — Admin after login | District-filtered assignment/editor pane left; street/conditionally authorized satellite inspection and explicit entrance map right. Telegram retains a separate workspace. | Loaded-page filtering is disclosed; administrator district context is private. Material edits invalidate confirmations. Imagery or building reference never verifies authorization, usability or entrance. |
| 05 — Experimental reporting | [Moderated technical design](EXPERIMENTAL_FLOOD_REPORTING_DESIGN.md) only. | No submissions, uploads, confirmed evidence, warnings or training labels activated. |

## Shared state and component boundaries

`App.jsx` owns separate district-filter, weather-point and evidence-feature identities. `LocationDirectorySelector.jsx` accepts the shared controlled district, uses unique accessible IDs and suspends directory queries when its page is inactive. Selecting a locality retains its real source metadata. District-only filtering does not request point weather or fabricate a district centroid.

`WeatherPointMap` is reused for the Home/Weather context instead of repeating a coordinate form. `useWeatherSession.js` pauses on inactive routes, caches the last selected-point receipt and applies the original six-hour freshness policy on return; point changes still cancel and reject old responses. `RainfallOutlook.jsx` checks exact scope before inference and cancels hidden-page work. No model artifact or inference contract is changed.

`PublicShelters.jsx` places its map into the right-hand panel through a React portal, preserving one `useShelterDirectory` fetch/freshness lifecycle, latest destination check and failure handling. `ShelterMap.jsx` preserves the user view when only labels/capacity change; real geometry or reference changes still navigate. Authenticated `AdminShelters.jsx` keeps cancellation, private-state clearing, concurrency, confirmation invalidation and audit behavior; its map does not recenter on unrelated form edits.

Detailed scientific/source metadata remains accessible; original backend APIs, research modules and archives are not deleted for cosmetic reasons. No additional provider, new geocoding collection, migration or operational database record is introduced.

## Browser evidence

Local-only screenshots/receipts: `data/recovery/wireframe_ui_v1/before/` and `after/`.

- Both sets contain all five routes at 1366×768, 1920×1080 and 390×844, captured with installed independent headless Google Chrome against the running launcher application.
- `home-{width}.png`, `weather-{width}.png`, `map-{width}.png`, `shelters-{width}.png` and `admin-{width}.png` are the route comparisons. Admin route captures show the actual protected login, not an invented operational account.
- `admin-isolated-{width}.png` shows authenticated sketch 04 using visibly labelled browser-only fixtures. No account/shelter is written to the operational database; imagery/building modes remain disabled without authorized settings.
- `kundapur-live.png`, `mangaluru-live.png` and `live-report.json` record real seven-day weather and saved-model inference. No provider fixture or database write is used for those results.
- Controlled browser outages and zero-hazard coverage remain separate from actual live-provider demonstrations. A grey early tile screenshot is not treated as proof of successful imagery: loaded tiles are checked independently.

Desktop uses one substantial information scroll pane and a persistent large map; mobile stacks naturally. Essential controls remain keyboard accessible and maps resize through the existing observer. Screen-by-screen DOM geometry, viewport overflow, state synchronization and map interaction are asserted in `frontend/tests/wireframes.spec.js` and the existing regression suite.

## Operational limitations

31 district names do not imply statewide verified geography: only five selectable place points across Udupi/Dakshina Kannada, with unresolved current LGD reconciliation. No public restricted SOI geometry is added. GIS raster previews still require existing local assets; the legally reviewed checksum-validated display package remains a future packaging decision described in `CURRENT_CAPABILITIES.md`.

Public operational shelter availability remains empty. Genuine administrator provisioning, authorized optional satellite configuration and explicitly approved Telegram live testing are separate operator actions. No warning feed or new hazard source is connected. Weather estimates and experimental rainfall inference do not establish flood safety, live flooding or evacuation advice. No model training, research expansion or automated warning occurs.

## Final verification — 11 October 2026

- Full frontend: **185 passed**, 19 files (11 added tests). Full backend: **1,354 passed**, including existing training-reproduction evaluation without rewriting the saved artifact. Real PostgreSQL/PostGIS integration: **49 passed** in a UUID-named isolated database removed by the harness. Full Playwright: **46 passed**, one worker. Production build passed. Existing offline dataset/provenance validators: **48/48 passed**.
- Independent installed Google Chrome **154.0.8037.57**: 15 before and 15 after route screenshots at 1366×768, 1920×1080 and 390×844; final screenshots have no horizontal overflow or page exceptions. Final route capture observed **164 HTTP 200 street tiles, zero tile HTTP failures**. This is environment-specific availability, not a provider uptime guarantee.
- Real Kundapur and Mangaluru provider/model demonstrations each returned weather HTTP 200 with seven days and inference HTTP 200 using unchanged `rainfall_logistic_v1`; probability remained null. `live-report.json` preserves actual retrieval/window details. This verifies inference, not prediction accuracy or flood warning capability.
- `admin-chrome-fixture-{width}.png` separately shows sketch 04 in independent Chrome with browser-only authenticated fixtures and an explicit demonstration banner, real public district reads/street tiles and **zero operational writes**. `admin-isolated-{width}.png` additionally covers the isolated editor workflow in browser regressions. No genuine administrator credentials, facility assignment, satellite access or Telegram delivery were used.
- Snapshot: **1,841 starting files**, **1,815 unchanged files exactly preserved** (SHA-256, bytes, size and nanosecond mtime), with **26 authorized existing code/test/documentation/log paths** separately reviewed and no unexpected exceptions. Original sketches have no EXIF GPS metadata and retain their original hashes. Annual rainfall remains 11,315 rows/365 dates/31 identifiers; GFD counts 33/23/2/329; hydrology 1,697 observations/81 cases/14 eligible rows/33 unresolved disagreements. Saved model SHA-256 remains `f3fa9b53d7047746f9d26cba8556705fb3fd2328128a236cb4f423575acf4316`.

Iteration corrected actual Home card overlap, historical-feature click/zoom timing and compact Admin map accessibility. Tests now navigate the supported initial context map and unique accessible selectors; original source/geometry/security assertions are retained. Original `weather-freshness.spec.js`, protected GIS tests and scientific source records remain unchanged. Existing jsdom/Starlette warnings are nonfatal. Browser artifacts stay local, outside the commit.
