# FloodPulse — Architecture (v2)

**FloodPulse** is a flood and drainage **risk prediction and early-alert system** for **all of Karnataka**, with emergency shelter management and navigation.

This document describes how the system is built and why. Branch `floodpulse-v2` is the cleaned codebase. The previous research pipeline is preserved in Git tag `archive/research-2026-10-16`.

## 1. Design principles

1. **Five features, one story.** Risk → Alert → Report → Shelter → Navigation. Anything that does not serve one of them is removed.
2. **Keep what is proven.** Login, CSRF, audit trails, shelter verification, report moderation and Telegram consent were already tested (600+ Python tests, 279 UI tests, live Telegram acceptance). They are kept and built on, not rewritten.
3. **Real data only.** Every number on screen comes from a named live source with a timestamp. When a source fails, the UI says *unavailable*. It never falls back to a guess.
4. **Honest AI.** No verified Karnataka flood-outcome labels exist, so no "flood yes/no" classifier is trained (the Phase 12G NO-GO). Risk is a transparent, rule-based index built on official thresholds. It is always labelled *experimental*.
5. **A human approves every alert.** The risk engine can *suggest* an alert; only an administrator sends one.

## 2. System overview

```
                         ┌──────────────── Browser (React + Leaflet) ────────────────┐
 Citizen ───────────────▶│ Home · Flood Map · Shelters · Report · Alerts             │
 Administrator ─────────▶│ Admin: Reports · Shelters · Alerts (+ risk suggestions)   │
                         └───────────────────────────┬───────────────────────────────┘
                                                     │ /api (same origin, cookies + CSRF)
                         ┌───────────────────────────▼───────────────────────────────┐
                         │ FastAPI backend                                           │
                         │  risk      ── statewide grid + point assessment           │
                         │  weather   ── Open-Meteo point weather                    │
                         │  reports   ── citizen GPS/photo, moderation, export       │
                         │  shelters  ── admin verification, public directory, auth  │
                         │  notifications/telegram ── preview → approve → send       │
                         │  routing   ── OpenRouteService with avoid-polygons        │
                         └──────┬──────────────────────────────┬─────────────────────┘
                                │                              │
                    PostgreSQL 16 + PostGIS            External real data (HTTPS)
                    (restricted roles, audit)          Open-Meteo forecast · GloFAS flood
                                                       Copernicus elevation · ORS · Telegram
```

## 3. Features and where they live

| Feature | Backend | Frontend | Data |
|---|---|---|---|
| **Risk prediction** (statewide) | `risk.py`; `river_forecast.py` + `river_flood_model.py` (GloFAS river forecast and the FloodPulse AI river flood model, six checked rivers); `rainfall_outlook.py` (earlier heavy-rain model, no screen) | `Home`, `Flood Map` risk layer and Rivers tab | Open-Meteo, GloFAS, elevation, GFD history, approved reports |
| **Official warnings** (displayed as issued) | `official.py` (`/api/official/warnings`, `/api/official/districts`, `/api/admin/official/suggestions`) | `OfficialWarnings` on Home, Flood Map IMD layer, Admin official drafts | IMD district-wise warnings (public GeoServer layer; codes from the IMD API reference), NDMA SACHET CAP 1.2 Karnataka RSS |
| **Early alerts** | `notifications.py`, `telegram_delivery.py`, `telegram_subscriptions.py` | `AdminNotifications`, `AlertSubscription` | Tables `admin_notifications`, `telegram_subscriptions` |
| **Citizen reports** | `reports.py`, `report_images.py` | `CitizenReport`, `AdminReports` | Tables `citizen_reports`, images, audit |
| **Shelter management** | `shelters.py`, `shelter_security.py` | `AdminShelters`, `AdminEntranceMap`, `PublicShelters` | Table `emergency_shelters`, audit |
| **Navigation** | `routing.py` | `PublicShelters` + `ShelterMap` route line | OpenRouteService (key optional) |
| Location + weather | `locations.py`, `location_weather.py`, `weather.py` | `useHomeGeolocation`, `LocationDirectorySelector` | Location directory v2 (31 districts) |
| Flood history map | `flood_map.py`, `historical.py`, `drainage.py` | `FloodIntelligenceMap` | GFD 2005/2009 Udupi extents |
| Platform | `main.py`, `location_database.py`, `mvp_database.py`, Alembic `0001`–`0006` | `App`, `AppNavigation` | — |

