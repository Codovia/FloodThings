# FloodPulse current capabilities

This is the current application summary. Dated research reports retain their
historical findings; they do not establish new operational coverage.

The primary objective is **actual Karnataka flood-occurrence prediction**. The
[Phase 12A foundation](FLOOD_OUTCOME_FOUNDATION.md) audits retained flood evidence
and daily-label training prerequisites. Its current decision is **NO-GO**: no
scientifically eligible daily flood labels, verified negatives or independent
flood test set. The experimental rainfall classifier remains a separate model.

[Phase 12C Groundsource extraction](GROUNDSOURCE_KARNATAKA_EXTRACTION.md) verifies
19,854 Karnataka candidate news records: 18,194 state-contained/date-usable and
17,296 additionally contained in one source district. All 31 fixed SOI source
district polygons have candidates; current LGD identities remain unresolved.
All records require manual verification, with zero eligible predictive positives
or defensible negatives. Operational forecasts are unchanged. The
[Phase 12B observation protocol](FLOOD_OBSERVATION_FEASIBILITY.md) still governs
the distinction between acquisition truth, daily occurrence and absence evidence.

| Route | Implemented capability | Limits |
|---|---|---|
| `/` | Accuracy-aware GPS/manual location, map, current weather, hourly rainfall and nearby river availability | Naming disabled without reviewed MapTiler access; zero approved v4 river associations; warning feed not connected |
| `/weather` | Real Open-Meteo weather, up to seven local-calendar forecast days, rainfall chart and saved inference | Six-hour browser-session refresh; no refresh with the browser closed |
| `/flood-map` | District filtering, independent historical/hazard/drainage/shelter layers and details | 56 original Udupi GFD polygons; zero verified potential-hazard polygons |
| `/shelters` | Reported Open entrances, capacity/facilities, timestamps and external directions | No invented destinations in empty/unavailable states |
| `/admin` | Protected shelter editor, manual verification, audit history and reviewed Telegram drafts | No public registration or automatic model-triggered messages |

## Geographic and scientific coverage

Directory v2 has **31 NIC district names, five selectable points** (Udupi, Karkala,
Kundapur, Saligrama and Mangaluru), and reviewed public navigation bounds for Udupi
and Dakshina Kannada only. Kaup remains disabled; current LGD reconciliation is
unresolved. District filters, weather points and historical features have different
meanings. A district name is never an invented weather coordinate. Citizens use
names, GPS or map clicks; coordinate entry is confined to the private shelter editor.

The 56 displayed historical polygons remain the original 33 cells for GFD 2728 and
23 for GFD 3551. Mechanisms remain Unknown unless independently evidenced. Missing
observation is not a flood-negative label. The existing 3 km Udupi research window
provides elevation, slope and land-cover previews. Its bounded OSM drain/ditch query
returned zero ways; this does not establish absent drainage or predict overflow.

`rainfall_logistic_v1` supports only retained **Kundapur and Mangaluru** points. Its
target is a model-grid proxy for **at least 64.5 mm rainfall over the reported rolling
24-hour UTC horizon**, not flooding. Retained holdout precision is **14.50%** and
recall **91.67%**. No calibrated probability is exposed. Retrospective ERA5 training
and live model inputs have proxy parity requiring validation. Unsupported points
or missing inputs return unavailable. Validated flood prediction remains unavailable.

## Shelter freshness and directions

The directory and enabled Flood Map shelter layer share `useShelterDirectory.js`.
An active view checks immediately and at most one minute after a successful receipt,
earlier if facility verification expires. Tab visibility, focus and network restoration
recheck availability. Hidden routes/layers cancel polling. Concurrent requests for
the same view are coalesced; requests time out after 15 seconds. Failed checks clear
destinations, with a 30-second cooldown for automatic activation attempts and no
automatic retry loop. Manual retry is available.

Browser receipt/check age, server `retrieved_at`, administrator `verified_at`, and
`verification_expires_at` remain distinct. Backend verification expires after 24 hours.
A fresh response does not renew facility verification, guarantee capacity or reserve
a place.

Choose **Recheck availability for directions**. A successful latest-directory check
must include the same Open, unexpired entrance with spare reported capacity. Only
then is a directions link revealed, for five seconds. Use that second explicit
action to open Google Maps. Errors or changed/removed entrances do not create
substitute routes. Directions are **not flood-safe**; confirm access with responsible
staff before travel.

## Administrator prerequisites and safeguards

Use `./start.sh` and its printed `/admin` URL. No account or default password is
created by this checkpoint. An authorized maintainer supplies the documented private
maintenance connection in their own shell and runs the existing provisioning utility:

```bash
cd backend
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME
```

It prompts privately for a password. Never give maintenance credentials to the API
process or commit them. See the [README](../README.md) and
[demonstration guide](RELEASE_DEMONSTRATION.md) for setup.

Changes to identity, address, district, entrance, capacity, occupancy, water, toilets,
accessibility or restrictions clear earlier confirmations and evidence. Review the
latest values before confirming Open/Full. Backend authorization, CSRF, revision
concurrency, capacity/status constraints and audit history remain mandatory.
Internal note edits do not recenter the entrance map.

