# FloodPulse college demonstration rehearsal

**Rehearsed:** 14 October 2026, IST. **Presentation:** 16 October 2026.

**Implementation baseline:** `c27200a219d460ddff6562ad862412c120bbc90b`, `feature/karnataka-data-foundation`.

The emergency-response journey is demonstrable with explicitly labelled isolated records. This is a college prototype, not an operational emergency service. No application feature, authentication rule, migration, model or configuration was changed for this rehearsal. New work consists of tests and documentation/evidence.

## Checklist and evidence

PASS means the stated, bounded check executed successfully. NOT TESTED means it remains unexecuted or requires independent human evidence. FAIL is reserved for an executed check which did not meet its contract; no reproducible product failure remained in the final executed suite. Fixture results never establish real floods, facility authorization or emergency readiness.

| Feature/check | Result | Evidence and actual limits |
|---|---|---|
| Existing PostgreSQL/PostGIS readiness | **PASS** | Read-only inspection: `floodpulse_directory`, PostgreSQL 16.4/PostGIS 3.4.3, migration `0006_report_position_provenance`; existing public health/directory HTTP 200. No persistent migration/grant change |
| Existing records preserved | **PASS** | Before/after fingerprints match all **18** application/migration tables and database-role password fingerprints. Existing counts: **1 active admin, 1 shelter, 0 citizen reports, 1 accepted notification** |
| Isolated administrator login/logout | **PASS** | Actual Chrome, freshly provisioned UUID-demo account, protected workspaces HTTP 200, HttpOnly/SameSite session, logout then HTTP 401; [rehearsal test](../frontend/tests/college-demonstration.spec.js) |
| Live existing-account login/password rotation | **NOT TESTED** | User explicitly requested keeping live authentication blocked. The previously exposed password was not used or reset. Private rotation/session revocation is still a prerequisite before a persistent staff demonstration |
| CSRF/authorization/privacy | **PASS** | Missing/invalid CSRF denied with HTTP 403, anonymous admin/evidence APIs HTTP 401, restricted database roles, private sanitized-photo access and audit; browser and isolated PostgreSQL checks |
| Citizen flood submission and review | **PASS** | Real UI→API→restricted PostGIS, explicit manual location/250 m estimated uncertainty, owned PNG, private SUBMITTED→UNDER_REVIEW→APPROVED with reason/audit; [main journey](../frontend/tests/mvp-e2e.spec.js), [moderation screenshot](verification/2026_10_14/demo-flood-moderation.png) |
| Drainage reporting and rejection | **PASS** | Actual Chrome CDP location fixture with 1,250 m uncertainty, owned JPEG/encoded EXIF, private submission→review→REJECTED→withdrawal; [drainage journey](../frontend/tests/final-application-audit.spec.js). Coordinates/EXIF are constructed fixtures, not sensor observations |
| Photo metadata and file validation | **PASS** | Genuine JPEG/PNG decoding, format/dimensions/hash, consented EXIF and discrepancy flags; malformed/spoofed/oversized files refused. A vision classifier, flood severity or water-depth extraction is not implemented |
| Restricted evidence export | **PASS** | Authenticated approved-evidence download; rejected/withdrawn records excluded, no withdrawal secret exposed. `USER_REPORTED`, `training_eligible=false`, `NOT_ASSESSED`, no automatic negatives/training |
| Withdrawal/retention controls | **PASS** | Actual withdrawal removes private photo/location; expiry/access/redaction/purge tests pass. Physical purge still requires operator action; withdrawal key is lost on page reload |
| Shelter assignment/public discovery | **PASS** | Actual map entrance selection, Pending excluded, explicit fixture confirmations and capacity/Open included, Closed removed; revision/expiry/authorization rules tested. All fictional facilities remain isolated and visibly DEMO ONLY |
| Exact-entrance directions | **PASS** | Explicit adequate locality origin, freshly rechecked eligible entrance, exact URL parameters; [directory screenshot](verification/2026_10_14/demo-shelter-directions.png). No routing from approximate network location |
| External route provider | **PASS** | Fresh Chrome/Google HTTP 200, visible walking geometry **450 m/~6 min via Kundapura Main Rd**, provider attribution; [provider screenshot](verification/2026_10_14/google-directions-demo.png). Both endpoints are demonstration references, not authorized shelters |
| Real facility authority/access/capacity | **NOT TESTED** | Existing live shelter preserved; physical verification and freshness require its designated operator. Google place names are not shelter authorization |
| Flood-safe routing | **NOT TESTED** | Authoritative current road/hazard/closure/access evidence unavailable. Generic directions must not be described as flood-safe |
| Live Open-Meteo weather | **PASS** | Selected Kundapur HTTP 200; 26.6 °C valid at **14 Oct 22:30 IST**. Independently summed **24** complete hours: **1.4 mm**, **14 Oct 23:00→15 Oct 23:00 IST**. Weather is model output; issue time unavailable. [Receipt](verification/2026_10_14/weather-model-summary.json) |
| Supported experimental rainfall indicator | **PASS** | Live saved `rainfall_logistic_v1` inference at exact Kundapur point, HTTP 200; UI says **Experimental Heavy-Rainfall Indicator**. This run was below its heavy-rainfall threshold, which does not imply flood absence/safety. Fresh live Mangaluru inference was not repeated |
| Model/research integrity | **PASS** | Read-only validator reproduced 8,768 source rows and saved-model holdout inference, `refitted=false`; original model hash retained. Phase 12G flood-model training NO-GO remains |
| Desktop/mobile usability | **PASS** | Actual Chrome Home **1366×768**, no document overflow; new mobile checks at **390×844** for Home/report/shelters/alerts and admin, no horizontal overflow; full keyboard/navigation/provider-failure suite passed. [Desktop](verification/2026_10_14/demo-home-desktop.png), [mobile report](verification/2026_10_14/demo-report-mobile.png), [mobile admin](verification/2026_10_14/demo-admin-mobile.png) |
| Native GPS/camera and college Wi-Fi/device | **NOT TESTED** | CDP/stub GPS and real gallery upload are exercised; physical location accuracy/camera capture and the actual presentation network require operator checks. Browser-blocked tile/network fixtures test honest recovery, not a provider availability claim |
| Existing live Telegram API acceptance | **PASS** | Read-only history independently corroborates the operator report; exact scope/timestamps below. No new Telegram request/send |
| Recipient-side live receipt | **NOT TESTED** | Operator reports successful receipt on 14 October. Private chat/message was not independently viewed or published |
| `/stop` enforcement with zero sends | **PASS** | Authenticated fixture webhook command against isolated PostGIS: opt-out audited, options false, pending send/new preview HTTP 409, notification still draft, zero sender calls; [specific regression](../backend/integration_tests/test_telegram_subscriptions_postgres.py) |
| Real-chat `/stop`/current HTTPS webhook | **NOT TESTED** | No live consent changed, webhook registered/queried or recipient contacted. Existing active subscription preserved. A human may verify opt-out separately without authorizing an alert |
| Fresh live alert during rehearsal | **NOT TESTED** | Deliberately not sent. Any future send needs fresh explicit operator approval of exact content/destination; the rehearsal request gives no such approval |
| Public deployment/emergency-service readiness | **NOT TESTED** | No deployment performed or readiness certification claimed; official warning/verified river/road-hazard integrations remain unavailable |

