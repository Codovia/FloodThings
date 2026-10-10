# FloodPulse release-candidate demonstration

For current coverage and shelter checks, use [CURRENT_CAPABILITIES.md](CURRENT_CAPABILITIES.md).
In the shelter directory, choose **Recheck availability for directions** before the
five-second external link is revealed. A failed check removes destinations. Material
facility/entrance/capacity/usability changes clear prior admin confirmations. Reconfirm
the latest information before saving Open/Full. Logout immediately hides private state;
lost write responses require history review rather than automatic retry.

Verified locally on 10 October 2026. This is a non-commercial college-project
prototype, without affiliation with a disaster-management authority. Weather,
experimental rainfall classification, historical GIS and administrator-controlled
directory/messaging functions are separate. Validated flood prediction remains
unavailable. Telegram live delivery remains **BLOCKED**.

## Services and initialization

Use Python 3.12+, the existing `backend/.venv`, Node 22.12+ (or 20.19+) and
PostgreSQL with PostGIS. The verified local service is the existing
`floodpulse-sprint6-db` container, loopback port 55436, PostgreSQL 16.4/PostGIS
3.4.3. Do not substitute another project's database. A new deployment needs its
own privately provisioned database and roles; this guide contains no credentials.

Install through `backend/requirements-dev.txt` and `frontend/package-lock.json`
using the README procedure. Supply environment configuration through private
secret management; the application does **not** load `.env` automatically.
Never expose passwords in command arguments, screenshots or shell history.

In an authorized maintenance process, set `LOCATION_DIRECTORY_ADMIN_URL` to the
intended database. From the repository root:

```bash
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
```

For the import command, change into `backend` first:

```bash
cd backend
.venv/bin/python -B -m app.import_locations
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME
```

Provisioning prompts privately for the password twice; no public registration or
default account exists. Migrations must reach `0003_admin_notifications` after
`0001_location_directory` and `0002_emergency_shelters`. The v2 import is
transactional/idempotent: 31 districts, six locality records, five selectable
points; Kaup stays disabled. See the README for exact least-privilege grants.
Do not give the public API the maintenance URL. Fresh migration/import and
restricted-role behavior were exercised in isolated PostgreSQL databases.

## One-command local startup

After private database setup, `./start.sh` starts the existing database when
needed, FastAPI and the **Vite development server**, all on loopback. It activates
`backend/.venv` and checks dependencies, schema/permissions, active directory and
actual API/frontend readiness before reporting success. No package installation,
migration/import, account/shelter creation, model training or messaging occurs.

Required private configuration: `DATABASE_URL` and `SHELTER_DATABASE_URL` for
the documented reader/service roles at `127.0.0.1:55436/floodpulse_directory`.
Provide exported values or the ignored owner-only
`data/tmp/launcher/config.json` connection-reference profile documented in README.
The existing workspace profile references its already provisioned role password
files. It contains no passwords; explicit environment values take precedence.
The parser checks ownership/permissions, URL-encodes passwords in memory and
executes no profile text. Missing variables are named without showing values.
The script does not source `.env`, copy credentials or provision new ones.
Prior activation of another virtual environment is unnecessary: the launcher
selects `backend/.venv`. Safe local defaults are PostgreSQL directory backend, live shelter mode,
loopback-only non-Secure development cookie and matching origin at port 14180.
Already configured settings must agree. Vite receives no database/Telegram
secrets, and the API receives no maintenance URL.

```bash
./start.sh --check  # Read-only checks; starts no service
./start.sh          # Remains in the terminal until Ctrl+C
```

Open **http://127.0.0.1:14180** or **http://127.0.0.1:14180/admin**;
backend is **http://127.0.0.1:18050**. Use the script's absolute path from another
working directory. `--help` lists optional port overrides. A checkout lock and
port checks reject duplicate/conflicting instances; Ctrl+C stops only owned web
process groups/children and leaves the database/data intact. Prerequisites are
Linux Bash, Docker daemon access, `flock`, `setsid`, `timeout`, `curl`, Node/npm,
installed frontend packages and `backend/.venv`. PostgreSQL must be the existing
`floodpulse-sprint6-db` container; no Compose configuration exists in this checkout.