Private requests are bounded to 15 seconds and guarded after cancellation, unmount
or session expiry. Logout immediately clears private state. A failed logout request
does not prove server-cookie revocation. Lost write responses do not prove failure:
refresh assignments/history before retrying; writes and sends are never retried
automatically.

Telegram still requires authorized configuration, preview and explicit approval.
No message is sent by this checkpoint. MapTiler satellite/hybrid and building search
remain configuration-blocked until authorized settings and actual tile loading are
verified. Reference names/imagery cannot establish shelter authorization, usability,
occupancy or road access.

## GIS runtime and future packaging

Research previews still depend on retained local TIFFs and manifests; a fresh clone
without them cannot serve every preview. Missing assets must remain explicit.
Restricted Survey of India geometry/derivatives stay local. No new asset
redistribution is performed.

A future display package should be a separate version with an allow-list of
individually reviewed publication-permitted assets, source/licence metadata and
SHA-256/size validation for every file. Keep original archives and reproduction
manifests separate and unchanged; reject missing/mismatched assets. Do not include
restricted boundary-derived products or expand the existing polygons' hazard meaning.

## Wireframe-based public and administrative workspaces

The five original JPGs are available in `docs/design/floodpulse_wireframes/`, with a byte/hash manifest and interpretation guide. Home follows sketch 01 (citizen information left, 60% Karnataka map right, location bar and three compact summary cards above); Weather follows 02 (point weather/forecast/experimental AI left, synchronized geography right); Shelters follows 03 (fresh directory left, verified-entrance map right); authenticated administration follows 04 (district-focused assignments/editor left, facility inspection right). The dedicated Flood Map retains 56 historical polygons and independently controlled honest zero-hazard coverage.

One public selected-district filter is shared across routes. It is distinct from the selected weather point and selected historical evidence feature. A name-only district never generates a weather coordinate. The shared name search has unique accessible control IDs and cancels work when inactive. The weather session pauses on Flood Map, Shelters and Admin, retains the last selected-point receipt, and checks six-hour freshness on return. Unsupported AI points are declared ineligible before calling inference. Public coordinate-entry forms remain absent.

The shelter page uses one freshness-checked directory response for its list and map, including an empty map context when no destinations exist. Existing one-minute freshness, verification expiry and explicit directions revalidation remain enforced. Admin filtering is over the loaded bounded assignment page, with pagination and an explicit limitation; it is not a claim of a complete district count. Admin district context never shares private state with public selection.

Sketch 05 is a future moderated workflow, documented in [Experimental Flood Reporting Design](EXPERIMENTAL_FLOOD_REPORTING_DESIGN.md). No report route or upload is active. See [implementation and verification mapping](WIREFRAME_IMPLEMENTATION.md). Satellite/building services remain configuration-blocked without authorized MapTiler settings; no warning feed, hazard geometry, new shelters, Telegram delivery or flood prediction is fabricated.

## Home emergency dashboard

Home requests one bounded high-accuracy browser fix on the first tab-session visit. A radius above 100 m (application policy, not certified accuracy) keeps statewide framing, prompts town selection and cannot establish local Home weather or river focus. Accepted precise GPS keeps its actual coordinates. Manual choices win over late GPS/geocoding; only a non-location attempt flag is stored. Optional MapTiler naming is disabled in the verified configuration because authorized credentials/rights/quota were not established. Provider labels require a matched locality polygon covering the accuracy area, never a nearest-town substitution or inferred canonical district.

One shared request supplies validated Open-Meteo current fields, hourly precipitation and seven daily rows. Home shows “Next 24 full forecast hours: X mm” only for exactly 24 consecutive preceding-hour intervals with valid mm values and explicit IST endpoints; no interpolation or daily substitution. Current estimates are model output, expire after 90 minutes and retain explicit freshness/missing states. The six-hour session retrieval cadence remains.

Home no longer fetches/displays historical cells, shelter lists/markers or their controls; those original data and protections remain on Flood Map, Shelters and Admin. The three summary cards remain. Flood availability, “Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.” and official feed “Not connected” stay visible above internal scrolling. The map shows accepted location/state context and only independently verified fresh river cells, of which production currently has zero.

Two bounded real Open-Meteo GloFAS forecast-v4 checks returned seven GMT discharge/mean/p25/p75 rows in m³/s. The API lacks river identity/native release/issuance, and retained v5 screening cannot establish v4 channel/viewing-area associations. These research samples do not activate local forecasts, flood probabilities, danger categories or inundation geometry. The read-only adapter defaults unsupported without a reviewed association. Phase 12G training NO-GO and pending CWC clarification remain unchanged.

At 100% Chrome zoom, Home document heights are exactly 768/900/1080 px for the required desktops; 390×844 retains natural scrolling. The 40% panel/60% map, navigation, resize, accessibility and scientific limitations remain. See [Home implementation](HOME_EMERGENCY_DASHBOARD.md) and [Sprint 13 live evidence, access and blockers](SPRINT_13_HOME_LOCATION_RIVER_OUTLOOK.md).
