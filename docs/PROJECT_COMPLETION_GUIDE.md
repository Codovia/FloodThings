# FloodPulse — Project Understanding and Two-Day Completion Guide

**Written:** 16 October 2026, 00:30 IST (presentation day). **Branch:** `feature/karnataka-data-foundation`, HEAD `55a501a` (local and `origin` match).
**Purpose:** one document explaining what FloodPulse is, what already works with real data, and exactly what to do over the next two days to finish and present it honestly.

Facts below come from the repository, the dated verification reports, and read-only live probes run when this guide was written (section 3). Earlier evidence is labelled with its date.

---

## 1. What FloodPulse is

FloodPulse is a **flood emergency-response web application for Karnataka** (focused on Udupi and Dakshina Kannada). Its unique selling point, set by the user's decision of 13 October 2026 ([MVP priorities](FLOODPULSE_MVP_PRIORITIES.md)), is:

1. **Citizen alerts.** An administrator writes a Telegram alert, previews it and approves it before it is sent to people who have opted in.
2. **Verified shelters with directions.** Administrators map-pin shelter entrances and record capacity and status. Citizens see only verified, unexpired Open shelters and get directions to them.
3. **Citizen GPS/photo reports.** Citizens submit flooding, waterlogging or blocked-drainage reports with location, photo and consent.
4. **Admin moderation.** Reports stay private until an administrator approves or rejects them, and every decision is audited.
5. **A provenance-aware future dataset.** Approved reports are exported with full source, time and hash provenance. They are never automatically treated as training truth.

**Flood prediction is deliberately a minor, experimental feature.** Research phases 12A–12G concluded **NO-GO** for training a validated flood-occurrence model: Karnataka has no scientifically eligible daily flood labels or verified negatives. The app therefore shows only an *Experimental Heavy-Rainfall Indicator* for two supported points. It predicts heavy rainfall, not flooding.

### Core rules (from [AGENTS.md](../AGENTS.md))

- No fabricated shelters, weather, forecasts, labels, image-analysis results or delivery receipts.
- Routes are **never** described as flood-safe. The app shows "Route safety not verified".
- Citizen reports remain `USER_REPORTED` until moderated.
- Model output never triggers a public warning.
- Every Telegram send needs a human preview and explicit approval.

---

## 2. Architecture and code map

| Layer | Technology | Where |
|---|---|---|
| Frontend | React + Vite, Leaflet maps | [frontend/src/](../frontend/src/) |
| Backend API | FastAPI (Python) | [backend/app/](../backend/app/) |
| Database | PostgreSQL 16.4 + PostGIS 3.4.3, Alembic migrations `0001`–`0006` | [backend/alembic/versions/](../backend/alembic/versions/), local port **55436** |
| Alerts | Telegram bot `FloodPulsebot`, webhook through Cloudflare Quick Tunnel | [backend/app/telegram_delivery.py](../backend/app/telegram_delivery.py), [scripts/full_launcher.py](../scripts/full_launcher.py) |
| Experimental model | `rainfall_logistic_v1` (saved logistic regression, no refitting) | [backend/models/](../backend/models/), [backend/app/rainfall_outlook.py](../backend/app/rainfall_outlook.py) |
| Launchers | `start.sh` (app only), `start-full.sh` (app + Telegram ingress) | repository root |

### Public pages (citizen)

| Route | Frontend file | Backend API |
|---|---|---|
| `/` Home | `HomeEmergencyDashboard.jsx`, `useHomeGeolocation.js` | `/api/weather`, `/api/location/*`, `/api/river-outlook` |
| `/weather` | `WeatherPanel.jsx`, `RainfallOutlook.jsx` | `/api/weather`, `/api/ai/rainfall-outlook` |
| `/flood-map` | `FloodIntelligenceMap.jsx` | `/api/flood-map/*`, `/api/historical-floods` |
| `/shelters` | `PublicShelters.jsx`, `useShelterDirectory.js` | `/api/shelters` |
| `/report` | `CitizenReport.jsx` | `/api/reports`, `/api/reports/{id}/withdraw` |
| `/alerts` | `AlertSubscription.jsx` | Telegram `/start floodpulse` and `/stop` via webhook |

### Admin pages (`/admin`, login + CSRF required)