Missing configuration/dependencies/container or schema/import/grants: use the
separate setup steps, without sharing secret contents. `--check` deliberately
fails on a stopped database; normal startup can start the existing container.
Port conflicts: close your own session or select free ports and matching origin.
Service failure: inspect private `data/tmp/launcher/{backend,frontend}.log`, not
public screenshots/log uploads. Failed startup cleans up owned web processes.
No default administrator is created. Existing research assets remain required
for GIS layers; they are never regenerated by the launcher.

## Start the production build locally (alternative)

Privately inject these backend settings before startup:

- `LOCATION_DIRECTORY_BACKEND=postgres`
- `DATABASE_URL`: existing directory reader connection
- `SHELTER_DATABASE_URL`: separate restricted shelter-service connection to the
  **same** database; includes notification-table SELECT/INSERT/UPDATE
- `SHELTER_PUBLIC_ORIGIN=http://127.0.0.1:14180`
- `SHELTER_COOKIE_SECURE=false`: explicit loopback demonstration only
- `SHELTER_DIRECTORY_MODE=live`: genuine operational directory; initially empty

Remove `LOCATION_DIRECTORY_ADMIN_URL` from the API environment. From the root:

```bash
backend/.venv/bin/python -B -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18050
```

In a second terminal:

```bash
cd frontend
npm run build
FLOODPULSE_API_TARGET=http://127.0.0.1:18050 npm run preview -- --host 127.0.0.1 --port 14180 --strictPort
```

Visit `http://127.0.0.1:14180`. `/api/health` checks process liveness, **not**
database/provider readiness. Also check `/api/locations/districts` and
`/api/shelters` for actual directory/database access. Production deployment
requires HTTPS, Secure cookies, exact public origin and static-host security
headers; Vite preview is only the local demonstration server.

## Citizen demonstration

1. Use the shared navigation to open **Weather & AI** (`/weather`). Open
   **Change location → Search districts and localities**, select Udupi then **Kundapur**.
   The settlement point must be 13.6250993, 74.6915722.
2. Wait for seven provider-supplied daily forecast cards and **Fresh**. Show
   requested versus provider-grid coordinates, UTC retrieval rendered in IST,
   local forecast dates and unavailable provider issuance time. Six-hour refresh
   is a browser-session cadence, not an Open-Meteo issuance schedule.
3. Choose **Run experimental rainfall model**. Show target ≥64.5 mm/24h,
   Logistic Regression `rainfall_logistic_v1`, exact rolling UTC horizon,
   precision **14.50%**, recall **91.67%**, and all limitations. A below-threshold
   result does not mean dry, safe or non-flood.
4. Select Dakshina Kannada then **Mangaluru**, 12.8698101, 74.8430082. Verify
   weather and opened AI panel switch to this point, not the old location.
5. Navigate to **Flood Map** (`/flood-map`). Inspect Udupi historical events
   2728/3551 (33/23 qualified cells), open
   **Show research layers**, and toggle slope/land cover. These remain Udupi
   historical/research scopes even while weather is selected elsewhere.
6. Navigate to **Shelters** (`/shelters`); it queries the verified directory
   automatically. **Refresh shelters** retries the lookup. An empty live directory must say
   “No currently verified open shelters are available in this directory.”
   Do not insert sample facilities into the operational database to fill it.
7. Use a 390-pixel mobile viewport and the collapsible **Menu**; inspect readable
   controls, map and cards. Check direct URLs and browser back/forward. The selected
   location and six-hour weather session persist during in-app navigation.
   Name-based locality search, map/GPS selection and manual refresh remain available. Public coordinate entry is removed; requested/provider-grid coordinates remain source metadata.

Weather is real Open-Meteo model output, not station observations. The AI uses
a separate bounded past-hourly request because the daily forecast response lacks
its inputs. The actual production-build demonstration used no API fixtures and
verified both outputs against saved model parameters; both happened to be
below-threshold, a legitimate result rather than a requirement that they differ.

