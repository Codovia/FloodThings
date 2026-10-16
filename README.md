# FloodPulse

**Flood and drainage risk prediction and early-alert system for Karnataka, with emergency shelter management and navigation.**

> College major project. FloodPulse is a prototype, not an official warning service. Risk levels are experimental. Always follow official advice from IMD, KSNDMC and the district administration.

## What it does

| Feature | Citizen sees | Administrator does |
|---|---|---|
| **Risk prediction** *(in progress)* | Flood risk and drainage (waterlogging) risk, Low → Severe, for any place in Karnataka, with the reason behind each level | Watches the statewide risk map |
| **Early alerts** | Telegram alerts after opting in (`/start floodpulse`, `/stop`) | Reviews the suggested alert, edits it, previews and approves it |
| **Citizen reports** | Reports flooding or a blocked drain with GPS + photo | Approves or rejects; approved reports feed drainage risk and routing |
| **Shelters** | Open, verified shelters with capacity | Pins the entrance on a map and verifies capacity and status (expires after 24 h) |
| **Navigation** *(in-app route in progress; Google Maps link works)* | Directions to a shelter that avoid approved flooded spots | — |

Every number comes from a real, timestamped source; if a source fails, the app says *unavailable*. How it all fits together is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Tech stack

React 19 + Vite + Leaflet · FastAPI (Python 3.12) · PostgreSQL 16 + PostGIS 3.4 · Alembic · scikit-learn · Telegram Bot API.

## Run it (Linux)

Prerequisites: Python 3.12+, Node 22.12+ (or 20.19+), Docker (existing `floodpulse-sprint6-db` PostGIS container), and the private launcher profile `data/tmp/launcher/config.json`. That profile holds the restricted database connections; see [Manual setup](docs/MANUAL_SETUP_CHECKLIST.md).

```bash
./start.sh --check          # read-only readiness check
./start.sh                  # starts backend + frontend (Ctrl+C to stop)
```

| | URL |
|---|---|
| App | http://127.0.0.1:14180 |
| Admin | http://127.0.0.1:14180/admin |
| API | http://127.0.0.1:18050 (interactive docs at `/docs`) |

**With Telegram:** put `TELEGRAM_BOT_USERNAME`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DESTINATIONS` and `TELEGRAM_WEBHOOK_SECRET` in a private `0600` root `.env`, then run:

```bash
./start-full.sh --check --telegram
./start-full.sh --telegram    # app + webhook proxy + Cloudflare Quick Tunnel
```

See [docs/FULL_SYSTEM_LAUNCHER.md](docs/FULL_SYSTEM_LAUNCHER.md) and [docs/TELEGRAM_OPT_IN_MVP.md](docs/TELEGRAM_OPT_IN_MVP.md).

**Administrator account.** There is no default password and no public sign-up. Create the account privately:

```bash
./scripts/setup-admin.sh                  # create an account (prompts privately)
./scripts/setup-admin.sh --verify-only    # test login
# rotate a password (maintenance connection exported privately in your own shell):
cd backend && .venv/bin/python -B -m app.provision_shelter_admin --username NAME --reset-password
```

**Routing (optional).** Add `OPENROUTESERVICE_API_KEY=` to the private `.env` (free key from openrouteservice.org). Without it, directions open in Google Maps.

## Test

```bash
cd frontend && npm test && npm run build                       # unit tests + production build
backend/.venv/bin/python -B -m pytest backend/tests tests -q \
  -k 'not test_real_training_reproduction_chronological_split_and_actual_metrics'
cd frontend && npx playwright test                             # browser tests (isolated ports, no Telegram)
backend/.venv/bin/python -B scripts/verify_mvp_e2e.py          # full journey on a disposable database
```

Tests never use the live database. PostGIS tests create disposable UUID databases.

## Project layout

```
backend/app/       API modules: risk, weather, reports, shelters, notifications, telegram
backend/alembic/   database migrations
backend/models/    saved rainfall model (rainfall_logistic_v1)
frontend/src/      React pages: Home, Flood Map, Shelters, Report, Alerts, Admin
scripts/           launchers, Telegram webhook, admin setup, model/data provenance
data/processed/    published derived data       data/reference/  location directory
docs/              architecture, operations guides, decisions/, research/
```

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design, risk method, data flow, security |
| [decisions/2026-10-16_4_DAY_PLAN.md](docs/decisions/2026-10-16_4_DAY_PLAN.md) | Current delivery plan and demo script |
| [decisions/2026-10-13_MVP_PRIORITIES.md](docs/decisions/2026-10-13_MVP_PRIORITIES.md) | Shelter, alert, report and dataset rules |
| [PREDICTION_FEATURE_METHOD.md](docs/PREDICTION_FEATURE_METHOD.md) | How the AI rainfall model was trained |
| [CITIZEN_REPORTING_MVP.md](docs/CITIZEN_REPORTING_MVP.md) | Report privacy, moderation, export |
| [OPEN_METEO_WEATHER.md](docs/OPEN_METEO_WEATHER.md) · [MAP_TILE_POLICY.md](docs/MAP_TILE_POLICY.md) | Weather semantics; map tile usage rules |
| [research/](docs/research/) | Why no flood-occurrence model is trained (Phase 12G NO-GO), data-source register |
| [update.md](update.md) | Full development log |

## Data and licences

Open-Meteo forecast, flood (GloFAS) and elevation APIs (CC BY 4.0, non-commercial) · geoBoundaries (CC BY 2.5 IN) · Global Flood Database (CC BY-NC 4.0) · OpenStreetMap (ODbL) · OpenRouteService · IMD rainfall categories.

Survey of India boundary data and raw research data stay local and are never committed.

## History

The earlier research pipeline is preserved in Git tag `archive/research-2026-10-16`: Sentinel-1, hydrology and gauge studies, label audits and 47 scripts. Restore any file with:

```bash
git checkout archive/research-2026-10-16 -- <path>
```