| Workspace | Frontend file | Backend API |
|---|---|---|
| Shelters | `AdminShelters.jsx`, `AdminEntranceMap.jsx` | `/api/admin/shelters*` ([shelters.py](../backend/app/shelters.py)) |
| Report moderation | `AdminReports.jsx` | `/api/admin/reports*`, `/review`, `/audit`, `/photo`, `/evidence` |
| Alerts | `AdminNotifications.jsx` | `/api/admin/notifications`, `/{id}/send` |

### Security already built (keep it all)

- scrypt password hashing and opaque HttpOnly SameSite sessions.
- CSRF tokens, revision-conflict checks, and append-only audit tables (UPDATE/DELETE denied to the app role).
- Restricted database roles: the API never receives maintenance credentials.
- Photo uploads are decoded (JPEG/PNG), size/type-checked, stored under generated names and served only to authenticated admins.
- Report withdrawal and retention purge.

---

## 3. Status verified now (16 Oct, 00:30 IST, read-only probes)

| Check | Result |
|---|---|
| Backend `127.0.0.1:18050` `/api/health` | **200** `{"status":"ok"}`, mode `live` |
| Frontend `127.0.0.1:14180` | listening |
| PostgreSQL `127.0.0.1:55436` | listening |
| Live Open-Meteo weather, Kundapur (13.6251, 74.6916) | **200**: 26.6 °C, 89 % humidity, valid 16 Oct 00:30 IST, not stale |
| Experimental indicator, Kundapur | **200**: `below_heavy_threshold_predicted`, `probability: null`, experimental |
| Public shelter directory | **1 live shelter**: "venugopal temple", Manipal, Udupi, Open, capacity 100 / occupancy 50, `demonstration: false`. **Verification expires 16 Oct 17:21 IST** |
| Anonymous `/api/admin/session` | **401** (correctly protected) |
| Root `.env` | all four Telegram keys set (values not displayed). `cloudflared` installed at `/usr/local/bin/cloudflared` |
| Git | working tree clean except the user's unrelated `backend/.env.example` and `QandA.md`; HEAD equals remote |

### Feature readiness

| Feature | Priority | State | Evidence |
|---|---|---|---|
| Home: location + real weather + 24 h rain | P0 | **Working**. GPS, manual or approximate network location, each with its source labelled | Live probe above; [Home doc](HOME_EMERGENCY_DASHBOARD.md) |
| Admin login | P0 | **Working**, one real admin (created 13 Oct). ⚠ Its password was previously exposed, and rotation is still pending | [Rehearsal](DEMONSTRATION_REHEARSAL_2026_10_14.md) |
| Admin shelter management (pin entrance, 4 confirmations, 24 h expiry, audit) | P0 | **Working** | Browser E2E tests; 1 live shelter |
| Public shelters + directions | P0 | **Working**. Directions open externally in Google Maps after a fresh availability recheck, with the label "not verified flood-safe" | Google route proof, 14 Oct |
| Telegram alerts (preview → approve → send → audit, opt-in/out) | P0 | **Working**. One live send accepted by Telegram on 14 Oct 22:14 IST | Persisted `telegram_accepted` HTTP 200 record |
| Telegram webhook via `start-full.sh --telegram` | P0 | **Built and unit-tested; live end-to-end NOT TESTED** | [Launcher doc](FULL_SYSTEM_LAUNCHER.md) |
| Citizen GPS/photo report → moderation → export | P1 | **Working** (fixture-tested end to end; zero live reports so far) | `mvp-e2e.spec.js`, `final-application-audit.spec.js` |
| Photo metadata (format, size, SHA-256, consented EXIF, discrepancy flags) | P1 | **Working** | Backend tests |
| AI image classification | P1 optional | **Not implemented** (honestly absent) | — |
| Experimental heavy-rainfall indicator | P2 | **Working** for Kundapur and Mangaluru only | Live probe above |
| Official warning feed | P2 | **Not connected** (Home says so) | — |
| River (GloFAS) outlook | P2 | Adapter exists; **zero approved river associations**, so it shows "unavailable" | [Sprint 13 doc](SPRINT_13_HOME_LOCATION_RIVER_OUTLOOK.md) |
| In-app route geometry | P3 | **Not configured** (no `OPENROUTESERVICE_API_KEY`) | — |

