# FloodPulse — weather, historical flood evidence and GIS research

A React + Vite dashboard → FastAPI → Open-Meteo seven-day weather dashboard with manual coordinates, Leaflet point selection and user-requested GPS (Bengaluru by default), plus a Leaflet map of two verified historical satellite flood events in Udupi. Historical data come from bounded real Earth Engine queries. `QandA.md` is preserved as historical product context; its old implementation and accuracy claims do not describe this rebuild.

The optional **Drainage Research Layers** panel reads `data/processed/udupi_drainage_gis_v1/`: a 3 km × 3 km study window around a verified Udupi OSM city point, not an official municipal boundary. Select surface elevation, derived slope or 2021 land cover. The bounded OSM query returned no drain/ditch ways; unmapped infrastructure remains unknown. Terrain is a 30 m surface model including buildings and vegetation, suitable for exploratory surface research with those limitations. These layers do not provide drainage-risk scores or live waterlogging information.

## Karnataka place selection

Choose **Search districts and localities**, search a name or select a district, then choose a mapped locality. The map immediately centers on its retained WGS84 settlement point and the existing point-weather endpoint retrieves seven provider-supplied forecast days. Manual coordinates, map clicks, GPS and six-hour browser-session refresh remain available. Selecting a district filters places and navigates where reviewed public bounds exist; it never requests district-wide weather or changes the previously selected weather point.

The active public directory, `data/reference/karnataka_location_directory_v2/`, contains **31 NIC-listed district names**, with independent current-LGD reconciliation still unresolved. Stable application IDs use the NIC website namespace, not guessed LGD codes. **Five selectable mapped settlements** are verified: Udupi, Karkala, Kundapur and Saligrama in Udupi district, plus Mangaluru in Dakshina Kannada. Both districts have reviewed public geoBoundaries navigation bounds. **Kaup** has an official municipal identity but remains disabled because its settlement coordinate has not been reviewed. The other 29 districts show incomplete-coverage messages and preserve manual/GPS selection. The original v1 directory remains unchanged and readable.

Kundapur retains `udupi-admin:municipality:kundapur`; lookup by `osm:node:245623778` resolves the same record. Official district records independently link Kundapur/Kundapura town names. Its genuine OSM `place=town` point is used; railway and taluk-centre results remain excluded. Saligrama's original OSM `place=village` classification is preserved separately from its official town-panchayat identity. Mangaluru also supports the source alias Mangalore. All points represent mapped settlements, not surveyed municipal centres, gauges or shelters.

Read-only APIs: `GET /api/locations/districts?q=...`, `GET /api/locations/localities?district_id=nic:udupi.nic.in&q=...`, `GET /api/locations/search?q=...`, and `GET /api/locations/localities/{locality_id}`. Search ordering is deterministic; `limit` is bounded to 50 and `offset` supports pagination. Unknown identifiers return 404, invalid parameters 422, and missing/corrupt directory data 503. Local search makes no external geocoder requests; the explicitly selected backend may use the public file snapshot or PostgreSQL. Backend checks provenance, coordinate availability and directory checksums before serving records.

Coordinates: © OpenStreetMap contributors, **ODbL 1.0**; the extracted place-point database is offered under that licence with attribution/share-alike conditions. Udupi navigation bounds: existing geoBoundaries CGAZ **CC BY 4.0**. Dakshina Kannada navigation bounds: geoBoundaries gbOpen IND ADM2, Pathways Data Pvt. Ltd./lgdirectory.gov.in, **ODbL 1.0**, represented year 2021; these are navigation context, not current official district-boundary certification. Government URLs cross-check small factual names/associations; no government HTML/text or SOI geometry is republished. The [source register](docs/DATA_SOURCE_REGISTER.md) and directory manifest retain source versions, original checksums and limitations. The weather API still identifies any requested coordinates as a point; directory provenance is displayed separately, without claiming that Open-Meteo verifies administrative identity or supplies district-wide conditions.

Reproduce the public directory offline with `backend/.venv/bin/python -B scripts/expand_location_directory.py validate` using the retained source files. `build` refuses an existing version. The original v1 validation command remains `backend/.venv/bin/python -B scripts/build_location_directory.py validate`. Runtime search reads either the explicit file backend or the active imported PostgreSQL version and makes no geocoder requests.

A fresh clone can serve the permitted directory snapshot without raw verification documents; offline source reproduction requires the retained originals locally. Both validators check source hashes, original node coordinates, actual public polygon containment and deterministic outputs without writes or network. Original SOI data and derived research tables remain local.

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

Task 7 stopped at the source-verification gate on 4 October 2026. Karnataka government records identify **Thekkatte MPCS** and **Padu-Kapu MPCS**, but neither facility's coordinates or entrance could be verified sufficiently for navigation. Current opening, accessibility, occupancy and capacity remain unknown. No shelter directory, database schema, search endpoint or routing feature has been published; the existing application remains the weather, historical-evidence and drainage-research views described above.

The [source register](docs/DATA_SOURCE_REGISTER.md#task-7--shelter-discovery-evidence-gap-4-october-2026) records the official documents, exact pages, bounded map checks and remaining evidence gap. To proceed, a facility-specific authoritative coordinate record or independently corroborated building/entrance location is needed. No openrouteservice key or database URL was configured during verification, and no live route was requested.

## Run locally

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

PostgreSQL/PostGIS location-directory persistence is implemented as described below. Python ML, predictive drainage analysis, Telegram alerts and shelter routing remain deferred. No flood prediction or risk claims are made.

The frozen Stage 5/5A reviews record the older README and three-day weather source as historical inputs. To reproduce those reviews, validate with the exact recorded input bytes from Git, whose checksums must match their immutable manifests, rather than substituting the current application version. Run `scripts/.venv/bin/python -B scripts/validate_frozen_app_reviews.py` for this read-only reproduction; it verifies original input hashes before using a temporary replay workspace. Their scientific outputs and original checksums remain unchanged.

### PostgreSQL/PostGIS location directory

The location API now supports an explicit database backend. `LOCATION_DIRECTORY_BACKEND=file` (default) serves the reviewed immutable snapshot for offline/migration use. `LOCATION_DIRECTORY_BACKEND=postgres` reads only the active imported PostgreSQL version. Missing configuration, unavailable database, missing migration/import or failed integrity checks return HTTP 503; there is **no automatic file fallback**. Weather/manual coordinates/GPS/map requests remain independent of the directory database. These settings do not change flood-prediction availability.

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