## Safe administrator demonstration

Create a **new isolated demonstration database**, enable PostGIS, migrate to head,
import the permitted directory and grant existing restricted reader/service roles
access **only to that database**. Provision a temporary demonstration account
there. Point both API database settings at it and use
`SHELTER_DIRECTORY_MODE=demonstration`. Restart the API; never change mode to
publish these records. The admin/public interfaces visibly say DEMONSTRATION ONLY.

Log in at `/admin`; create `DEMONSTRATION ONLY — release test facility` as
Pending, with a test entrance 13.5, 74.7, capacity 10 and occupancy 2. Explicitly
mark all four confirmations and record **isolated test confirmation, not real
facility verification** before saving Open. Inspect public discovery, reported
capacity and the external directions destination `13.5,74.7` without travelling.
Update occupancy to 3 (renew confirmations), then Full/10, then Closed. Public
destinations must disappear for Pending/Full/Closed. Audit must show all five
changes. Sign out; protected reads/writes must return 401.

Admin security: opaque HttpOnly/SameSite=Strict sessions, same-origin/CSRF writes,
rate-limited login, hashed passwords, 30-minute idle/eight-hour absolute session
limits. Open shelter verification expires after 24 hours and requires spare
capacity. This is an application policy, not an official emergency-service
standard. Directions use a verified entrance; straight-line distance is not road
distance and external routes are **not verified flood-safe**. Stop demo services,
remove only the disposable demo database, and restore original runtime settings.

## Telegram

Unconfigured Alerts remains disabled and the rest of the app works. Do not
configure fixture credentials in the application. Real verification requires a
legitimate bot and preauthorized **private test** destination, privately injected
backend configuration, and an operator reviewing and explicitly approving one
non-emergency test message. Inspect the actual API acceptance, matching audit
record and message in that private chat. API acceptance does not prove reading.
Never send to public channels for a demonstration. ML output never triggers
notifications or emergency warnings.

## Backup and recovery

Keep backups private (0600), outside Git, and inspect dump/restore exit status.
For the verified local container, an authorized operator can take a custom-format
backup without putting a password on the command line:

```bash
umask 077
docker exec -u postgres floodpulse-sprint6-db pg_dump -U postgres -Fc floodpulse_directory > /PRIVATE_BACKUP_DIRECTORY/floodpulse.dump
```

Create a **new isolated, empty** database with an authorized maintenance tool;
never restore over the application database. Restore this trusted project dump:

```bash
docker exec -i -u postgres floodpulse-sprint6-db pg_restore -U postgres --exit-on-error --single-transaction --no-owner --no-acl -d NEW_ISOLATED_DATABASE < /PRIVATE_BACKUP_DIRECTORY/floodpulse.dump
```

Compare migration revision, PostGIS version and every application-table row;
exercise read APIs before using a restored deployment. The verified release
backup/isolated restore matched all **12** application tables. Ownership/grants
were deliberately omitted for isolated verification: a deployment must
reprovision least-privilege roles. A single-database dump does not back up cluster
roles, private environment configuration, local research files or model assets.
Keep those separately under the project's existing preservation policy.
[PostgreSQL 16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html) and
[pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html) document these
archive/restore semantics. Only restore trusted backups.

Provider failure: show unavailable or explicitly stale last-known weather;
retry manually after checking connectivity. Never substitute fixtures. Missing
models/unsupported points: show AI unavailable; do not run training to repair a
demo. Database failure: show directory/admin errors, keep independent map/GPS weather usable
where possible, and check service/roles/migrations. Telegram uncertainty: inspect
history and destination; do not resend an uncertain attempt automatically.

## Validation and evidence limits

Run backend unit tests with **only**
`test_real_training_reproduction_chronological_split_and_actual_metrics`
deselected for this release (it refits the actual dataset). The read-only
replacement reconstructs all 8,768 examples, checks source/model/table hashes and
reproduces the existing 2,888-row holdout from the saved model:

```bash
backend/.venv/bin/python -B scripts/validate_saved_rainfall.py
backend/.venv/bin/python -B -m pytest backend/tests -q -k 'not test_real_training_reproduction_chronological_split_and_actual_metrics'
```