## Telegram: operator report versus independently verified history

The operator confirms successful live delivery on **14 October 2026**. This is recipient-side **operator testimony**; it is not a screenshot or independently observed reading/delivery receipt.

The existing database independently contains **one live-mode accepted notification** with:

| Persisted evidence | UTC | IST |
|---|---|---|
| Preview created | 14 Oct 16:44:02.688429 | 14 Oct 22:14:02.688429 |
| Administrator confirmed / attempt recorded | 14 Oct 16:44:16.005313 | 14 Oct 22:14:16.005313 |
| Acceptance completed | 14 Oct 16:44:17.242747 | 14 Oct 22:14:17.242747 |

Status is `accepted`, result `telegram_accepted`, HTTP **200**, with a provider message ID recorded and confirmation by the composing administrator. Private correlation matched the currently authorized **private, explicitly test-only** destination and a prior active-consent audit receipt. This verifies persisted application evidence of Telegram API acceptance; it does not independently prove recipient receipt, reading or current webhook reachability. See the [identifier-free evidence summary](verification/2026_10_14/telegram-acceptance-summary.json). No recipient identity, chat ID, message text, provider message-ID value or credentials are committed.

The earlier 13 October “unconfigured/blocked” snapshot and early 14 October invalid-destination diagnosis are superseded for configuration/API-acceptance status. The current root `.env` parses with valid backend configuration and public username `FloodPulsebot`. That configuration was preserved, not edited. No automatic resend, new preview in the live database, webhook update or actual Telegram `/stop` was performed.

