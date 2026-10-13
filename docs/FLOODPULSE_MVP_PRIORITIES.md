# FloodPulse — Deadline-Driven MVP Decisions

**Decision date:** 2026-10-13  
**Target demonstration:** 2026-10-16  
**Status:** User-approved priority change; implement against actual repository state.  
**Scope:** Karnataka personal/academic project, existing React + Vite, FastAPI, PostgreSQL/PostGIS, Leaflet, Telegram; no unnecessary rewrite.

## 1. The core product and USP

FloodPulse is primarily an **AI-assisted flood emergency reporting, alerting, shelter management and evacuation-support platform**, **not** primarily a statewide flood prediction research project.

Core citizen workflow:

1. Citizen opens Home; application attempts automatic GPS detection and town/city naming; otherwise gives a clearly marked approximate location with an easy fallback.
2. Citizen views source-timestamped local weather, any valid official warnings, and an appropriately labelled experimental flood/rain/river *indicator* only where supported.
3. Citizen receives a meaningful admin-approved/official alert, not a fictitious AI-generated emergency warning.
4. Citizen finds **actually verified open shelters** on the map and can request directions from an adequately determined current location.
5. Routing uses a real provider, and routes are explicitly **NOT CERTIFIED FLOOD-SAFE** unless verified closure/hazard/road-access evidence supports that claim. If verified blocked-road data is available, honor it; otherwise show warnings and do not say “safe route”.
6. Citizen submits a GPS-located, time-stamped photo/camera report of flooding, waterlogging or blocked/drainage-risk conditions, with description, consent and clear user-reported status.
7. Admin reviews incoming report and image-derived *suggestions*, approves/rejects or requests correction, and manages shelter locations, entrances, operational status and alert dispatch on maps.
8. Approved reports form a **provenance-aware, future ML dataset** without fabricating observations, labels or negatives.

## 2. Priority order and deadline

**P0 — Demonstrable emergency workflow:** admin login and map-based shelter creation/verification; public verified shelter map and directions; explicit route limitations; human-approved Telegram alerts with dedupe, test delivery, clear subscription/opt-out and receipts; automatic name-based location / actual weather. Prove one coherent end-to-end flow first.

**P1 — Citizen reporting and admin verification:** public GPS/camera/gallery report submission; privacy-aware upload; admin map moderation; image-feature extraction with explicit uncertainty; event log and dataset export. Keep unverified reports separate from confirmed events.

**P2 — Minimal experimental prediction/indicator:** small reproducible research/demo component from legitimately sourced input, preferably existing Open-Meteo 24-hour rainfall and separately verified GloFAS reach, plus any scientifically usable labels if independently reviewed. Do not claim validated binary flood prediction in places without eligible labels. Keep experimental outputs separate from official warnings and never auto-trigger evacuation/Telegram.

**P3 — Polishing/coverage expansion:** advanced maps, expanded statewide coverage, external CWC metadata, high-confidence site-specific flood model, richer imagery and analytics. These cannot block the MVP.

Stop lengthy river-gauge historical research unless required by a specific P0/P1 deliverable; CWC enquiry was sent and remains pending. Scientific Phase 12G training NO-GO is retained for any claim of a validated flood-outcome model; **implementation of the MVP must not wait for CWC's reply**.

## 3. Explicitly requested Home correction

- Current Sprint 13 implementation incorrectly makes manual place selection mandatory when geolocation has poor accuracy (>100 m) and its geocoder is disabled. Replace the blanket cutoff with purpose-specific uncertainty handling.
- Try standard browser geolocation with permission, then a *working, authorized* reverse geocoding source for name/city if justified; coarse browser accuracy ~280 km cannot support a precise location claim. If permitted network-based city estimation or a previously **user-approved** place is available, show it with source/approximate label rather than misrepresenting it as GPS. Do not silently guess the town.
- Automatically fetch model weather for an accepted point; if approximate, label its spatial uncertainty. Maintain existing validated Open-Meteo hourly precipitation aggregation and timestamps.
- Replace repetitive “Your Area Emergency Summary” with **“Local Conditions & Flood Outlook”**: named location + source, actual current conditions, next-24-full-hour rainfall and window, nearby approved river data or clear unavailable, authoritative alert status, minimal meaningful guidance. Reduce repetition and empty space.
- Keep Home 1366x768 at 100% zoom: no whole-page desktop scroll; desktop ~40% information / 60% interactive map, mobile natural scrolling.
- Do not restore dedicated Home shelter/historical-evidence sections merely to pad the screen. Shelters remains a separate route; a compact direct shelter link or safety action is permitted if useful.

## 4. Emergency shelters and route safety contract