The existing explicit PostgreSQL integration suite needs a maintenance URL and
creates/drops only isolated UUID databases. Run `npm test`, `npm run test:map`
and `npm run build` from `frontend`; existing browser regressions use isolated
provider fixtures and are distinct from the real-provider demonstration above.
Frozen scientific validators need locally retained original data and the
appropriate scripts/application environments. Do not regenerate missing
protected data or alter tests to force a pass.

Sources/limits: Open-Meteo CC BY 4.0/non-commercial free-service terms; ERA5
reanalysis-trained model with unverified live parity and low precision; OSM ODbL
points; geoBoundaries navigation context; GFD CC BY-NC 4.0 historical evidence;
Copernicus/ESA research layers. See source manifests/README for individual terms.
Restricted SOI geometry and detailed research observations remain local. A fresh
clone lacks excluded original rasters: explicit GIS-unavailable responses are
expected until exact separately retained files are supplied. No official flood
service, validated flood probability, automatic alert, new shelter availability,
ML retraining or Stage 5B is delivered by this release.


## Sprint 11 — district-wise evidence map

Use the [Karnataka Flood Intelligence Map demonstration](FLOOD_INTELLIGENCE_MAP.md#demonstration). All 31 district names filter eligible public evidence; statewide reset preserves layer choices. Udupi has 56 original GFD raster-cell polygons across two events; potential-hazard polygons are unavailable. Select Udupi, zoom to mapped water and inspect a cell with mouse or keyboard. Switch to Kolar to demonstrate honest no-public-geometry coverage and unavailable zoom, then return statewide. Independently toggle hazards, bounded drainage context and verified shelters. Keep mechanisms Unknown, no-drain results unknown, and operational shelter empty state intact. Weather/AI remain on `/weather`; map cells are not model-supported settlements. Research products and the trained model are unchanged.

## Full-screen dashboard and satellite-assisted entrance review

Use all five direct routes (`/`, `/weather`, `/flood-map`, `/shelters`, `/admin`) at 1920×1080, 1366×768 and 390×844. Desktop cards/evidence panels scroll internally; small screens scroll naturally. Home is an overview, Weather & AI has an optional point map, and Flood Map remains the main GIS workspace. Scroll detail panels to review complete forecasts, source timestamps and limitations; keyboard controls remain available. Navigate between pages to confirm the selected locality and freshness lifecycle persist.

There are 31 district names and five selectable locality points, not statewide locality coverage. Select an unsupported district to demonstrate the explicit coverage message and Flood Map filter without fabricated weather coordinates. Select Kundapur/Mangaluru by name for the saved-model demonstration. Public latitude/longitude form fields are absent.

The current database has zero active administrators. In a separate authorized maintenance shell with private `LOCATION_DIRECTORY_ADMIN_URL`, use the existing provisioning command above, choose your own username and supply the password only at its two private prompts. Then start `./start.sh` and sign in at `http://127.0.0.1:14180/admin`. No default credentials exist. Real successful admin login remains a manual prerequisite; isolated browser fixtures do not establish that an operational account exists.

In Shelter workspace, use verified directory names to navigate the street map. Directory or building-reference selection **must not populate the entrance**. Inspect the facility and click its actual verified entrance; review the admin-only coordinate fields and independently confirm facility name/address, authorization, usability and capacity. Moving the entrance clears previous verification confirmations. Keep an unverified assignment Pending. Switch to Telegram notifications to demonstrate exact preview and explicit approval without sending a message. Never create an operational shelter from a demonstration fixture.

Optional Satellite/Hybrid and building search require operator-authorized MapTiler terms/account/key configuration; see [ADMIN_SATELLITE_MAP.md](ADMIN_SATELLITE_MAP.md) for the provider comparison and exact non-secret settings. No account creation or charges are performed by the app. Verify real image tiles and attribution in independent Chrome only after configuration; this delivery remains **configuration-blocked** for live satellite/hybrid. Satellite imagery does not establish occupancy, safety, access or permission.