## Executed automated checks

| Check | Result / evidence |
|---|---|
| Backend/security | **1,455 passed**, one actual model-fitting reproduction deliberately deselected |
| Frontend | **275 passed**, 25 files |
| PostgreSQL/PostGIS | **68 passed** using only the audit-owned container and UUID databases; includes zero-send opt-out regression |
| Installed-Chrome Playwright | **84 passed**, final command exit **0**, 2.8 min; real isolated persistence/login plus clearly labelled protocol/layout fixtures |
| Production build | **PASS**, existing ~691 kB bundle advisory remains |
| Saved-model validator | **PASS**, 8,768 rows, saved holdout inference; no fitting or new research |
| Live read-only checks | **PASS**, current process/directory HTTP 200 and anonymous session HTTP 401; notification/consent history and database health inspected |

The first Chrome command logged **84 passed** and successfully removed its temporary database/roles, but its outer process reported SIGTERM during teardown. A repeat using a separate verification process session completed **84 passed / exit 0**. This was a harness-exit concern, not a reproduced product failure. Existing Starlette/httpx deprecation and Vite bundle-size advisory remain. No failing usability or functional assertion remained in the final run.

Private raw logs/receipts remain owner-only under `/tmp/floodpulse-college-rehearsal`; full image evidence exports and passwords are excluded from Git. Existing integration tests exercise mocked Telegram delivery results only; those are separate from the real historical acceptance record. The new browser rehearsal itself creates no alert preview/send. The main joined journey uses actual backend/PostGIS/image decoding, real selected-point weather/model requests and fixture incidents/facilities. The fresh Google check uses fixture endpoints and no device GPS.

For a repeat, provide an authorized maintenance connection **privately to a separate test PostgreSQL/PostGIS service**, never the web API, and run:

```bash
backend/.venv/bin/python -B -m pytest backend/tests -q \
  -k 'not test_real_training_reproduction_chronological_split_and_actual_metrics'
backend/.venv/bin/python -B -m pytest backend/integration_tests -q
backend/.venv/bin/python -B scripts/verify_mvp_e2e.py \
  --config=playwright.audit.config.js tests
(cd frontend && npm test && npm run build)
backend/.venv/bin/python -B scripts/validate_saved_rainfall.py
```

The runner strips Telegram credentials, creates fresh restricted roles/account and a UUID database, then drops its own objects. The automated rehearsal database is **not retained for interactive presentation**. Do not enter the invented incidents/entrances in the existing live database.

## Presentation sequence (approximately 8 minutes)