**Test baseline (14–15 Oct):**

| Suite | Result |
|---|---|
| Backend | 1,455 passed |
| PostGIS | 68 passed |
| Frontend | 278 passed |
| Playwright | 84 passed |
| Production build | passes |

---

## 4. Real data available — what each source can and cannot support

### Live sources (used by the running app)

| Source | Used for | Licence / limit | What you must not claim |
|---|---|---|---|
| **Open-Meteo Forecast API** | Current weather, hourly rain, 7-day forecast | Free, non-commercial; attribution required | It is model output, not an observation; no issue time is provided |
| **Open-Meteo GloFAS flood API** | River discharge samples (research only) | Free, non-commercial | No river identity is provided, so it cannot set local danger levels |
| **OpenStreetMap tiles + locality nodes** | Maps; location directory v2 (31 districts, 5 selectable points) | ODbL; tile usage policy | Place names do not authorize shelters |
| **Google Maps (external link)** | Turn-by-turn directions | Opened in the user's browser | Not flood-safe; no closure data |
| **Telegram Bot API** | Alerts, opt-in/out | Bot token in private `.env` | A Telegram "accepted" response does not prove the recipient read the message |
| **BigDataCloud reverse geocode** (approximate) | Approximate city from IP when GPS fails | Free client-side tier | Approximate only; never shown as GPS |

### Local research datasets (`data/`, about 4 GB, not in Git)

| Dataset | What it is | Use in demo |
|---|---|---|
| Global Flood Database polygons | 56 Udupi flood cells (2005 event 2728 and 2009 event 3551) | Flood Map historical layer |
| Groundsource news records | 19,854 Karnataka candidate flood reports, unverified | Talking point: why labels are not training-ready |
| CHIRPS 2025 rainfall, ERA5 rows | 8,768 rows that trained `rainfall_logistic_v1` | Indicator provenance (precision 14.5 %, recall 91.7 %) |
| Sentinel-1 / JRC / hydrology pilots | Phase 3–12 feasibility studies | Explain the NO-GO decision; not served |
| Survey of India boundaries | District geometry | **Restricted. Keep out of Git; do not redistribute** |

### Real data you could still add (needs the user's action)

| Source | What it gives | What is needed | Verified |
|---|---|---|---|
| **NDMA SACHET** (`sachet.ndma.gov.in`) | Official CAP 1.2 alerts from IMD/CWC/INCOIS, published as an RSS feed | Confirm the exact feed URL and terms on the portal before building. One 2025 report says feeds are country/state-level, not district | Only partly. The exact feed endpoint was **not** confirmed in this research |
| **OpenRouteService** | In-app route geometry | Free API key. Standard plan: about 2,000 directions requests per day, 40 per minute | Plans page |
| **Open-Meteo historical weather API** | A weather snapshot at each report's observed time, for the dataset | No key needed | Not yet probed |

---

## 5. Day 1 — Thursday 16 October (presentation day)

Goal: present the working emergency workflow with real live data, safely. **No new features today.** Do the steps in this order.

### 5.1 Morning security fix (about 10 min) — required

The live admin password was exposed earlier and has not been rotated. Rotate it in your own terminal. This also deletes all existing sessions.

```bash
cd /home/pioneer/Projects/FloodPrediction/backend
export LOCATION_DIRECTORY_ADMIN_URL='<your private maintenance URL>'   # never commit or paste into chat
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME --reset-password
unset LOCATION_DIRECTORY_ADMIN_URL
cd .. && ./scripts/setup-admin.sh --verify-only    # private browser login check
```

### 5.2 Restart with Telegram ingress (about 10 min)

The current app was started by the old launcher. Stop it in its own terminal with **Ctrl+C**, wait for the prompt, then run:

```bash
./start-full.sh --check --telegram   # read-only; must pass
./start-full.sh --telegram           # app + proxy + Quick Tunnel + webhook registration
```

Then confirm the webhook end to end:

1. From your **own test** Telegram account, send `/start floodpulse` to `@FloodPulsebot`.
2. Check that the consent appears in `/admin` → Alerts.

If the tunnel fails, present with `./start.sh` and show the 14 Oct acceptance evidence instead. Do **not** improvise a public deployment.

### 5.3 Renew the real shelter (before 17:21 IST)

