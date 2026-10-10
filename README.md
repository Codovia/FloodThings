# FloodPulse — weather, historical flood evidence and GIS research

See [current capabilities and operational limits](docs/CURRENT_CAPABILITIES.md) for
the current application summary and shelter-freshness policy. The pending
handwritten-wireframe redesign has not been implemented.

For the verified production-build citizen/admin demonstration, private setup,
backup/isolated restore and service-failure recovery, see the
[release demonstration guide](docs/RELEASE_DEMONSTRATION.md). Telegram live
delivery remains blocked pending a legitimate private test configuration and
explicit operator approval; validated flood prediction remains unavailable.

A React + Vite dashboard → FastAPI → Open-Meteo seven-day weather dashboard with verified district/locality name search, Leaflet point selection and user-requested GPS (Bengaluru by default), plus a Leaflet map of two verified historical satellite flood events in Udupi. Historical data come from bounded real Earth Engine queries. `QandA.md` is preserved as historical product context; its old implementation and accuracy claims do not describe this rebuild.

The optional **Drainage Research Layers** panel reads `data/processed/udupi_drainage_gis_v1/`: a 3 km × 3 km study window around a verified Udupi OSM city point, not an official municipal boundary. Select surface elevation, derived slope or 2021 land cover. The bounded OSM query returned no drain/ditch ways; unmapped infrastructure remains unknown. Terrain is a 30 m surface model including buildings and vegetation, suitable for exploratory surface research with those limitations. These layers do not provide drainage-risk scores or live waterlogging information.

## Karnataka place selection

Expand **Change location**, choose **Search districts and localities**, search a name or select a district, then choose a mapped locality. The map immediately centers on its retained WGS84 settlement point and the existing point-weather endpoint retrieves seven provider-supplied forecast days. Map clicks, GPS and six-hour browser-session refresh remain available; public coordinate-entry fields have been removed. Selecting a district filters places and navigates where reviewed public bounds exist; it never requests district-wide weather or changes the previously selected weather point.

The active public directory, `data/reference/karnataka_location_directory_v2/`, contains **31 NIC-listed district names**, with independent current-LGD reconciliation still unresolved. Stable application IDs use the NIC website namespace, not guessed LGD codes. **Five selectable mapped settlements** are verified: Udupi, Karkala, Kundapur and Saligrama in Udupi district, plus Mangaluru in Dakshina Kannada. Both districts have reviewed public geoBoundaries navigation bounds. **Kaup** has an official municipal identity but remains disabled because its settlement coordinate has not been reviewed. The other 29 districts show incomplete-coverage messages and preserve map/GPS selection. The original v1 directory remains unchanged and readable.

Kundapur retains `udupi-admin:municipality:kundapur`; lookup by `osm:node:245623778` resolves the same record. Official district records independently link Kundapur/Kundapura town names. Its genuine OSM `place=town` point is used; railway and taluk-centre results remain excluded. Saligrama's original OSM `place=village` classification is preserved separately from its official town-panchayat identity. Mangaluru also supports the source alias Mangalore. All points represent mapped settlements, not surveyed municipal centres, gauges or shelters.

Read-only APIs: `GET /api/locations/districts?q=...`, `GET /api/locations/localities?district_id=nic:udupi.nic.in&q=...`, `GET /api/locations/search?q=...`, and `GET /api/locations/localities/{locality_id}`. Search ordering is deterministic; `limit` is bounded to 50 and `offset` supports pagination. Unknown identifiers return 404, invalid parameters 422, and missing/corrupt directory data 503. Local search makes no external geocoder requests; the explicitly selected backend may use the public file snapshot or PostgreSQL. Backend checks provenance, coordinate availability and directory checksums before serving records.

Coordinates: © OpenStreetMap contributors, **ODbL 1.0**; the extracted place-point database is offered under that licence with attribution/share-alike conditions. Udupi navigation bounds: existing geoBoundaries CGAZ **CC BY 4.0**. Dakshina Kannada navigation bounds: geoBoundaries gbOpen IND ADM2, Pathways Data Pvt. Ltd./lgdirectory.gov.in, **ODbL 1.0**, represented year 2021; these are navigation context, not current official district-boundary certification. Government URLs cross-check small factual names/associations; no government HTML/text or SOI geometry is republished. The [source register](docs/DATA_SOURCE_REGISTER.md) and directory manifest retain source versions, original checksums and limitations. The weather API still identifies any requested coordinates as a point; directory provenance is displayed separately, without claiming that Open-Meteo verifies administrative identity or supplies district-wide conditions.

Reproduce the public directory offline with `backend/.venv/bin/python -B scripts/expand_location_directory.py validate` using the retained source files. `build` refuses an existing version. The original v1 validation command remains `backend/.venv/bin/python -B scripts/build_location_directory.py validate`. Runtime search reads either the explicit file backend or the active imported PostgreSQL version and makes no geocoder requests.

A fresh clone can serve the permitted directory snapshot without raw verification documents; offline source reproduction requires the retained originals locally. Both validators check source hashes, original node coordinates, actual public polygon containment and deterministic outputs without writes or network. Original SOI data and derived research tables remain local.


## Application navigation

The shared header provides five pages. Location selection and the weather freshness session persist during navigation; browser back/forward and direct URLs work.

| Page | URL | Content |
| --- | --- | --- |
| Home | `/` | Karnataka point map, selected-location weather, forecasts, experimental AI and shelter access |
| Weather & AI | `/weather` | District/locality search, GPS/map selection, seven-day weather, provider rainfall chart and saved Logistic Regression outlook |
| Flood Map | `/flood-map` | 31-district evidence filter, original Udupi historical polygons and details, separate unavailable hazard layer, optional drainage context and verified shelter entrances |
| Shelters | `/shelters` | Verified Open destinations with spare capacity, reported facilities, timestamps and external entrance directions; explicit empty/error states |
| Admin | `/admin` | Existing protected login, shelter verification/audit and explicitly approved Telegram notifications |