1. **0:00–0:45 — scope:** identify the college prototype, isolated DEMO ONLY environment and emergency-response USP. Explain that weather, citizen reports and verified shelter availability are distinct from flood predictions/official warnings.
2. **0:45–2:00 — citizen:** select an explicit manual point or permitted accurate GPS, choose flooding/drainage obstruction, use an owned non-personal image, review consent and submit privately. Explain SUBMITTED/USER_REPORTED. Keep this tab open to retain its withdrawal key.
3. **2:00–3:15 — administrator:** sign in with the separate private demo account, inspect the pinned location, uncertainty, actual photo metadata and privacy. Enter an auditable reason and approve/reject. Explain that EXIF is untrusted metadata and vision analysis is unavailable.
4. **3:15–4:00 — evidence:** inspect/download the restricted approved-evidence export. Highlight source/time/hash/reviewer provenance, `training_eligible=false`, and rejected/withdrawn exclusion. Do not display real private reports or credentials.
5. **4:00–5:30 — shelter:** create a conspicuously fictional isolated Pending facility, map-pin its entrance, demonstrate explicit fixture verification/capacity/Open controls and public eligibility. Recheck availability, choose an adequate origin and inspect the exact-entrance directions. Say “route safety not verified.” Close it and show removal.
6. **5:30–6:30 — alerts:** show the sanitized **14 October acceptance evidence** and state that recipient receipt is operator-confirmed. Explain exact review/approval/deduplication and the executed isolated zero-send `/stop` test. Do not press send or alter a live subscription during this rehearsal-based presentation.
7. **6:30–7:15 — supporting inputs:** select Kundapur and fetch fresh Open-Meteo weather. Show the next 24 complete hours and the experimental heavy-rainfall indicator with limitations; do not expect the 14 October values to remain current on 16 October.
8. **7:15–8:00 — privacy/mobile:** show a mobile viewport, withdraw the isolated citizen evidence, sign out, and explain human verification/retention and future separately reviewed dataset work.

## Human checks before 16 October

- Privately rotate the previously exposed persistent administrator password/revoke old sessions before using that account. Its live authentication remains intentionally blocked; isolated demo authentication is verified.
- Prepare a separate persistent **labelled demonstration** database/roles and chosen private demo account if presenting interactively. Rehearsal UUID databases were discarded. Verify DEMO ONLY banners before entering any invented record. Never replace live configuration or seed live facilities/reports for convenience.
- Recreate/renew isolated shelter verification on presentation day: availability expires after 24 hours, so screenshots/fixture verifications from 14 October are not valid availability on 16 October. Real operational authority, entrance condition, usability and capacity require independent human evidence; none is certified here.
- Verify native GPS, camera/gallery behavior, display/zoom, map/provider access and weather on the actual demonstration device/network. Manual location remains the tested fallback. Explain any unavailable tiles/data instead of substituting fabricated observations.
- Have the operator privately confirm the actual Telegram receipt if questioned. A real-chat `/stop` can be manually checked separately without sending an alert; it changes consent, so this rehearsal preserved it. Current webhook/HTTPS reachability and any later live send need separate human verification/approval.
- Assign the physical retention-purge operator and respect image rights/privacy. Native image-content analysis, public citizen-report publication, model-ready label assessment and environmental issue-time snapshots remain unimplemented dependencies.
- Keep original research/model artifacts, source attribution and scientific NO-GO intact. No statewide flood probability, automatically verified flood ground truth, flood-safe route, official warning integration or emergency-response guarantee may be claimed.

## Preservation and remaining limitations

All **18** existing application/migration table count/content fingerprints and database-role password fingerprints match before/after. **77** protected files retain identical SHA-256/size/mtime; **3,857** existing data files retain identical size/mtime (mutable launcher logs excluded). Root `.env`, PostgreSQL configuration/password references, original migrations/research/model files, unrelated `backend/.env.example`/`QandA.md` and prior `update.md` content were preserved. No persistent account reset, live report/shelter creation, deployment, model training or notification/consent mutation occurred.

Only the audit-owned temporary PostGIS container is removed after verification; the existing development PostgreSQL/application are left untouched. Current live authentication and device/facility/webhook checks remain explicit manual dependencies. The final publication hash is reported outside this file to avoid self-reference.