"venugopal temple" expires at **17:21 IST today**. After it expires it automatically disappears from public view, which is correct behaviour.

- Re-confirm it in `/admin` → Shelters **only if** you actually have current evidence of its authority, entrance, capacity and occupancy (for example, a call to the person responsible).
- If you do not, either let it show as unavailable or set it to Pending. Do not renew it just for the demo.
- If it is not a genuinely authorized shelter, mark it Closed or Pending. It is currently public with `demonstration: false`.

### 5.4 Device check at the venue (about 15 min)

On the presentation laptop and network:

- Check Home at 100 % zoom (1366×768).
- Allow GPS. If the position is coarse or denied, pick **Kundapur** manually.
- Check that weather loads.
- Check that `/report` opens the camera or gallery on a phone.
- Check that map tiles load.

If something fails, say so on screen. Manual location is the tested fallback.

### 5.5 Eight-minute demo script

| Time | Step | What to say |
|---|---|---|
| 0:00 | Scope | "Emergency-response prototype; prediction is experimental; nothing here is an official warning." |
| 0:45 | Home | Location source and uncertainty; live Open-Meteo weather; "Next 24 full forecast hours: X mm"; official feed *Not connected* |
| 1:45 | `/report` | Choose a manual point or GPS, flooding/drainage, an **owned** photo, consent → private receipt `SUBMITTED` |
| 2:45 | `/admin` → Reports | Pinned location, photo metadata (EXIF untrusted), reason → APPROVE; audit trail |
| 3:45 | Evidence export | Download JSON: provenance, SHA-256, reviewer, `training_eligible=false` |
| 4:30 | Shelters | Admin entrance pin, confirmations, Open → public list → "Recheck availability" → Google directions → "Route safety not verified" |
| 5:45 | Alerts | Preview the exact text and recipients → **explicit approval** → send to your own test chat only (if you decide to) → receipt/audit |
| 6:45 | `/weather` | Experimental Heavy-Rainfall Indicator: Kundapur/Mangaluru only; rainfall ≠ flood |
| 7:30 | Close | Withdraw the demo report, sign out, then explain the future work in Day 2 below |

**Rule for live demo records:** only submit reports you own and that are clearly labelled demo text, such as "DEMO – college presentation". Afterwards, withdraw or reject them so they do not enter the real evidence export.

### 5.6 Questions examiners may ask

| Question | Honest answer |
|---|---|
| "Does it predict floods?" | No. The NO-GO decision means no validated flood labels exist. The indicator predicts ≥64.5 mm/24 h rainfall at two points (precision 14.5 %, recall 91.7 %). |
| "Is the route safe?" | Not certified. No authoritative road-closure feed is available. |
| "Is a citizen photo truth?" | Not until reviewed, and even then it is reviewed citizen evidence, not ground truth. Nothing trains automatically. |
| "Where is the AI?" | An experimental rainfall classifier, plus a dataset pipeline designed for future supervised models. Image AI is future work and was deliberately not faked. |

---

## 6. Day 2 — Friday 17 October (finish and document)

Pick **at most two** of these slices. Each slice follows the AGENTS.md loop: acceptance test → implement → verify → append to `update.md` → commit → push → verify the remote hash. They are ordered by value per hour.

### Slice A — Report-time weather snapshot for the dataset (P1, about 3 h)

**Why:** the priorities require an "environmental feature snapshot with issue time and observed time". The export currently says `not_captured`.

**What:** when an admin approves a report, fetch Open-Meteo hourly precipitation and temperature for the report point and its observed hour. Store the values with `retrieved_at`, the source URL and the model name, in a new additive migration `0007`. Add them to the evidence export.

**Acceptance test:**
- Approving an isolated test report stores the snapshot.
- Provider failure stores `unavailable` with a reason, never invented values.
- `training_eligible` stays false.

### Slice B — Official warnings link-out (P2, about 2 h)

**Why:** Home shows "Official warning feed: Not connected".

**Minimal honest version:** a clearly labelled link to `sachet.ndma.gov.in` and the IMD/KSNDMC pages. This requires no parsing.

**Full version (only after verifying the feed URL and terms):** a read-only CAP parser filtered to Karnataka, showing the original issuer, sent/expires times and a link to the source. Never re-word the alert, and never trigger Telegram from it.