- Admins must log in and map-pin true entrances, name, contact/address, authorizing source, capacity, occupancy, verified-at, expiry, operational Open/Full/Closed/Pending; record evidence and an audit trail. No manufactured operational facilities.
- Display only authorization-qualified, unexpired and Open shelters with usable entrances. Capacity is not a reservation. Zero verified shelters must remain zero in public view.
- The user chooses a verified destination; routing service returns a road route and directions only after coordinates are suitable and the route/provider is available.
- **Never call a general navigation route “safe from flooding” by default.** Official road closures/verified hazards and access confirmation are independent inputs; where missing, show “Route safety not verified; check closures and local authorities”. Do not claim a route avoids floodwater if no verified road-closure coverage.
- Demo-only facilities may exist only in an isolated, clearly labelled test environment and never as real public shelters.

## 5. Alert contract

- Continue the existing Telegram-only design (no SMS/email rollout).
- Differentiate OFFICIAL_WARNING, ADMIN_ALERT, CITIZEN_REPORT and EXPERIMENTAL_MODEL_INDICATOR. Reports and AI indicators are NOT automatic public flood warnings.
- Authenticated admin reviews precise content, affected geometry, expiry, recipient targeting and source before explicit send. Include dedupe, rate limit, opt-in/out, delivery status/audit. No pretend-delivered messages.
- If Telegram credentials or subscribers do not exist, finish testable previews/contracts and report what requires user-side bot configuration. Avoid secrets in Git.

## 6. Photo/GPS citizen report and dataset contract

MVP report fields: report UUID, source `USER_REPORTED`, event type (flooding/waterlogging/drainage blockage/other), description, client-observed timestamp + server receipt timestamp (UTC), GPS position with horizontal accuracy & consent, optional approximate place label, photo object reference + cryptographic hash, submitter optional/pseudonymous ID, moderation state, evidence provenance, audit history.

Required states: SUBMITTED -> UNDER_REVIEW -> APPROVED/REJECTED (with reviewer, UTC time, reasons); allow duplicate grouping and corrections. Public display must not leak precise private addresses/identities. Never publish reports as verified before approval.

Camera/gallery upload: supported MIME and file-size controls, content sniffing, safe generated names, object-level access, optional metadata stripping for publicly served images, retention and abuse protections. Camera permission only after an explicit user action. Handle inaccessible GPS and missing photos transparently.

Image analysis: start with defensible, inspectable extraction: genuine image dimensions, format, captured EXIF timestamp/GPS **if present and permission/licensing allow**; compare EXIF to submitted GPS/time and flag differences. Optional genuine licensed pre-trained vision model can suggest floodwater, blocked drain, debris, road waterlogging *with uncertainty*, clearly labelled `AI_SUGGESTED`, requiring admin confirmation; if no supported model, do not fabricate image-derived labels. Never estimate water depth, affected houses, persons or exact road closures purely from unsupported pixels.

Future training dataset: store raw report (restricted), derived model suggestions, admin-reviewed outcome, identity/time/source provenance, image hash/URI and license, environmental feature snapshot with *issue time* and observed time, spatial/time joins and uncertainty. Keep citizen reports and approved events separate from model-ready positive/negative label eligibility. No negative labels from lack of reports, no unreviewed images as truth, no hindsight leakage. No default auto-training.

## 7. Prediction MVP scope

Ship a working, explainable experimental indicator endpoint/UI based on real sourced time-stamped inputs. Example: next-24-full-hour rain accumulation + separately verified hydrological river forecasts and source availability. If event-positive/negative labels do not pass review, **do not call it a trained flood-occurrence AI model or a calibrated flood-risk probability**; display `EXPERIMENTAL — NOT AN OFFICIAL FLOOD WARNING`, explain supporting inputs, coverage, uncertainty and limits. A rainfall classifier is rainfall inference, not flood occurrence. Keep research training NO-GO as recorded. User prefers this minimal honest demo over further deadline-blocking research.

## 8. Engineering / scope control

- Reuse current components/contracts wherever possible; build thin vertically integrated features with tests and real database migrations only when required.
- No fake GIS/weather/evacuation/shelter assets in operational product. Isolated labelled test fixtures permitted.
- Keep sensitive uploads and original research data off Git; retain provenance and data licenses.
- Preserve unrelated `backend/.env.example`, `QandA.md` and previous protected research artifacts; don't use destructive Git cleanup.
- Append a concise sprint outcome to root `update.md`; report actual live vs mocked verification separately.
- Avoid feature-bloat and wide architecture rewrites. Stop at a functioning end-to-end demo by 2026-10-16.

## 9. Definition of Done for user demo

At least one real, demonstrable flow: choose/detect location -> real local weather -> citizen GPS/photo submission -> admin reviews pinned report and image suggestions -> approves or rejects -> admin verifies an actual shelter (or demonstrate on isolated named test fixture) -> citizen requests directions with limitations -> admin explicitly sends a Telegram alert to a real subscribed test user (if credentials configured) -> audit logs and future dataset entries visible. An experimental weather/river indicator is secondary and never presented as a verified flood warning.
