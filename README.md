# FloodPulse — weather, historical flood evidence and GIS research

A React + Vite dashboard → FastAPI → Open-Meteo weather slice for one Bengaluru reference point, plus a Leaflet map of two verified historical satellite flood events in Udupi. Historical data come from bounded real Earth Engine queries. `QandA.md` is preserved as historical product context; its old implementation and accuracy claims do not describe this rebuild.

The optional **Drainage Research Layers** panel reads `data/processed/udupi_drainage_gis_v1/`: a 3 km × 3 km study window around a verified Udupi OSM city point, not an official municipal boundary. Select surface elevation, derived slope or 2021 land cover. The bounded OSM query returned no drain/ditch ways; unmapped infrastructure remains unknown. Terrain is a 30 m surface model including buildings and vegetation, suitable for exploratory surface research with those limitations. These layers do not provide drainage-risk scores or live waterlogging information.

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

Open http://127.0.0.1:5173. Vite proxies `/api` to FastAPI; the browser never calls the weather provider directly. API docs: http://127.0.0.1:8000/docs. `GET /api/health` checks the application process only, not upstream availability. `GET /api/weather` performs one request with a 10-second HTTP timeout and no retries. Refresh is manual. The browser times out after 15 seconds and clears previous readings while refreshing.

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

- [Open-Meteo documented Forecast API](https://open-meteo.com/en/docs): current temperature, relative humidity and precipitation, plus three daily precipitation totals and min/max temperatures. Current conditions are **weather model estimates**, not observed station measurements. Precipitation covers the preceding provider interval; daily totals use Asia/Kolkata calendar days.
- [Bengaluru reference coordinates from OpenStreetMap Wiki](https://wiki.openstreetmap.org/wiki/Bengaluru): 12.9767936, 77.5900820. The provider's returned grid coordinates are shown separately. One reference point is not statewide or neighbourhood-level coverage.
- Weather attribution: Open-Meteo, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The public API is for non-commercial use under [provider terms](https://open-meteo.com/en/terms).
- `current.valid_at` is the current model estimate's valid time; forecast rows have local validity dates. `retrieved_at` is the backend's UTC retrieval time, displayed in IST. Station observation time and forecast issue time are explicitly unavailable: this endpoint does not supply them. Retrieval time is not forecast issue time.
- Null values remain null and display **Unavailable**. Partially missing readings are marked partial. HTTP failures or invalid/empty provider payloads return HTTP 503 with attribution and no weather values. Estimates older than 90 minutes are flagged stale (an application display policy).

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

Tests use `httpx.MockTransport`, temporary working directories and a socket guard that rejects network/database connections. Mocked weather values exist only in tests. Neither runtime nor tests write weather archives or access a database.

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

PostgreSQL + PostGIS persistence, Python ML, drainage analysis, Telegram alerts and shelter routing remain deferred. No flood prediction or risk claims are made.
