# Administrator map references and optional satellite access

Reviewed 10 October 2026. This is a project prototype; imagery assists a manually verified entrance selection and cannot establish shelter authorization, structural safety, occupancy, usable facilities or road access.

## Provider review

| Provider | Official evidence and access | Coverage and limits | Decision |
| --- | --- | --- | --- |
| MapTiler Satellite / Satellite Hybrid | [Satellite catalogue](https://www.maptiler.com/maps/satellite/), [Maps API](https://docs.maptiler.com/cloud/api/maps/), [credentials](https://docs.maptiler.com/guides/credentials/), [terms](https://www.maptiler.com/terms/cloud/), [plans/quotas](https://www.maptiler.com/cloud/pricing/), [attribution](https://www.maptiler.com/copyright/). Account and authorized browser key required. Raster TileJSON supports Leaflet; hybrid combines imagery and labels. | Provider describes global coverage, which includes Karnataka geographically. Imagery date, usable building-level detail, labels/outlines and actual tiles at an intended facility have **not** been verified. Requests consume the account's plan quota; do not assume unlimited/free usage or guaranteed availability. | Opt-in adapter implemented; live access **CONFIGURATION_BLOCKED**. No account created, plan accepted, key configured or image retrieved. |
| Esri/ArcGIS Imagery Hybrid | [Basemap services](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/introduction-static-basemap-tiles-service/), [open styles/tiles](https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/basemaps/open-styles-tiles/), [legacy OSM Hybrid](https://developers.arcgis.com/rest/basemap-styles/osm-hybrid-style-get/). Authorized account/token, applicable service terms, attribution and billing/usage review required. | World imagery does not prove a specific Karnataka facility's imagery quality, date or complete building labels. The reviewed legacy OSM hybrid endpoint is in mature support; do not adopt an unauthenticated legacy URL as evidence of permission. | Evaluated, not configured or queried. No unkeyed proprietary tile fallback. |
| OpenAerialMap | [Imagery usage](https://docs.imagery.hotosm.org/usage/using-imagery/), [about/licensing](https://openaerialmap.org/about/). Current documented routes use imagery items/STAC and a mosaic; original imagery attribution and applicable licence must be retained. | Community-contributed coverage is incomplete. Documented mosaic zooms 0–13 show a **coverage grid**, with actual imagery at higher zooms. No appropriate Karnataka facility image/coverage has been established here. | Not a verified statewide satellite/hybrid substitute. No collection downloaded. |

## Optional MapTiler configuration

A designated operator must first review the provider's account terms, imagery/geocoding permissions, plan quotas and potential charges. This implementation does not accept terms or purchase access. Create an account only if the operator authorizes it, then create a **public browser API key restricted to the exact demonstration/deployment origins**. Never use a private service token in Vite: every `VITE_*` value is exposed in the browser bundle.

The adapter requires all three settings:

```text
VITE_ADMIN_MAP_PROVIDER=maptiler
VITE_ADMIN_MAP_TERMS_ACCEPTED=true
VITE_MAPTILER_PUBLIC_KEY=<AUTHORIZED_ORIGIN_RESTRICTED_PUBLIC_BROWSER_KEY>
```

Set these privately in the existing launcher environment, or an ignored `frontend/.env.local`, before running `./start.sh`. Never commit the configuration or copy credentials into documentation, screenshots, tests or logs. Restart Vite after changing its environment; rebuild for a production bundle. The acceptance flag records the operator's configuration decision, **not** an automatic legal acceptance. The default remains the existing OSM street map without satellite access.

The app requests the official 256-pixel TileJSON for `satellite` or `hybrid`, validates HTTPS/provider host, zoom and tile templates, and retains provider attribution as escaped text alongside MapTiler/OSM links. No imagery URL is logged or returned by FastAPI. Provider errors leave evidence overlays available with a tile-unavailable notice. Attribution must remain visible; no tile proxy, user-agent substitution, offline tile scraping or mass prefetching is used.

After configuration, an operator must open `/admin` in independent Chrome, select both modes, and verify actual HTTP-success image tiles, readable attribution, local image detail and useful labels. Until then, **live satellite/hybrid rendering is not verified**. Names, outlines and imagery currency are not guaranteed.

## Place/building references and entrance workflow

The existing five verified directory places can navigate the admin street map without satellite credentials. With authorized MapTiler access, the explicit [geocoding search](https://docs.maptiler.com/cloud/api/geocoding/) accepts 3–120 characters, requests at most five references inside a bounded Karnataka search envelope and `country=in`, and has a ten-second timeout. It is invoked by a button, not every keystroke. The envelope is a query filter, not an administrative-boundary certification. No public OSM geocoder is queried.

Selecting a directory place or geocoded result only recentres the map. It does **not** fill entrance coordinates, establish a district association, authorize a shelter, or verify any facility. Results are rendered as text. Inspect labels/outlines where supplied, zoom, and click the **actual independently verified entrance**. The click fills the admin-only coordinate fields and clears every verification confirmation/evidence entry. Review facility name, address, district and entrance; save Pending first. Open/Full updates retain the existing four required confirmations and audit workflow. No image or model output assigns or activates a shelter.

## Administrator setup and login

The current read-only database check found **zero active administrator accounts**. No account or operational shelter was created. Configure the already documented private `LOCATION_DIRECTORY_ADMIN_URL` in a separate authorized maintenance shell, then use the existing utility:

```bash
cd /home/pioneer/Projects/FloodPrediction/backend
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME
```

Choose a unique lowercase username (3–64 characters, starting with a letter; permitted subsequent characters are letters, digits, dot, underscore and hyphen). The utility prompts twice without echo for a private password of 16–128 characters and stores a password hash. Never pass a password in command arguments. Use `--reset-password` only for an explicit existing-account rotation; it revokes existing sessions. Do not expose the maintenance connection to the API.

Run `./start.sh`, open `http://127.0.0.1:14180/admin`, enter the provisioned username/password, and select Sign in. Use Shelter workspace for assignment/verification/audit and Telegram notifications for exact review and explicit approval. Sign out ends the session. The launcher sets the matching loopback origin and allows insecure cookies only for this local HTTP setup; public deployment requires HTTPS, Secure cookies and the exact same-origin configuration already documented in README.

Invalid login was exercised against the real API. Successful authentication/assignment was tested with isolated backend tests and visibly labelled browser fixtures; successful login to the current demonstration database remains pending private provisioning. No live Telegram message was sent.