On mobile, use **Menu** to reveal navigation; Escape closes it. All pages use the same blue/teal design and retain keyboard focus indicators, loading/error announcements and source attribution. The rainfall chart uses real daily forecast totals only: missing values remain gaps. Weather is point-specific; historical floodwater is not live flooding, and experimental heavy-rainfall inference is not a calibrated flood probability. The public operational shelter directory is not seeded with demonstration facilities.

Home pairs a prominent Karnataka point map and the current shelter summary with compact weather/AI cards. **Change location** expands the shared district/locality, manual-coordinate and GPS controls. Weather & AI keeps the full seven-day cards, rainfall chart and source timestamps; its point map is optional. Shelters starts with the verified directory and a compact location bar, rather than a repeated weather form. Navigation retains the same location and six-hour weather session without a new weather request.

### Background maps

The default is the standard OpenStreetMap tile service, with visible © OpenStreetMap contributors attribution. Tile images send only the real application origin as their referrer; the global privacy header is preserved. Browser caching is honored, with no bulk download, proxy, identity spoofing or automatic provider switching. On a tile error the background layer stops and a notice appears, while geographic overlays and point selection remain usable. This does not establish flood absence.

To intentionally use the application without background tile requests, set `VITE_MAP_BASEMAP=none` in the ignored `frontend/.env.local`, then restart Vite (or rebuild the production frontend). `osm` is the default; unknown settings also request no tiles. This does not download or cache an offline basemap. Do not put private keys in Vite variables. See [the map policy diagnosis and browser verification](docs/MAP_TILE_POLICY.md) for limitations and independently observed results.

Use the existing `./start.sh` workflow below. Vite serves these direct URLs; a production static host must serve the application entry for frontend routes while preserving the separate FastAPI `/api` routing. No backend, database, credential or model migration is required for this UI change.


## Experimental AI Rainfall Outlook

Select **Kundapur** or **Mangaluru** through the existing PostgreSQL/file-backed place selector, wait for real weather, then choose **Run experimental rainfall model**. The saved `rainfall_logistic_v1` StandardScaler + Logistic Regression model receives verified past-hourly Open-Meteo inputs and returns a binary experimental rainfall outlook. Switching locations clears old results; once opened, the panel refreshes after a new successful weather receipt. Its separate bounded hourly request supplies features absent from the seven-day weather response; it does not repeat that weather request. Model/provider failures show unavailable, with manual retry and no replacement prediction. Other points retain normal weather but are outside this model's supported scope.

`GET /api/ai/rainfall-outlook?latitude=13.6250993&longitude=74.6915722` returns the actual model result, version/checksum, requested point and provider grid, input features/units, successful UTC retrieval, feature-valid time and exact 24-hour horizon. Invalid coordinates return 422; missing/incompatible model or hourly inputs, unsupported points and provider failures return 503. The horizon begins at the next complete UTC hour, within one hour after retrieval. The backend consumes only past-hourly values ending before that start, never future observations. No calibrated probability is exposed.

