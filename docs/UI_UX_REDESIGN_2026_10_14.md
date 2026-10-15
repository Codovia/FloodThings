# FloodPulse demonstration UI/UX review

Requested filename retained; research and implementation started **15 October 2026**, for the 16 October demonstration. Scope: frontend presentation, accessibility, tests and documentation. No real participant study or WCAG conformance certification is claimed.

## Phase A — research and decisions

Published guidance consulted on 15 October:

| Source | Guidance applied |
|---|---|
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Keyboard access, meaningful headings/labels, status announcements, visible/unobscured focus, contrast, reflow and target sizing. AA minimum targets are 24 CSS px subject to exceptions; our ordinary control target is 44 px. |
| [NN/g progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Prioritize common tasks and disclose specialist information on request. Critical safety and privacy information stays outside collapsed sections. |
| [GOV.UK Design System](https://design-system.service.gov.uk/) and [question pages](https://design-system.service.gov.uk/patterns/question-pages/) | Specific headings, short helpful instructions and coherent question groups. A wizard is not automatically better; preserve a short, editable form with clearly numbered sections. |
| [GOV.UK confirmation pages](https://design-system.service.gov.uk/patterns/confirmation-pages/) | Confirm completion, show a reference and explain what happens next. FloodPulse cannot restore a lost withdrawal key; say so explicitly. |
| [USWDS](https://designsystem.digital.gov/) and [alerts](https://designsystem.digital.gov/components/alert/) | Consistent components and contextual, actionable feedback; use text as well as color. Avoid turning ordinary unavailable data into an emergency alarm. |

These are published design recommendations. The choices below are project-specific engineering/design judgments, not findings from user testing.

### Prioritized findings from source inspection

1. Reporting and Telegram subscription routes exist but are absent from primary navigation; Home action links sit among weather details.
2. Citizen reporting puts incident, location, photo and long consent text in one fieldset; review lacks a clear focus transition and incomplete forms do not explain the disabled Review action.
3. Moderation places raw image JSON and hashes before decisions. Queue selection and detail need clearer hierarchy; retention is too prominent beside routine refresh.
4. Shelter forms contain many controls without meaningful groups. Explicit verification must remain visible and independently confirmed.
5. Desktop admin forms have nested constrained scrolling and small text. At narrow widths, headers and long strings need robust wrapping. Disclosure summaries need visible keyboard focus.
6. Notification composition/preview/approval/history are implemented securely but their sequence needs an explicit visual explanation. No notification will be sent in this work.

### Before / after information architecture

| Area | Before | Implemented after |
|---|---|---|
| Navigation | Five routes; report/alerts reached indirectly | Seven existing routes; report and Telegram directly discoverable, correct page titles |
| Home | Location, weather/rain/unknown forecast, dense context and map | Same truthful essentials plus prominent citizen actions before specialist context |
| Citizen report | One long fieldset and inline review | Numbered incident → location → optional photo/consent → review; explicit readiness and completion feedback |
| Admin reports | Queue/map with raw metadata in decision path | Queue → selected evidence → reason/decision; technical metadata/export JSON on request |
| Shelters | Long ungrouped editor | Identity/entrance, facilities/capacity, availability/verification, restrictions/notes; all original controls retained |
| Notifications | Composer, preview, history | Clearly named compose → exact preview → explicit approval → result sequence; unchanged send logic |

### Design system and implementation boundary

Use existing system fonts, dark ink, restrained teal actions, pale neutral surfaces, consistent spacing and borders. Use generous control targets, underlined text links, strong focus outlines, text statuses, bounded readable line lengths and mobile stacking. Keep Home's 1366×768 map/essential-summary contract; allow natural document flow for task-heavy pages and enlarged text. No added framework or dependency.

Initial file scope: `App.jsx`, `AppNavigation.jsx`, `HomeEmergencyDashboard.jsx`, `CitizenReport.jsx`, `PublicShelters.jsx`, `AlertSubscription.jsx`, `WeatherPanel.jsx`, `AdminShelters.jsx`, `AdminReports.jsx`, `AdminNotifications.jsx`, a scoped `UserExperience.css`, frontend unit/browser tests and this document/`update.md`. Original APIs, request payloads, auth/CSRF, mode flags, source data and delivery logic remain authoritative. Existing wireframes are references, not mandatory layouts.

## Phases B and C — implemented changes

Citizen goals: recognize the selected location and actual data status, then find reporting, shelter or subscription actions quickly. Administrator goals: inspect private evidence before deciding, keep verification independent and control each notification explicitly. No participant interviews, field observations or usability study were conducted.

- Primary navigation exposes all seven existing routes and gives reporting/subscriptions correct document titles. Home adds a prominent citizen-action area without loading invented shelters or hazards.
- Citizen reporting groups incident, optional GPS/manual position, optional photo/consent and review. Readiness text explains missing requirements; review/error/receipt transitions move focus. Completion and withdrawal explanations reflect the actual in-memory withdrawal-key limitation. A direct map link preserves manual selection when GPS or tiles fail.
- Subscription information distinguishes project notices from official warnings and provides an explicit setup retry. Public shelter cards add a textual Open/entrance status; original freshness, capacity, restrictions and recheck-before-directions controls remain.
- Moderation shows queue selection, location uncertainty and evidence before specialist metadata. Image provenance and export JSON remain available through native disclosures. Retention maintenance is separate from ordinary review. No request payload or moderation rule changed.
- Shelter fields are grouped into identity/entrance, facilities/capacity/contact, availability/verification and restrictions/notes. All four confirmations remain independent, visible and initially unchecked; edits still clear them.
- Notification composition shows the full sequence and focuses the exact server preview. Consent/destination controls, explicit approval and sender/deduplication code are unchanged. Existing send regression results are mocked; no live message is authorized by this work.
- Shared styling improves contrast, control sizes, focus, form grouping and mobile wrapping. Long admin/report pages use natural scrolling; Home retains its desktop viewport/map split. Existing weather/model and historical-map contracts remain; source/uncertainty disclosures are retained.

Original wireframe images and current screens were inspected as references. The task-heavy admin layout deliberately moves away from fixed-height nested editor panes.

## Verification record

All final relevant checks passed. Tests and screenshots do not establish emergency-service readiness or WCAG conformance.

| Check | Result | Scope |
|---|---|---|
| Frontend unit regression | **278 passed**, 26 files | Includes report focus/readiness, retry, queue transitions and all existing scientific/security UI contracts |
| Backend security/image/notifications | **67 passed** | Existing unit checks; notification-provider outcomes mocked |
| PostgreSQL/PostGIS integration | **68 passed** | New disposable container, UUID test databases/roles; original migrations and restricted grants exercised without altering existing databases |
| Installed Chrome full regression | **89 passed**, exit **0**, 3.3 min | Real isolated login/logout/CSRF, report/photo → moderation/audit/export → shelter map/Pending/Open/Closed → public discovery/exact directions; mixed provider/HTTP fixtures identified by their tests |
| Final UX screenshot/fixture repeat | **5 passed**, exit **0** | Final credential-free capture, mocked draft history, keyboard, overflow, enlarged text, zoom-equivalent reflow and sampled 4.5:1 text contrast |
| Production build | **PASS** | 68 modules; existing bundle advisory remains (~696 kB JavaScript before gzip); no added dependency |
| Preservation | **PASS** | All 18 live table count/content fingerprints unchanged; 233 protected tracked/config file hashes unchanged. API/backend/model/migration/data/launcher files and private root configuration preserved |

The first full regression found the intentional admin-heading change and a joined-test timing assumption. Its weather wait coincided with the backend provider deadline. A later run exposed real provider dates outside the accepted local week: backend correctly returned 503, and the test incorrectly waited for inference despite no usable weather receipt. The corrected test explicitly checks honest 503/unavailable behavior and continues the independent response journey; it never inserts fallback data. Existing unit coverage independently verifies zero model requests without weather. Later real provider retrieval and supported inference succeeded, as recorded below. No backend date-validation or model rule was relaxed.

**Live versus simulated:** the joined journey used real restricted PostgreSQL transactions, original authentication/CSRF, actual image decoding, audit and export. Incidents, photo, shelter authority/capacity and GPS overrides are explicitly invented test fixtures. Preview/send outcome regression tests elsewhere simulate Telegram responses; the added preview test sends nothing. No real Telegram request/send or webhook/consent mutation occurred. External directions were checked for exact origin/entrance parameters, not newly certified road safety or a new live provider route.

**Fresh provider evidence:** at **15 October 00:30 IST**, selected Kundapur weather returned HTTP 200, **26.2 °C**. An independent sum of 24 consecutive hourly intervals reproduced **2.7 mm**, **15 October 01:00 → 16 October 01:00 IST**. Live saved `rainfall_logistic_v1` inference also returned HTTP 200, `experimental=true`, `probability=null`, below-heavy-threshold classification. This is rainfall inference, not flood occurrence or safety. [Sanitized receipt](verification/ui_ux_2026_10_15/live-weather-indicator-summary.json), [actual Home](verification/ui_ux_2026_10_15/after-home-live-weather.png), [isolated public directions](verification/ui_ux_2026_10_15/after-isolated-shelter-directions.png).

Private raw logs/receipts/exports were written under `/tmp/floodpulse-ux-verification` and the existing test evidence directories, excluded from Git. Those temporary logs were no longer available after the execution environment interruption; the pass/exit and preservation summaries were observed directly before interruption. The sanitized provider receipt and reviewed screenshots are retained in this repository. Test-only containers were removed after completion; no persistent interactive demo was provisioned. Live authentication remains blocked. Existing Starlette/httpx and jsdom mock-navigation warnings are not live-browser failures. Original research/model artifacts and the Phase 12G scientific training NO-GO are unchanged.

## Demonstration-day UI checklist

- Confirm DEMO ONLY banners and the correct isolated environment before entering invented records.
- Use an explicit location; explain GPS uncertainty, weather source/time, unavailable official warning/flood forecast and experimental rainfall limits.
- Submit an owned non-personal photo report; keep its tab open for withdrawal.
- Review evidence with the separate demo administrator; record a reason and show restricted provenance without claiming flood ground truth.
- Renew all shelter confirmations on 16 October; recheck eligibility before exact-entrance directions. State route safety is unverified.
- Show existing sanitized Telegram acceptance evidence only; do not send another alert.
- Check keyboard/mobile/network behavior on the actual presentation device; sign out and withdraw demo evidence at the end.

## Screenshot evidence

All images are actual rendered Chrome sessions. These layout images use explicitly isolated HTTP fixtures, not real incidents or staff accounts. External providers are blocked in the layout checks, so tile-unavailable messages are intentional recovery-state evidence.

| Before | After | Interpretation |
|---|---|---|
| [Desktop Home](verification/ui_ux_2026_10_15/before-home-desktop.png) | [Desktop Home](verification/ui_ux_2026_10_15/after-home-desktop.png) | 1366×768, GPS denied, unknown weather/flood outlook, direct citizen actions |
| [Mobile report](verification/ui_ux_2026_10_15/before-report-mobile.png) | [Mobile report](verification/ui_ux_2026_10_15/after-report-mobile.png) | 390 px, numbered editable groups and readiness feedback |
| [Admin login](verification/ui_ux_2026_10_15/before-admin-login.png) | [Admin login](verification/ui_ux_2026_10_15/after-admin-login.png) | No entered credentials; typography and navigation |

Additional after images: [shelter editor fixture](verification/ui_ux_2026_10_15/after-admin-shelter-fixture.png), [exact notification preview fixture](verification/ui_ux_2026_10_15/after-notification-preview-fixture.png). The preview screenshot is a mocked draft with unchecked approval and no send; it is not delivery evidence.

## Manual accessibility and operating limits

The automated checks cover explicit keyboard transitions, semantic labels/groups, overflow at 320/390/768/1366 px, 200% root text enlargement and 683×384 CSS-pixel reflow equivalent to a 1366×768 desktop at 200% zoom. Operating the actual Chrome zoom menu at 200%, screen-reader speech, every color/state contrast, native GPS/camera and the college device/network still require human checks. Sampled contrast checks do not establish full WCAG 2.2 AA conformance. Maps retain list/selector/coordinate alternatives; map tiles, live weather and external directions still depend on providers. No new routing safety evidence or flood model is introduced.

A persistent interactive demo database remains a separately approved setup task. Tests create disposable UUID databases and do not prepare or authenticate the existing live account. Its password-rotation gate remains in force. Existing Telegram acceptance evidence remains available; no webhook or consent setting is changed.

## Changed-file manifest

Frontend presentation and UI tests (no backend implementation change):

- `frontend/src/AdminNotifications.jsx`
- `frontend/src/AdminReports.jsx`
- `frontend/src/AdminReports.test.jsx`
- `frontend/src/AdminShelters.jsx`
- `frontend/src/AlertSubscription.jsx`
- `frontend/src/AlertSubscription.test.jsx`
- `frontend/src/App.jsx`
- `frontend/src/AppNavigation.jsx`
- `frontend/src/AppNavigation.test.jsx`
- `frontend/src/CitizenReport.jsx`
- `frontend/src/CitizenReport.test.jsx`
- `frontend/src/HomeEmergencyDashboard.jsx`
- `frontend/src/HomeEmergencyDashboard.test.jsx`
- `frontend/src/PublicShelters.jsx`
- `frontend/src/UserExperience.css`
- `frontend/src/main.jsx`
- `frontend/tests/mvp-e2e.spec.js`
- `frontend/tests/shelters.spec.js`
- `frontend/tests/ui-ux.spec.js`

Documentation: this file and the chronological `update.md` entry. Credential-free evidence: the ten PNGs and `live-weather-indicator-summary.json` under `docs/verification/ui_ux_2026_10_15/`, linked above. Existing unrelated `backend/.env.example` and `QandA.md` remain untouched and excluded.
