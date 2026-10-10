# FloodPulse — Five Original Handwritten UI Wireframes

These five images are the original user-supplied photographs, copied byte-for-byte. They are the design references for the existing FloodPulse application (NOT screenshots of the current frontend). This brief helps read the handwritten text; **inspect each image directly** before implementing. Where handwriting is unclear, treat the notes below as an interpretation rather than an exact quotation.

## Source-derived intentions: what each drawing asks for

1. **`01_home_emergency_dashboard.jpg` — Home Page: Emergency Dashboard**
   - Page title/subtitle and navigation across the top.
   - A left-hand information panel with emergencies and details of relevant district places.
   - A large Karnataka map on the right highlighting flood-danger / affected places where supported.
   - The main screen should look like an integrated emergency dashboard.

2. **`02_weather_and_prediction.jpg` — Weather & Prediction**
   - District dropdown on the left.
   - Weather information and prediction/risk details for the selected district/location.
   - A Karnataka map on the right, focused on or highlighting the selected district and showing relevant marked places.
   - Selection, information panel and map must be visibly connected.

3. **`03_emergency_shelters.jpg` — Shelter**
   - District dropdown on the left.
   - Concise list/details of shelter places in the selected district.
   - Map on the right showing shelter places in that district.

4. **`04_admin_after_login.jpg` — Admin (authenticated)**
   - District selection and shelter list/status/count in the left panel.
   - Right-hand map of the selected district.
   - Administrator inspects/selects a building/location on the map and assigns a suitable location as a shelter.
   - A form/editing area on the left supports assignment details and confirmation.

5. **`05_experimental_report_flood.jpg` — Experimental flood reporting**
   - A future flow using GPS/location map and a camera/photo.
   - A person can document and report a flood for review/future improvement.
   - Explicitly drawn as **experimental**, not an already-deployed authoritative flood warning.

## Decisions from conversation and completed Codex architecture audit

These requirements supplement the drawings and **are not represented as verbatim handwriting**:

- Keep the five current public/admin routes `/`, `/weather`, `/flood-map`, `/shelters`, `/admin` and existing navigation, while making each feel like a focused desktop page. The user specifically wants a distinct Flood Map explorer in addition to the sketches.
- Favor a responsive left information panel + right primary map on desktop; mobile layouts stack and scroll naturally. Do not conceal critical information inside unusably small scroll boxes.
- One searchable district/locality selector shared across public pages. Public users type names, not latitude/longitude. District filtering and verified point-weather selection are separate states; selecting a district without a verified point must **not** invent a point or district-wide weather.
- Flood Map has separate historical-flood and published-potential-hazard layers, drainage context, district filtering, clickable evidence details, provenance, unknown mechanism where unsupported. District dropdown has 31 names; verified display data is limited to 56 GFD historical polygons from 2 Udupi events; potential hazard polygons currently 0.
- Historical recorded water or drainage geometry does not by itself establish current high risk. No fabricated district risk counts, site-level labels, flood warnings, severity bands or shelter availability.
- Existing experimental rainfall model predicts heavy rain, **not flood occurrence**; its supported inference points are Kundapur and Mangaluru only. Retain experimental designation and limitations.
- Admin site keeps secure login, shelter entrance confirmation, authorization/usability/capacity/verification checks, auditing and separate human-approved Telegram operations. Satellite/hybrid option is contingent on separately authorized imagery credentials. No auto-classification of buildings as shelters.
- The fifth drawing's GPS/photo reporting is a **future proposed module**; design-only until privacy, secure storage, verification, moderation and public publication policy are approved. Do not auto-publish reports as confirmed flood evidence.
- Use the completed integrity checkpoint on commit `665507eaa52337ec818df160e81c60d303562563` as the baseline, verify current HEAD before modifying code. Preserve existing fixes for shelter freshness, edit invalidation and session protections.
- Respect existing protected data, ignored credentials, untracked `QandA.md` and unrelated `backend/.env.example` edits. Never stage restricted data.

## Implementation / review acceptance criteria

- The five original sketch images are genuinely accessible to Codex; cite the specific image file used for layout changes.
- Home is emergency-overview first, Weather & Prediction is environmental-information first, Shelters is verified-availability first, Admin is facility-management first; Flood Map is a dedicated evidence workspace.
- At 1366×768, principal heading, location control and main content/map are visible and usable, without clipping; small/zoomed screens remain scrollable.
- District selection is consistent across routes; verified point location and inspected evidence feature remain distinct.
- Empty/unavailable data is rendered honestly; no risk claims are made from absent evidence.
- External map tile provider policies, attribution and optional satellite credentials are respected.
- No regressions to live Open-Meteo weather, saved model inference, GFD polygons, PostgreSQL/PostGIS, admin auth, shelters, Telegram safeguards.
- Compare independent-browser before/after screenshots with these photos; verify frontend/backend/integration/browser tests and protected file hashes.

## Operational notes

- These are scanned photos of handwritten sketches, **not production-ready design files**. Layout details need professional interpretation and responsive behavior.
- Confirm the currently reported `665507eaa52337ec818df160e81c60d303562563` state and any intervening changes before implementation.
- Implement in coherent phases with concrete acceptance criteria; don't attempt flood ML retraining, synthetic GIS generation or irreversible database migrations as part of frontend layout work.