Target: **at least 64.5 mm precipitation over 24 hours**, using the amount boundary in [IMD's heavy-rainfall definition](https://www.imdpune.gov.in/hazardatlas/extr_rainfallnew_p2001_2010.html). It includes heavier amounts. This is a **model-grid rainfall proxy** in a rolling UTC window, not an IMD station measurement/reporting day, flood occurrence, district-wide forecast or official warning. Below threshold does not mean dry or safe. Flood prediction remains unavailable and no alerts are triggered.

Training uses two bounded real [Open-Meteo ERA5 reanalysis](https://open-meteo.com/en/docs/historical-weather-api) responses, 28 December 2022–1 January 2026, with six-hour example cutoffs during 2023–2025. Eight features: 24/72-hour precipitation totals, maximum hourly precipitation in the past 24 hours, 24-hour mean temperature/humidity/surface pressure, and seasonal sine/cosine. Complete sources have no snowfall. Missing windows are excluded explicitly, never filled. Train: **5,842 examples (113 at/above threshold)**; chronological 2025 holdout after a four-day embargo: **2,888 examples (96 at/above threshold)**. Confusion matrix `[[2273, 519], [8, 88]]` (TN/FP, FN/TP); precision **0.1450**, recall **0.9167**, F1 **0.2504**. Low precision and 519 false positives prevent warning use. Overlapping windows/nearby coastal grids mean these are not independent event counts.

Historical ERA5 (0.25° delayed reanalysis) and live best-match weather model output differ in grids, models and publication semantics. Matching variables, units and transformations are verified; **training/serving parity remains a proxy requiring validation**. Past valid-time boundaries do not establish historical availability as issued or operational forecast skill. Do not interpret the held-out reanalysis metrics as live station accuracy.

The committed portable JSON artifact includes the fitted scaler and learned coefficients, checksummed and verified against scikit-learn across the entire holdout. Startup/inference needs no training data or credential. Raw responses and the detailed example table remain local. Model metadata retain exact parameters, original source checksums and actual metrics. Open-Meteo data: CC BY 4.0; its free service has non-commercial terms. Place coordinates: © OpenStreetMap contributors, ODbL 1.0. No restricted SOI-derived values enter this model.

Offline source-to-dataset reproduction and exact retraining, when the retained originals are present:

```bash
backend/.venv/bin/python -B scripts/train_rainfall_outlook.py validate
```

The `fetch` command makes at most one bounded official request per missing source and verifies cached originals; `train` refuses the existing immutable model/dataset version. Reproduction into a new version requires explicitly changing version/output paths rather than overwriting this one. No model fitting happens in the application or ordinary API requests.

## Shelter navigation verification status

Task 7 stopped at the source-verification gate on 4 October 2026. Karnataka government records identify **Thekkatte MPCS** and **Padu-Kapu MPCS**, but neither facility's coordinates or entrance could be verified sufficiently for navigation. Current opening, accessibility, occupancy and capacity remain unknown. Those historical listings remain unverified and unactivated. Sprint 8 now provides a separate administrator-controlled directory and external entrance directions, described below; it does not import these historical facilities.

The [source register](docs/DATA_SOURCE_REGISTER.md#task-7--shelter-discovery-evidence-gap-4-october-2026) records the official documents, exact pages, bounded map checks and remaining evidence gap. To proceed, a facility-specific authoritative coordinate record or independently corroborated building/entrance location is needed. No openrouteservice key or database URL was configured during verification, and no live route was requested.

## Run locally

### One-command Linux demonstration

After the existing dependency/database setup and private configuration, run
`./start.sh` from the repository root (or invoke its absolute path from another
directory). It activates **backend/.venv**, checks Python/Node/Vite dependencies,
starts only the existing **floodpulse-sprint6-db** PostgreSQL/PostGIS container if
stopped, and verifies database connectivity, required schema/role permissions
and the active directory without writes. It then starts loopback FastAPI and the
Vite **development** server, and prints URLs only after readiness succeeds:

- Application: **http://127.0.0.1:14180**
- Administrator: **http://127.0.0.1:14180/admin**
- Backend: **http://127.0.0.1:18050**

Configure `DATABASE_URL` (directory reader) and `SHELTER_DATABASE_URL`
(restricted shelter service), both pointing at the existing
`127.0.0.1:55436/floodpulse_directory`. Either privately export them, or use the
ignored local `data/tmp/launcher/config.json` profile below. Environment values
take precedence. The profile references separately provisioned password files;
passwords are not embedded/copied into the profile, printed or passed as command
arguments. Profile/password files must be regular, user-owned and owner-only
(`chmod 600`); symlinks are rejected. The launcher never sources or overwrites
`.env`, evaluates shell code or creates credentials. Defaults
are `LOCATION_DIRECTORY_BACKEND=postgres`, `SHELTER_DIRECTORY_MODE=live`,
`SHELTER_COOKIE_SECURE=false` for explicit loopback HTTP, and
`SHELTER_PUBLIC_ORIGIN=http://127.0.0.1:14180`. If already configured, these
values must agree with the launcher. Optional `FLOODPULSE_BACKEND_PORT` and
`FLOODPULSE_FRONTEND_PORT` select other free loopback ports; a configured shelter
origin must match the frontend port. Maintenance credentials are removed from
the API environment; database and Telegram secrets are removed from Vite's
environment. Telegram configuration is optional and no notification is sent.

An example **credential-free** profile structure (use the actual private file
paths configured by your database administrator):

```json
{
  "database_connections": {
    "DATABASE_URL": {
      "url": "postgresql+psycopg://floodpulse_location_reader@127.0.0.1:55436/floodpulse_directory",
      "password_file": "private/directory-password"
    },
    "SHELTER_DATABASE_URL": {
      "url": "postgresql+psycopg://floodpulse_shelter_app@127.0.0.1:55436/floodpulse_directory",
      "password_file": "private/shelter-password"
    }
  }
}
```

Relative password paths resolve from the repository root; absolute paths are
also supported. Keep these files outside Git. This workspace's local profile
already references its existing restricted-role files. It is deliberately not
distributed in a clone. Virtual-environment activation only selects Python;
it does not set database connections. `start.sh` selects `backend/.venv` itself,
so prior activation of the root `.venv` is unnecessary.

`./start.sh --check` checks prerequisites **without starting any service**;
`./start.sh --help` displays usage without requiring configuration. Press
**Ctrl+C** to stop only the launcher's backend/frontend process groups, including
their children. PostgreSQL is left running, including when the launcher started
it. A checkout lock and port checks prevent duplicate/conflicting launches;
unrelated processes are never terminated.

Prerequisites: Linux Bash and `docker`, `flock`, `setsid`, `timeout`, `curl`, the
existing Python environment, supported Node/npm and installed frontend packages.
The container/volume, PostGIS, migrations and directory import must already have
been provisioned via the documented maintenance workflow. The launcher does
**not** install packages, create/reset databases or volumes, migrate/import data,
provision an admin, create shelters, train ML or download datasets.

Errors identify the failed stage. Missing private configuration, dependencies,
container, schema/import or role grants require the corresponding README setup;
a stopped database fails `--check` but normal startup can start it. Port/lock
conflicts require closing your own prior session or choosing free ports, not
killing arbitrary processes. Private service logs are in
`data/tmp/launcher/backend.log` and `frontend.log`; they are not printed
automatically or committed. Failed startup shuts down owned web processes.
The [demonstration guide](docs/RELEASE_DEMONSTRATION.md) retains the production
build procedure, safe admin demonstration and recovery steps.

The Git checkpoint includes extraction/validation code, manifests and permitted small CSV/GeoJSON/PNG products. Original rasters (`*.tif`) and the recovery copy stay in this local workspace and are excluded from ordinary Git history. A fresh clone therefore does **not** contain complete historical-spatial or drainage versions: their validators and APIs return explicit unavailable states until the exact original rasters matching the committed manifests are supplied through separate storage. Do not regenerate files inside a completed version or weaken its checksum checks. Browser map tests require the complete local versions. Global Flood Database derivatives remain **CC BY-NC 4.0**, including their non-commercial condition; other sources retain the separate terms recorded in each manifest. This checkpoint does not grant a common licence over all data.

Requires Python 3.12+ and Node.js 22.12+ (or 20.19+).

From the project root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from the project root:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Vite proxies `/api` to FastAPI; the browser never calls the weather provider directly. API docs: http://127.0.0.1:8000/docs. `GET /api/health` checks the application process only, not upstream availability. `GET /api/weather` performs one request with a 10-second HTTP timeout and no retries. The default request uses Bengaluru; paired `latitude` and `longitude` query parameters select any valid WGS84 point without assigning a district/locality identity. Invalid pairs return 422. Weather loads immediately for the selected point and refreshes when its last successful backend retrieval reaches six hours of age. Manual refresh remains available. Automatic requests pause while the tab is hidden or the browser is offline; returning to the tab or reconnecting checks whether refresh is due. Scheduling is confined to the open browser session, not a server-side job or an Open-Meteo issuance schedule. No requests run while the application is closed.

The freshness indicator distinguishes **fresh**, **stale**, **refreshing** and **unavailable**. Backend `retrieved_at` is a successful-response UTC clock, displayed in IST; it remains distinct from current-model valid time, forecast dates and the unavailable provider issuance time. Missing/invalid/future retrieval clocks cannot establish freshness. Seven forecast dates remain tied to the retrieved response rather than shifting while data are retained. Freshness indicates retrieval age, not forecast accuracy.

Same-location refreshes retain previously retrieved information while loading. A failed refresh labels retained information **stale**, shows the error and keeps the selected location. Changing coordinates discards the old location's data and aborts its request; late responses cannot replace the new selection. One request may run per selected location. Browser requests time out after 15 seconds. Failed retrieval cycles permit at most three attempts: the first attempt, a retry after 30 minutes, then one after 60 more minutes. Hidden/offline time can defer these retries; visibility/focus events never bypass backoff. After three failures, automatic retries pause until manual refresh or location change. Manual refresh starts a new bounded cycle. Successful responses with an unknown retrieval clock wait six hours before another automatic attempt; already-stale timestamps get a 30-minute cooldown. No missing readings or dates are filled.

The historical panel lets users select event **2728** (14–30 September 2005) or **3551** (25 September–12 October 2009). `GET /api/historical-floods` provides the catalogue and genuine Udupi boundary; `GET /api/historical-floods/{event_id}` provides the event's verified GeoJSON. FastAPI reads `data/processed/udupi_flood_spatial_v1/` locally, verifies checksums and serves explicit unavailable states if it is absent or invalid. Application startup needs no Earth Engine credentials. Basemap tiles require internet access; the district and flood polygons still display if tiles fail.

`GET /api/drainage-research` serves the local study geometry, layer metadata, legends, source/licence notices and mapped drain inventory. `GET /api/drainage-research/layers/{elevation|slope|land_cover}.png` serves verified map previews. Missing/invalid versions return HTTP 503, and unknown layer names return 404. PNGs are reprojected to Web Mercator for Leaflet; the authoritative rasters are GeoTIFFs in UTM 43N. Opening the panel requires no Earth Engine or Overpass requests. Sources: Copernicus WorldDEM-30 licence with attribution/liability notices, ESA WorldCover CC BY 4.0, OSM ODbL 1.0. Full provenance is in the GIS manifest and existing source register.

Validate this version offline with the existing spatial Python dependencies:

```bash
scripts/.venv/bin/python -B scripts/extract_udupi_drainage.py --validate-only
```

The extractor uses the existing authorized `floodpulse` project, 10-second EE requests with no retries, bounded Overpass/download responses and a 120-second total limit. It never authenticates, launches exports or re-extracts historical flood data. Reproduction requires an explicitly new output directory; a completed version is never silently replaced:

```bash
# Optional live reproduction; creates a separately named research version.
scripts/.venv/bin/python -B scripts/extract_udupi_drainage.py --project floodpulse --output data/processed/udupi_drainage_gis_v1_reproduction
```

OSM changes over time; the original query responses and snapshot timestamps are retained so the completed version can be reproduced/validated without asserting a later OSM query will return identical data.

This is **historical event-window maximum extent**, not daily flood occurrence, current flooded roads, predicted risk or evacuation guidance. Flood data: Global Flood Database V1, Cloud to Street / Dartmouth Flood Observatory, Tellman et al. (2021), **CC BY-NC 4.0** (attribution and non-commercial use required). Boundary: geoBoundaries v6, William & Mary geoLab, CC BY 4.0. Dataset provenance and limitations are in the spatial manifest and `docs/DATA_SOURCE_REGISTER.md`.

If port 8000 is occupied, start Uvicorn with `--port 18000` and start Vite with `FLOODPULSE_API_TARGET=http://127.0.0.1:18000 npm run dev -- --host 127.0.0.1`. The same variable works with `npm run preview`.

## Data meaning and sources

- [Open-Meteo documented Forecast API](https://open-meteo.com/en/docs): current temperature, relative humidity and precipitation, plus up to seven daily precipitation totals, min/max temperatures and provider weather condition codes. Current conditions are **weather model estimates**, not observed station measurements. Precipitation covers the preceding provider interval; daily totals use Asia/Kolkata calendar days.
- [Bengaluru reference coordinates from OpenStreetMap Wiki](https://wiki.openstreetmap.org/wiki/Bengaluru): 12.9767936, 77.5900820. The provider's returned grid coordinates are shown separately. One reference point is not statewide or neighbourhood-level coverage.
- Weather attribution: Open-Meteo, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The public API is for non-commercial use under [provider terms](https://open-meteo.com/en/terms).
- `current.valid_at` is the current model estimate's valid time; forecast rows have local validity dates. `retrieved_at` is the backend's UTC retrieval time, displayed in IST. Forecast dates are Asia/Kolkata calendar days beginning today, not rolling 24-hour periods; today includes elapsed hours. Daily weather codes describe the most severe condition for that day. `forecast_coverage` records requested/returned/valid day counts and missing dates; omitted days are never fabricated. `forecast_units` identifies mm, °C and WMO codes. A valid day has at least one non-null daily value; coverage `complete` concerns dates, while missing individual fields still produce partial status. Station observation time and forecast issue time are explicitly unavailable: this endpoint does not supply them. Retrieval time is not forecast issue time.
- Null values remain null and display **Unavailable**. Fewer returned days display incomplete coverage; an empty daily array can still show valid current conditions with a daily-forecast unavailable notice. Partially missing readings are marked partial. HTTP failures or invalid/empty provider payloads return HTTP 503 with attribution and no weather values. Estimates older than 90 minutes are flagged stale (an application display policy).

## Verify safely

From the project root:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
cd ../frontend
npm run build
npm test
npm run test:map
```

Tests use `httpx.MockTransport`, temporary working directories and a socket guard that rejects network/database connections. Mocked weather values exist only in tests. Neither runtime nor tests write weather archives. Location persistence is separate from weather; ordinary unit tests forbid database access.

Frontend unit tests mock fetch/Leaflet in isolation. Browser map tests require Chromium (`npx playwright install chromium`) and the saved spatial dataset; they start local backend/frontend servers, block external tile/weather requests and compare API responses/rendered Leaflet cell counts with exported GeoJSON. Their artifacts go to the system temporary directory.

Optional spatial extraction/validation with the already authorized project (no authentication or Drive export):

```bash
uv pip install --python scripts/.venv/bin/python -r scripts/requirements-earthengine.txt -r scripts/requirements-spatial.txt
scripts/.venv/bin/python -B scripts/extract_udupi_spatial.py --project floodpulse
scripts/.venv/bin/python -B scripts/extract_udupi_spatial.py --validate-only
```

An existing spatial version is refused before live queries. Original GeoTIFF bytes and exact georeferencing are retained, along with district-clipped raster-cell polygons. The existing daily research dataset is read only. Earth Engine's edge-overlap clipping is reconciled with the previous centre-in-district reductions; exclusions and original raster counts are recorded, not hidden.

For one optional live check while the backend is running:

```bash
curl --max-time 15 --fail-with-body http://127.0.0.1:8000/api/weather
```

`npm run preview -- --host 127.0.0.1` serves the built dashboard with the same local API proxy. Production hosting will need a reverse proxy for `/api`; Vite preview is a local verification server.

PostgreSQL/PostGIS location-directory persistence, experimental rainfall ML inference, administrator-controlled shelter assignments and manually approved Telegram notices are implemented as described here. Predictive drainage analysis, automatic emergency alerts and validated flood prediction remain unavailable. External shelter directions are not verified flood-safe.

The frozen Stage 5/5A reviews record the older README and three-day weather source as historical inputs. To reproduce those reviews, validate with the exact recorded input bytes from Git, whose checksums must match their immutable manifests, rather than substituting the current application version. Run `scripts/.venv/bin/python -B scripts/validate_frozen_app_reviews.py` for this read-only reproduction; it verifies original input hashes before using a temporary replay workspace. Their scientific outputs and original checksums remain unchanged.

### PostgreSQL/PostGIS location directory

The location API supports an explicit database backend. `LOCATION_DIRECTORY_BACKEND=file` (API default) serves the reviewed immutable snapshot for offline/migration use; the documented launcher explicitly selects `postgres`. `LOCATION_DIRECTORY_BACKEND=postgres` reads only the active imported PostgreSQL version. Missing configuration, unavailable database, missing migration/import or failed integrity checks return HTTP 503; there is **no automatic file fallback**. Weather/GPS/map requests remain independent of the directory database. These settings do not change flood-prediction availability.

Use the existing deployment's PostgreSQL/PostGIS service where authorized. This checkout had no configured database URL, models or Alembic history. Sprint 6 verified a separate persistent Docker database, PostgreSQL **16.4 / PostGIS 3.4.3**, using an already cached `postgis/postgis:16-3.4` image. The inaccessible native PostgreSQL 18.6 service was left untouched. The cached image is verification infrastructure, **not a current security-patch recommendation**: deploy with a reviewed, patched compatible PostgreSQL/PostGIS image and normal backup/TLS/secret management.

For a new PostgreSQL 16 development instance, use a private password file outside Git and a dedicated persistent volume. For example, with `FLOODPULSE_POSTGIS_IMAGE` set to a reviewed image and `FLOODPULSE_DB_PASSWORD_FILE` to an existing private file:

```bash
docker run -d --name floodpulse-location-db \
  -p 127.0.0.1:55432:5432 \
  -v floodpulse_directory_data:/var/lib/postgresql/data \
  --mount type=bind,src="$FLOODPULSE_DB_PASSWORD_FILE",dst=/run/secrets/db-password,readonly \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/db-password \
  -e POSTGRES_DB=floodpulse_directory "$FLOODPULSE_POSTGIS_IMAGE"
```

The volume path above applies to PostgreSQL 16; follow the image's documentation for other major versions. Do not point tests at an existing production database. Enable PostGIS through an authorized administrator if it is not already present (`CREATE EXTENSION postgis` in the intended database). The migration checks for it and fails explicitly; it does not install extensions or modify system services.

Install backend requirements into its virtual environment. Supply maintenance credentials only through `LOCATION_DIRECTORY_ADMIN_URL` (or `DATABASE_URL` for the dedicated maintenance process), using the `postgresql+psycopg://` scheme with URL-encoded password characters. `.env.example` documents variable names; the application does not automatically load `.env` files. Never commit actual credentials.

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -B -m app.import_locations
# A second import reports already_imported; no duplicate rows/timestamp reset.
# Import a retained version without changing the active pointer:
.venv/bin/python -B -m app.import_locations --directory ../data/reference/karnataka_location_directory_v1 --no-activate
```

Revision `0001_location_directory` creates five `location_directory_*` tables for versions/provenance, districts, localities, lookup identifiers and the active-version pointer, plus indexes and constraints. Verified geometry is `POINT`, EPSG:4326, **X=longitude / Y=latitude**; disabled Kaup has no geometry. Import validates source checksums and records first, serializes concurrent imports, then imports and activates in one transaction. Conflicting content under an existing version fails; no partially imported version is activated. JSONB stores original public records/manifest; both original-byte and canonical-content checksums are retained. V1 source files remain immutable. Downgrade removes only these new tables and retains PostGIS/unrelated schema; do not downgrade a live directory without a backup.

Use a distinct read-only application login, granting `CONNECT` on the intended database, `USAGE` on the intended schema and `SELECT` only on:

```sql
GRANT SELECT ON location_directory_versions, location_directory_districts,
  location_directory_localities, location_directory_identifiers,
  location_directory_active TO floodpulse_location_reader;
```

An administrator should create/configure this login with private credentials through their normal secret-management process. Do not grant it table ownership, schema CREATE or data-write privileges. Run the public API with only its reader `DATABASE_URL` and `LOCATION_DIRECTORY_BACKEND=postgres`, removing the maintenance URL from that process:

```bash
.venv/bin/python -B -m uvicorn app.main:app --host 127.0.0.1 --port 18040
```

Existing location routes and response contracts remain unchanged. Each read uses a bounded, read-only repeatable-read transaction and closes the connection; pools are disposed at application shutdown. The dataset remains five selectable points across two districts and 31 NIC names with unresolved current-LGD identity, with OSM/geoBoundaries attribution and reuse conditions preserved. No SOI geometry or scientific observation tables are imported.

Normal tests remain offline. Explicit integration tests require a maintenance URL with permission to create a **new isolated test database** and enable PostGIS. They create/drop only a UUID-named `floodpulse_sprint6_test_*` database, never the configured application's database:

```bash
.venv/bin/python -B -m pytest integration_tests -q
```

Without that explicit configuration they are skipped, not reported as verified PostgreSQL tests. Run frontend Playwright with the reader environment to verify the same selector against PostgreSQL. Browser weather regressions use isolated fixtures; a live Open-Meteo demonstration is a separate bounded integration operation.

## Administrator-controlled emergency shelters

Open `/admin` to manage manually assigned facilities. This is a project prototype, without affiliation with a disaster-management authority. There is **no public registration, default administrator password or imported operational shelter listing**. The citizen dashboard's **Find open shelters** control queries this separate directory; name/GPS/map weather selection remains independent. Existing historical shelter references are not imported or activated.

Revision `0002_emergency_shelters`, following the existing location-directory migration, creates `shelter_admins`, `shelter_sessions`, `shelter_login_limits`, `emergency_shelters` and `shelter_audit`. It uses the same PostgreSQL/PostGIS database and preserves location tables. Entrance geometry is WGS84 `POINT`, **X=longitude / Y=latitude**, checked against stored numeric coordinates. Database constraints enforce capacity, occupancy, coordinate pairs, verification and status consistency. Updates use revision checks and transactions that also insert audit snapshots; a failed audit insert rolls back the assignment. Downgrade removes only these shelter tables; back up operational data before any downgrade.

Run `alembic upgrade head` through the existing authorized maintenance environment. Provision a designated administrator privately; the command prompts twice without echoing or saving the password:

```bash
cd backend
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME
# Explicit password rotation also revokes all existing sessions:
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME --reset-password
```

The maintenance process alone receives `LOCATION_DIRECTORY_ADMIN_URL`. Passwords must contain 16–128 characters and are salted using scrypt (`N=131072, r=8, p=1`), the [OWASP documented fallback when Argon2id is unavailable](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). No administrator password file is supported. Do not pass the maintenance URL to the API or reuse the directory's read-only role for writes. Configure a distinct, privately provisioned `floodpulse_shelter_app` login with only these privileges in the intended database:

```sql
GRANT CONNECT ON DATABASE floodpulse_directory TO floodpulse_shelter_app;
GRANT USAGE ON SCHEMA public TO floodpulse_shelter_app;
GRANT SELECT ON location_directory_districts, location_directory_active,
  shelter_admins TO floodpulse_shelter_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON shelter_sessions, shelter_login_limits
  TO floodpulse_shelter_app;
GRANT SELECT, INSERT, UPDATE ON emergency_shelters TO floodpulse_shelter_app;
GRANT SELECT, INSERT ON shelter_audit TO floodpulse_shelter_app;
```

The login must not own tables, create schema objects, alter administrator accounts, delete shelters or update/delete audit history. Supply its private same-database `SHELTER_DATABASE_URL` to the API. Keep the existing directory reader `DATABASE_URL` and `LOCATION_DIRECTORY_BACKEND=postgres` unchanged. Also set:

- `SHELTER_PUBLIC_ORIGIN`: exact browser origin, without a trailing slash, e.g. `https://floodpulse.example.org`.
- `SHELTER_COOKIE_SECURE=true`: production default; HTTPS is required.
- `SHELTER_DIRECTORY_MODE=live`: production default; demonstration assignments are excluded.

Explicit loopback development may use `http://127.0.0.1:5173` (or the actual local frontend port) with `SHELTER_COOKIE_SECURE=false`; non-loopback insecure cookie configurations fail closed. Vite proxies `/api` to the existing FastAPI target. Deployments must preserve `Origin`, serve the frontend/API under the configured same origin, and apply the frame-denial/nosniff headers to static frontend responses as the included Vite dev/preview servers do. Configure TLS at deployment; this sprint does not publish a hosted emergency service.

Authentication uses random opaque HttpOnly/SameSite=Strict cookies with only token hashes stored in PostgreSQL, an eight-hour absolute/30-minute idle lifetime, server-side logout revocation, exact-Origin checks and a per-session CSRF header for writes. Login requires a same-origin JSON request and custom header. Persisted 15-minute limits apply per account and direct client address; forwarded addresses are deliberately not trusted. Reverse-proxy deployments may share the peer limit unless a separately reviewed trusted-proxy policy is introduced. Responses never cache administrator or shelter availability data. Passwords, session cookies and CSRF tokens must not be logged; the React CSRF token remains in memory.

Create a **Pending verification** assignment first. Enter its facility/address, NIC district association, verified entrance (map selection or coordinates), capacity/occupancy, facilities, accessibility and restrictions. A marker is only a proposed entrance; it does not verify a facility. To save **Open** or **Full**, independently confirm **authorization, exact entrance, current usability and capacity**, and record verification evidence. All four confirmations reset in the form and are required on every Open/Full update. Open requires spare capacity; Full requires occupancy equal to capacity. Closed preserves the previous verification timestamp as history but is not available. Pending clears active verification. Contact details are public only with explicit disclosure approval; internal notes/evidence/administrator identities stay private.

Public `GET /api/shelters` returns only Open assignments with spare capacity and verification less than **24 hours** old. This expiry is an application policy, not an official emergency-service standard; it is not an occupancy reservation or assurance of access. Optional latitude/longitude computes approximate **straight-line** PostGIS distance, not road distance. Google Maps URLs use the exact stored entrance and optional selected origin, following the [official Maps URLs directions format](https://developers.google.com/maps/documentation/urls/get-started). External directions are **not verified flood-safe**. Refresh and confirm access with local authorities before travel. Full, Closed, Pending, expired and demonstration records never become live destinations. An empty directory explicitly states: “No currently verified open shelters are available in this directory.” No weather/AI output creates assignments or alerts.

Protected APIs: login/session/logout, `GET/POST /api/admin/shelters`, `PUT /api/admin/shelters/{id}` and `GET /api/admin/shelters/{id}/audit`. Public endpoints are read-only. Administrative lists are paginated in bounded pages of 100; audit retrieval currently shows up to 100 stored events. Database failures return explicit 503 errors, unauthorized access 401, CSRF/origin failure 403, revision conflict 409 and invalid input 422.

Normal unit tests are offline. The existing explicit PostgreSQL integration harness creates/drops only UUID-named test databases and verifies real PostGIS, migrations, constraints, permissions, authentication and rollback. A labelled isolated browser demonstration exercised Pending → Open → Full → Closed → Open, exact directions, five audit events, logout, mobile layout and real existing weather. Its fixture database is removed afterwards. The live directory remains empty until designated staff provision an account and genuinely verify facilities; no demonstration passwords or assignments are retained in the live database. No historical or restricted geographic data are imported.

## Administrator-approved Telegram notifications

Sprint 9 adds an **Alerts** section inside the existing authenticated `/admin` portal. It is a prototype messaging tool, not an official disaster warning service. Experimental rainfall predictions never generate or trigger a notification. No bot is configured by default, and no live Telegram delivery was verified in this checkpoint.

Apply the existing Alembic workflow to revision `0003_admin_notifications`; it adds only `admin_notifications` and preserves directory/shelter tables. Give the existing separately provisioned application role the additional table-scoped privilege through the maintenance connection:

```sql
GRANT SELECT, INSERT, UPDATE ON admin_notifications TO floodpulse_shelter_app;
```

Do not grant public writes, schema ownership or DELETE. Existing admin provisioning, HTTPS same-origin sessions, idle expiry, login rate limits and CSRF configuration remain required. An actual designated operator still needs private provisioning; the production database contains no test administrator or operational notices.

Privately provision a bot using the [official Telegram bot workflow](https://core.telegram.org/bots/tutorial), arrange permission to send to its intended destination, and configure the **backend process environment**:

- `TELEGRAM_BOT_TOKEN`: the private BotFather token; never put it in Git, browser configuration, URLs in shell commands, screenshots or logs.
- `TELEGRAM_DESTINATIONS`: a JSON object mapping stable private aliases to `{ "label": "Operator-facing name", "chat_id": "<NUMERIC_CHAT_ID>", "test_only": false }`. Actual chat IDs are server-only; the admin API returns aliases and labels.
- An optional private test destination is another entry with `test_only: true` and its positive private-chat ID. Demonstration mode permits **only** such entries; it cannot target a configured public broadcast destination. No fixture bot configuration is loaded in production.

The application does not automatically load `.env`. Keep actual configuration outside the repository, restrict its permissions and rotate a leaked token through Telegram. Do not paste credentials into support requests. Missing/invalid configuration disables the composer with a clear reason; it never triggers automatic network requests or substitute delivery results. Egress requires HTTPS to `api.telegram.org`. This client deliberately avoids token-bearing URL logging, redirects, environment proxies and automatic retries; ensure external APM/network tooling also redacts the Bot API credential path.

Operator workflow: sign in → choose an authorized destination → write an informational or emergency notice → optionally select a currently verified Open shelter → **Review exact notification** → verify the complete server-rendered text and destination → check the explicit approval box → **Approve and send once through Telegram**. Do not use experimental ML as evidence for flood claims, shelter availability or evacuation instructions. Review uses plain text, without Markdown/HTML transformations or link previews. Optional shelter details are read from PostgreSQL, omit private notes/contact data, and are checked again before sending. Changed/expired shelter evidence requires a new preview. Preview approval expires after 30 minutes; destination reconfiguration also invalidates it.

Protected API contracts (all require the existing administrator session; POSTs additionally require same-origin and CSRF):

- `GET /api/admin/notifications/options`: configuration readiness, authorized destination labels and currently verified Open shelter choices.
- `POST /api/admin/notifications`: create/retrieve an idempotent **unsent preview** using a client UUID `request_id`; no Telegram request occurs here.
- `POST /api/admin/notifications/{id}/send`: explicit boolean `approve: true` and exact reviewed `content_sha256`; only the composing administrator can approve.
- `GET /api/admin/notifications?limit=50&offset=0`: bounded authenticated history, maximum 100 per page.

The PostgreSQL record includes the composing/confirming administrator, exact message, destination alias/label, UTC creation/approval/attempt/result times and sanitized outcome codes. It contains no bot token or chat ID. Each record is durably claimed **before** the external request, preventing repeated clicks, concurrent requests and retry sends for that record. A token/chat fingerprint prevents destination substitution after preview. Sending uses one TLS-verified POST with 10-second connection/socket timeouts and a bounded response body, following the [official `sendMessage` protocol](https://core.telegram.org/bots/api#sendmessage).

Outcomes are `draft`, `sending`, `accepted`, `rejected` or `delivery_unknown`. **Accepted means Telegram API acceptance, not recipient reading or action.** Network timeouts or unverifiable responses remain uncertain and are never retried automatically. A crash or final database-write failure can leave `sending`; inspect Telegram and the recorded attempt before considering a separate notice. This is at-most-one attempt per notification, not a guarantee of exactly-once delivery. Terminal records cannot be sent again. Refreshing history never sends a message. The component cancels pending reads on exit and removes repeat-send controls as soon as an attempt starts, including after a lost browser response.

Verification uses offline protocol responses, authenticated disposable PostgreSQL tests and visibly labelled browser fixtures. None sends an operational announcement. Live delivery remains **BLOCKED until a legitimate bot and authorized private test chat are configured**. After that, a designated administrator should explicitly approve one clearly non-emergency private test notice, then inspect Telegram acceptance and the matching database record. Do not test on public channels or assume a simulated result verifies delivery.


## Karnataka Flood Intelligence Map

Open `/flood-map` and select one of 31 NIC-listed districts, or statewide view. Historical Flood Locations and Potential Flood-Prone Zones have independent controls. The eligible public historical coverage is **56 raster-cell polygons from two Udupi events**; no verified potential-hazard geometry is registered. Other districts remain selectable with explicit coverage limitations. Only Udupi/Dakshina Kannada have reviewed navigation bounds. Click a historical polygon or use the keyboard cell selector to inspect its dates, observation quality, Unknown mechanism, source licence and original geometry checksum. Drainage context is a separate bounded Udupi study with zero returned mapped drain/ditch ways, not an overflow assessment. Shelter markers require current verified Open assignments with spare capacity. See [map methodology and API](docs/FLOOD_INTELLIGENCE_MAP.md) for sources, restrictions and demonstration steps. No new migration or source download is needed; restart the existing application launcher after updating backend code.

## Full-screen workspaces and admin map references

Desktop/laptop screens at least 1100 px wide and 740 px tall use viewport workspaces with scrollable detail cards. Mobile/tablet screens retain natural scrolling. Home combines a Karnataka map, weather/forecast, experimental AI and shelter summaries; Weather & AI keeps its map optional; Flood Map emphasizes the 56 retained historical polygons and a separate evidence sidebar; Shelters emphasizes approved destinations; Admin separates shelter management and Telegram review. Detailed panels can scroll without changing the selected location or requesting weather again.

Public latitude/longitude **entry fields have been removed**. Use **Change location → Search districts and localities** to type a name or choose among 31 NIC district names, then select a verified locality. Five selectable points across Udupi and Dakshina Kannada remain the exact existing subset; Kaup stays disabled. A name-only district filters evidence without inventing a weather point. District selection carries into Flood Map; map/GPS still select points independently. Coordinates remain visible only as source/point metadata, with separate provider-grid values. Seven calendar-day forecasts and six-hour browser-session freshness are unchanged.

The admin entrance picker adds street/satellite/hybrid controls and explicit building-reference search, while keeping activation manually verified. Satellite/hybrid and external building search are disabled unless an authorized MapTiler browser configuration is supplied. No imagery access or successful live satellite rendering is claimed. See [provider evaluation, private configuration and safe administrator login](docs/ADMIN_SATELLITE_MAP.md). The current read-only check found no active administrator; provision only through the existing password-prompt utility and authorized maintenance shell. Neither reference search nor imagery can verify a shelter or trigger Telegram messages.

### Original-wireframe workspaces

Home, Weather & AI, Shelters and authenticated Admin now follow the user's [original photographed layouts](docs/design/floodpulse_wireframes/DESIGN_REFERENCE.md): information/workflows on the left, geographic context on the right on desktop, naturally stacked on mobile. Open **Change location → Search districts and localities** to use the same district filter across public routes. Only a verified locality, GPS request or map click changes the weather point. A historical flood-cell selection remains evidence-only. Weather source/grid/timestamp details are available in their disclosure beneath the forecast.

The map is optional on Weather through **Hide/Show geographic context**. Inactive routes pause weather/model work; returning reuses a fresh selected-point receipt or refreshes if due. The shelter list and map share the same revalidated response. Admin's assignment district filter applies to the loaded page; pagination remains necessary for additional records. Satellite access, provisioning, CSRF/session and Telegram approval procedures above remain unchanged.

The [future flood-reporting design](docs/EXPERIMENTAL_FLOOD_REPORTING_DESIGN.md) is documentation only; submissions are not enabled. See [wireframe implementation and screenshot mapping](docs/WIREFRAME_IMPLEMENTATION.md) for verification.