**Acceptance test:**
- Feed unavailable → "Not connected".
- An expired alert is hidden.
- No automatic sends.

### Slice C — In-app route line with OpenRouteService (P3, about 3 h)

**Prerequisite:** get a free key and put `OPENROUTESERVICE_API_KEY` in the private `.env`.

**What:** a backend proxy endpoint that draws the route on the Shelters map, keeps the "not verified flood-safe" banner, and falls back to the existing Google link.

**Acceptance test:**
- Missing key → the feature is hidden.
- Quota error → an honest message.
- The origin/entrance adequacy rules are unchanged.

### Slice D — Project report and viva pack (about 2 h, recommended regardless)

Turn sections 1–4 into the college report (problem, architecture, data sources, security, results, limitations, future work).

Include:
- Screenshots from [docs/verification/ui_ux_2026_10_15/](verification/ui_ux_2026_10_15/) and [2026_10_14/](verification/2026_10_14/).
- The test counts from section 3.

Do not include credentials, chat IDs or private report photos.

### Explicitly out of scope for the next two days

- Training a flood-occurrence model.
- Statewide coverage.
- CWC gauge integration (still awaiting CWC's reply).
- A satellite basemap (needs MapTiler rights).
- Image AI classification.
- Public deployment.

Mention all of these as future work.

---

## 7. Command reference

```bash
# Start / stop
./start-full.sh --check --telegram && ./start-full.sh --telegram    # Ctrl+C to stop
./start.sh                                                         # app only

# Read-only health
curl -s http://127.0.0.1:18050/api/health
curl -s 'http://127.0.0.1:18050/api/weather?latitude=13.6250993&longitude=74.6915722'
cd backend && .venv/bin/python -m app.mvp_database                 # read-only DB/grant check

# Tests (persistence tests ONLY against an isolated test database)
cd frontend && npm test && npm run build
backend/.venv/bin/python -B -m pytest backend/tests -q \
  -k 'not test_real_training_reproduction_chronological_split_and_actual_metrics'
backend/.venv/bin/python -B scripts/validate_saved_rainfall.py
backend/.venv/bin/python -B scripts/verify_mvp_e2e.py               # disposable UUID database; no Telegram
```

URLs:
- App: http://127.0.0.1:14180
- Admin: http://127.0.0.1:14180/admin
- API: http://127.0.0.1:18050

---

## 8. Risks and how to handle them

| Risk | Mitigation |
|---|---|
| Venue Wi-Fi blocks the tunnel or tiles | Use `./start.sh` and manual location. Show the committed screenshots as backup |
| Shelter expires mid-demo (17:21 IST) | Renew it with genuine evidence, or show the expiry as a feature |
| Open-Meteo rate limit or outage | The app shows an honest 503 "unavailable"; explain it, do not fake values |
| An accidental Telegram send | The send button requires preview and explicit approval. Only your own test chat is in `TELEGRAM_DESTINATIONS` |
| The exposed admin password | Rotate it first (5.1) |

## 9. Further reading

- [MVP priorities](FLOODPULSE_MVP_PRIORITIES.md)
- [Readiness, 13 Oct](MVP_END_TO_END_READINESS.md)
- [Rehearsal, 14 Oct](DEMONSTRATION_REHEARSAL_2026_10_14.md)
- [Full launcher](FULL_SYSTEM_LAUNCHER.md)
- [Telegram opt-in](TELEGRAM_OPT_IN_MVP.md)
- [Citizen reporting](CITIZEN_REPORTING_MVP.md)
- [Current capabilities](CURRENT_CAPABILITIES.md)
- [README](../README.md)
- [update.md](../update.md) — full history

## Summary

FloodPulse's emergency workflow is built and tested: location and weather, citizen reports, moderation, export, shelters, directions and approved Telegram alerts. It runs live today on real Open-Meteo, OSM and Telegram data.

What remains is mostly **operational**, not code:
1. Rotate the admin password.
2. Run the Telegram launcher live once.
3. Renew the shelter with genuine evidence before 17:21 IST.
4. Check the venue device.

Day 2 should add, at most, the report-time weather snapshot and an official-warnings link-out, plus the written project report. The rainfall indicator must stay labelled experimental, and no route may be called flood-safe.