## 4. Risk engine (statewide)

### 4.1 Two levels of detail

| Level | Coverage | Inputs | Refresh |
|---|---|---|---|
| **Statewide grid** | 256 cells of 0.25° (~28 km), clipped to the Karnataka boundary (geoBoundaries ADM1, CC BY 2.5 IN, already in the repo) | Rainfall factors only | Server cache, every 3 hours. 256 points ≈ 2,048 Open-Meteo calls/day, within the free 10,000/day |
| **Point assessment** | Any point inside Karnataka (GPS, map click or locality) | All factors | On request; cached 30 min per ~1 km point |

### 4.2 Factors and scoring

**Flood risk** (river and rain):

| Factor | Source | Points |
|---|---|---|
| Forecast rain, next 24 h | Open-Meteo hourly | IMD categories: <15.6 mm = 0 · 15.6–64.4 = 1 · 64.5–115.5 = 2 · 115.6–204.4 = 3 · ≥204.5 = 4 |
| Rain, past 5 days | Open-Meteo `past_days=5` | ≥50 mm = 1 · ≥150 mm = 2 *(project-chosen)* |
| River flow, next 3 days | GloFAS v4 nearest 5 km cell vs that cell's 2015–2024 annual maxima (Gumbel fit) | ≥2-year level = 2 · ≥5-year level = 3 |
| Low-lying ground | Copernicus GLO-90 elevation | <10 m = 1 |
| Mapped historical flood within 1 km | GFD 2005/2009 (**Udupi only**; elsewhere shown as "no data", not as zero risk) | 1 |

**Drainage / waterlogging risk:**

| Factor | Source | Points |
|---|---|---|
| Forecast rain, next 24 h | Open-Meteo | IMD category, capped at 2 |
| Peak hourly intensity, next 24 h | Open-Meteo | ≥10 mm/h = 1 · ≥20 mm/h = 2 *(project-chosen)* |
| Approved flooding/waterlogging/blocked-drain reports within 1 km, last 72 h | FloodPulse database | 1 report = 1 · ≥3 = 2 |
| Low-lying ground | Copernicus elevation | <10 m = 1 |

**Level:** 0–1 Low · 2–3 Moderate · 4–5 High · ≥6 Severe. The statewide grid shows a **rain-only** level, labelled as such.

**Missing inputs.** A missing input is shown as *unavailable*, and the result is marked `partial`. The engine never assumes a missing value is zero risk. If rainfall itself is unavailable, the level is *unavailable*.

### 4.3 Why these choices

- **IMD categories.** They are India's official heavy-rainfall definitions.
- **Return levels.** GloFAS's own flood thresholds are return periods. A 10-year record keeps history downloads at ~260 API calls per river cell. Each cell is cached on disk once.
- **Rule-based, not trained.** A classifier needs verified flood and no-flood days; Karnataka has none that pass review. A transparent index can be explained factor by factor, which examiners and users can check.

### 4.4 API

| Endpoint | Access | Returns |
|---|---|---|
| `GET /api/risk?latitude=&longitude=` | public | Point flood + drainage assessment with every factor, source and status; 422 outside Karnataka; 503 when rainfall is unavailable |
| `GET /api/risk/grid` | public | 256-cell rain-only statewide grid, cached 3 h |
| `GET /api/admin/risk/suggestions` | admin session | Draft alert texts for High/Severe cells; sends nothing |
| `POST /api/route` | public | OpenRouteService route avoiding approved reports (count only exposed); `not_configured` without a key |

Measured live on 16 Oct 2026: full grid in ~10 s (13 requests of 20 points, 4 in parallel), then served from cache; a point assessment takes 1–2 s (river history cached on disk per GloFAS cell).

### 4.5 Validation (planned — not yet run)

A retrospective case-study check will use archived real data on known flood periods:

- Udupi, September 2005 and September–October 2009 (GFD events)
- Karnataka, August 2019

It will be reported as "the index reached High/Severe on N of M known flood days". It is not called accuracy, because there are no verified negative days.

### 4.6 The existing AI model

