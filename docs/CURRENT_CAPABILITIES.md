# FloodPulse current capabilities

This is the current application summary. Dated research reports retain their
historical findings; they do not establish new operational coverage.

| Route | Implemented capability | Limits |
|---|---|---|
| `/` | Location, map, weather, experimental rainfall and shelter overview | Point information; no connected official emergency-warning feed |
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

## Pending design work

The five handwritten wireframes were absent from accessible attachments and the
repository. Map-centred layout implementation, further shared-location consolidation
and the future GPS/photo-reporting design await those actual references. No public
reporting submissions are enabled. Reports must remain unverified pending an approved
privacy, moderation and administrator-verification workflow.

Statewide hazard coverage, flood probability/risk classes, drainage-overflow
prediction and automated emergency/evacuation alerts remain unavailable.