`rainfall_logistic_v1` (logistic regression; predicts ≥64.5 mm/24 h; precision 14.5 %, recall 91.7 %) is trained for Kundapur and Mangaluru only. It is shown as a second opinion at those points and is not part of the score.

## 5. Early-alert flow

```
statewide grid (cached 3 h) ── cell reaches High or Severe
      └─▶ Suggested alert in Admin → Alerts (draft text, level, location)   ← computed on request, not stored
            └─▶ Admin edits text → Preview (exact message + recipients) → Approve → Telegram send
                  └─▶ Delivery result + audit record
```

"Use as draft" only fills the composer. Citizens opt in with `/start floodpulse` and opt out with `/stop`. Suggestions never send on their own; the existing Telegram deduplication, consent recheck and audit apply to every real send.

## 6. Navigation

1. The citizen picks a verified Open shelter.
2. The backend rechecks availability.
3. It requests an OpenRouteService route (foot or car).
4. It passes `avoid_polygons` built as 150 m buffers around approved flooding/blocked-road reports from the last 72 h.
5. The route line is drawn with the label **"Avoids N reported flooded spots — not certified flood-safe."**

Without an API key, the existing Google Maps external link remains.

## 7. Security (unchanged, kept)

- **Authentication:** scrypt password hashes; opaque HttpOnly SameSite session cookies; CSRF token on every write; login rate limiting.
- **Database:** restricted PostgreSQL roles. The API cannot UPDATE or DELETE audit rows; maintenance credentials never reach the API.
- **Photos:** decoded and validated (JPEG/PNG, size, dimensions); stored with generated names and SHA-256; viewable only by admins; withdrawal and retention purge supported.
- **Secrets:** a `0600` root `.env`, never committed. Tests use disposable UUID databases and never the live database.

## 8. Repository layout (v2)

```
backend/app/        FastAPI modules (table in §3)
backend/alembic/    migrations 0001–0006 (+0007 for alert suggestions, Day 3)
backend/models/     rainfall_logistic_v1 (saved, hash-checked)
backend/tests/      unit tests        backend/integration_tests/  PostGIS tests
frontend/src/       React pages and hooks        frontend/tests/  Playwright
scripts/            launchers, Telegram webhook, admin setup, model + data provenance
data/processed/     published derived data (Udupi history, drainage study)
data/reference/     location directory
docs/               ARCHITECTURE (this), operations guides, decisions/, research/
floodpulse.sh, scripts/app_launcher.sh
```

## 9. What was removed and why

| Removed | Reason |
|---|---|
| 47 research scripts (Sentinel-1, JRC, hydrology closure, Groundsource, CWC gauges, CHIRPS assembly, label audits, SOI/LGD) | One-off research behind the NO-GO; not used by the app |
| 35 tests for those scripts | Tested removed code only |
| Phase 12a–f reports, 13 research method docs | Historical. The NO-GO evidence is kept in `docs/research/` |
| 15 dated sprint/rehearsal/audit/readiness reports, `CODEX_START_HERE.md`, `AGENTS_MVP_ADDENDUM.md` | Superseded; their history remains in `update.md` and the archive tag |
| Weather page in the main menu | Merged into Home |

All of it is recoverable with:

```bash
git checkout archive/research-2026-10-16 -- <path>
```

## 10. Real data sources

| Source | Use | Licence / limit |
|---|---|---|
| Open-Meteo Forecast | Rain (past 5 d + next 3–7 d), weather | CC BY 4.0; free 10,000 calls/day |
| Open-Meteo Flood (GloFAS v4) | River discharge history + forecast | CC BY 4.0; ~5 km grid |
| Open-Meteo Elevation (Copernicus GLO-90) | Terrain | Free; attribution required |
| geoBoundaries IND ADM1 | Karnataka boundary for the grid | CC BY 2.5 IN |
| Global Flood Database | 2005/2009 Udupi extents | CC BY-NC 4.0 |
| OpenStreetMap | Tiles, localities | ODbL |
| OpenRouteService | Routing with avoid-polygons | Free key, ~2,000 routes/day |
| Telegram Bot API | Alerts | Private bot configuration |
| IMD / MoES | Rainfall category thresholds | Official classification |
