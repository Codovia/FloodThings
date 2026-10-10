# FloodPulse college-demonstration manual setup audit

Audited **10 October 2026**, branch `feature/karnataka-data-foundation`, source
commit **`adbb28a394c9de00603c0b0beaf54100e75defe4`**. This is a local prototype,
not an official emergency service. Status reflects this laptop, not a fresh clone
or public deployment. Effort estimates below are planning estimates, not measured
completion times.

The audit made only read-only inspections and SQL transactions. No administrator,
shelter, message, migration, import, package, model or service was created or
changed. No credential was printed or copied. Only this checklist and the
chronological progress-log append are authorized Git changes. Preexisting
`backend/.env.example`, older `update.md` whitespace and `QandA.md` are preserved
outside the commit. No authentication/send request was made to Telegram.

## 1. Already configured — verified on this laptop

| Item | Verified evidence | Status |
| --- | --- | --- |
| Launcher | Executable `start.sh`; selects `backend/.venv`, independent of the caller's venv/current directory; loopback FastAPI 18050 and Vite development 14180. Source matches the audited commit. | READY |
| Backend | Python 3.12.14; FastAPI 0.135.1, Uvicorn 0.41.0, httpx 0.28.1, SQLAlchemy 2.0.54, Alembic 1.20.0, psycopg 3.3.6, GeoAlchemy2 0.20.0, NumPy 2.5.3, scikit-learn 1.8.0 installed. | READY |
| Frontend | Node 22.22.1/npm 9.2.0; React/react-dom 19.2.0, Leaflet 1.9.4, Vite 7.3.6 installed; `frontend/dist/index.html` exists. Build was not regenerated in this audit. | READY |
| Private launcher profile | Ignored `data/tmp/launcher/config.json`, current-user ownership/mode 0600, credential-free service URLs; both referenced files exist, are nonempty and owner-only. Actual reader/service authentication passed without printing values. | READY |
| PostgreSQL/PostGIS | Existing `floodpulse-sprint6-db` running; PostgreSQL 16.4/PostGIS 3.4.3; only database port `127.0.0.1:55436`. No container/environment dump was printed. | READY |
| Schema and directory | Head `0003_admin_notifications`; active `karnataka_location_directory_v2`; 31 NIC district names, six locality records, five selectable points. Authenticated reconstruction passes checksum/identity validation. | READY |
| Selectable localities | Karkala, Kundapur, Mangaluru, Saligrama, Udupi. Kaup remains disabled. Current LGD reconciliation is unresolved; district names are not a new verified LGD catalogue. | READY |
| Restricted database roles | Both service logins lack superuser/create-database/create-role privileges. Directory reader can read directory records, cannot insert them or write sessions/notices. Shelter role can read its tables/write sessions and notices, cannot modify administrator accounts. | READY |
| Saved rainfall model | `backend/models/rainfall_logistic_v1/{model.json,metadata.json}` exist, load and validate; model SHA-256 `f3fa9b53d7047746f9d26cba8556705fb3fd2328128a236cb4f423575acf4316`. Only exact Kundapur/Mangaluru points are supported. No training needed. | READY |
| Historical GIS | `data/processed/udupi_flood_spatial_v1/` loads and validates all required assets; events 2728/3551 retain 33/23 cells. | READY |
| Drainage GIS | `data/processed/udupi_drainage_gis_v1/` loads and validates retained source/derived TIFFs, PNGs, geometry and metadata. Elevation/slope/land-cover available. | READY |
| Browser/API configuration | Vite proxies `/api` using `FLOODPULSE_API_TARGET`; launcher sets actual backend target. Local origin is `http://127.0.0.1:14180`, insecure cookie allowed only for loopback HTTP. | READY |

Backend/frontend ports were **not listening** at audit time. This is a stopped
session, not a missing installation. Neither service was started here. Real
weather/model/browser demonstrations are recorded in prior progress-log entries;
they were not repeated as part of this read-only audit. Open-Meteo, map tiles and
external directions still require suitable connectivity at the venue.

## 2. Missing manual actions, in priority order

### P0 — Remove credential-shaped text from the tracked template

**ACTION_REQUIRED; approximately 5–15 minutes.** A preexisting local change to
the commented `TELEGRAM_BOT_TOKEN` line in **`backend/.env.example`** contains
token-shaped text. It was detected without showing the value. It is not active
environment configuration and the application does not load it. Whether this is
a valid token was not tested; no leak to Git history or recipients is asserted.

Privately edit only that line back to its committed placeholder. Keep any real
credential in private backend configuration, never in a tracked example, a
screenshot, shell command/history or support message. Do not display the current
diff/file contents while cleaning it up, and do not stage this unrelated edit.
If it is genuine and may have been exposed, revoke/replace it through BotFather
before use. Telegram documents secure token handling and replacement in its
[tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token) and
[authentication-token instructions](https://core.telegram.org/bots/features#generating-an-authentication-token)
(reviewed 10 October 2026). No token rotation was performed here.

### P1 — Decide and provision the administrator demonstration

**ACTION_REQUIRED for admin interaction; approximately 15–30 minutes for a
designated account, or 45–90 minutes for an isolated shelter demonstration.**
Read-only SQL found **zero administrators, zero active administrators, zero
shelters and zero notification records**. The login page can be shown, but no
existing account can authenticate. No password reset is required; no account
exists to reset.

Choose the intended demonstration mode before provisioning:

- Genuine designated administrator, empty live directory: use the current
  database, leave shelter listings empty unless independently authorized and
  verified. A working admin account does not establish genuine shelter availability.
- Full create/Open/Full/Closed demonstration with invented development fixtures:
  follow [Safe administrator demonstration](RELEASE_DEMONSTRATION.md#safe-administrator-demonstration)
  in a **separate disposable database**, with `SHELTER_DIRECTORY_MODE=demonstration`
  and visibly labelled records. Never seed this live database from old maps/OSM.

The existing provisioning utility accepts **only an explicitly supplied private
maintenance `LOCATION_DIRECTORY_ADMIN_URL`**, not the launcher reader/service
profile. Local maintenance password-file metadata exists and is owner-only;
its contents were not inspected. An authorized operator must arrange the
maintenance connection privately. It must never be inherited by the public API.
Do not rerun ready migrations/imports on this laptop just to create an account.
Once the intended maintenance environment/database is configured:

```bash
cd /home/pioneer/Projects/FloodPrediction/backend
.venv/bin/python -B -m app.provision_shelter_admin --username YOUR_ADMIN_USERNAME
```

The existing command prompts twice without echo for a 16–128-character password,
stores salted scrypt hashes and creates no public registration. Do not put a
password on the command line. Replace `YOUR_ADMIN_USERNAME` with a 3–64-character
identifier beginning with a lowercase letter, using lowercase letters, digits,
periods, underscores or hyphens. `--reset-password` is only for a deliberately
authorized later rotation, and revokes existing sessions.

**Isolated-database caveat:** `start.sh` validates the database name
`floodpulse_directory`; it will reject a differently named demo database. Use
the release guide's [two-server alternative](RELEASE_DEMONSTRATION.md#start-the-production-build-locally-alternative)
with both private database URLs pointing to the disposable demo database. The
launcher profile does not automatically configure those manual commands. Do not
weaken the launcher guard or mix operational and demonstration records.

### P2 — Start and rehearse the intended presentation session

**ACTION_REQUIRED; approximately 15–30 minutes including venue connectivity.**
Current citizen setup needs no package installation, migration, directory import,
new credentials or model training. Use the already configured normal terminal:

```bash
cd /home/pioneer/Projects/FloodPrediction
./start.sh --check
./start.sh
```

No prior venv activation is necessary. `--check` does not start a stopped
database; normal startup can start only the existing project container. Open
`http://127.0.0.1:14180` and `/admin`; backend is `http://127.0.0.1:18050`.
Press Ctrl+C to stop owned web services and leave PostgreSQL running. Do not
change to `localhost` while the exact admin origin is configured as `127.0.0.1`.

Follow [Citizen demonstration](RELEASE_DEMONSTRATION.md#citizen-demonstration):
Kundapur then Mangaluru, seven real forecast cards, freshness and requested/grid
coordinates, actual experimental rainfall model, historical/GIS layers, empty
genuine shelter directory and mobile layout. Check internet/firewall access to
`api.open-meteo.com`, the existing OSM tile host and Google Maps if demonstrating
external directions. GPS needs browser permission; manual/map coordinates remain
available. No weather/flood reading should be replaced by a fixture during the
genuine demonstration. The AI is low-precision experimental rainfall classification,
not flood probability, official warning or a statewide model.

## 3. Optional real Telegram testing

**OPTIONAL; approximately 20–45 minutes after account/private-chat access. Live
delivery is BLOCKED until configuration, permission and explicit approval exist.**
Neither `TELEGRAM_BOT_TOKEN` nor `TELEGRAM_DESTINATIONS` is in the inspected
runtime environment; the launcher profile configures only database connections.
The edited commented template does not activate Telegram. No private destination
or successful real delivery is verified.

Follow the existing [README Telegram procedure](../README.md#administrator-approved-telegram-notifications)
and [release Telegram procedure](RELEASE_DEMONSTRATION.md#telegram):

1. Resolve P0; obtain a legitimate bot from BotFather and arrange a consenting
   private test chat. The user must contact the bot first, per the official
   [sending-message prerequisite](https://core.telegram.org/bots/tutorial#sending-messages).
2. Privately inject `TELEGRAM_BOT_TOKEN` and `TELEGRAM_DESTINATIONS` into the
   **backend process environment**. The destination JSON uses an alias, label,
   numeric chat ID and `test_only: true` for a private test; the code requires a
   positive private-chat ID for that flag. No actual values belong in this file.
   The launcher does not load Telegram credentials from JSON/.env.example/.env.
3. Restart the intended session after authorized configuration. Ensure HTTPS
   access to `api.telegram.org`; no token-bearing URL in terminal/log/APM output.
4. Authenticated admin: choose the private destination → compose a clearly
   non-emergency test → review exact preview → explicitly approve → send **once**.
5. Inspect API acceptance, database history and message in the consenting chat.
   Acceptance does not prove reading; an uncertain result must not be resent
   automatically. In demonstration mode, only designated test destinations are allowed.

No CLI bypass/send procedure is recommended. No ML-triggered alert or evacuation
order is enabled. Skipping this optional live test does not prevent the citizen
weather/model/GIS demonstration; describe Telegram as implemented but unverified live.

## 4. Second presentation laptop

**ACTION_REQUIRED only if a second laptop is used; estimate 2–4 hours after
hardware, permissions and source-access approval. It was not inspected.**

1. Use a compatible Linux environment with Bash, Docker access, `flock`, `setsid`,
   `timeout`, `curl`, Python 3.12+ and supported Node/npm. Windows/macOS direct
   launcher compatibility is not established. Follow existing README install
   procedures; do not copy virtual environments or node_modules across machines.
2. Obtain the intended Git revision. The trained model and directory v2 are
   committed; copy no credential-bearing template edit. Install existing packages:

   ```bash
   python3 -m venv backend/.venv
   backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
   cd frontend
   npm ci
   ```

   These are future setup commands, **not executed by this audit**.
3. Provision an independent persistent PostgreSQL/PostGIS database and least-
   privilege roles using [README database setup](../README.md#postgresqlpostgis-location-directory)
   and [shelter grants](../README.md#administrator-controlled-emergency-shelters),
   including notification-table grants. For **start.sh compatibility**, its
   contract is container `floodpulse-sprint6-db`, `127.0.0.1:55436`, database
   `floodpulse_directory`. The README's generic new-instance example uses another
   name/port: an authorized operator must adapt those explicitly on the new
   laptop, or choose the documented manual server startup. Never recreate/reset
   this laptop's volume or reuse another application's database.
4. Privately supply separate reader/service connections and legitimate owner-only
   credential files. Rebuild the ignored reference profile for that laptop;
   copying Git does not transfer it. Do not clone an administrator password or
   operational database just to create test accounts.
5. For the **new** database only, enable PostGIS and apply the existing maintenance
   workflow after privately configuring its maintenance URL:

   ```bash
   # From the repository root, intended new database only:
   backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
   cd backend
   .venv/bin/python -B -m app.import_locations
   # Provision the chosen authorized admin only if needed (P1).
   ```

6. Retain exact permitted GIS assets through approved private transfer. Required
   directories are `data/processed/udupi_flood_spatial_v1/` and
   `data/processed/udupi_drainage_gis_v1/`, including their matching manifests.
   Their total local footprint is **383,986 bytes**. The two historical TIFFs and
   five drainage/source TIFFs are ignored by Git but are required even when the
   UI displays committed GeoJSON/PNG: loaders validate every original file.
   Do not regenerate/re-extract them. SOI originals or statewide research archives
   are not necessary for the application demonstration and must not be distributed.
7. Preserve `backend/models/rainfall_logistic_v1/{model.json,metadata.json}`
   (**8,387 bytes** together); no raw training sources or retraining are required
   for inference. Offline full training-data reproduction additionally requires
   retained local sources and is a separate optional task.
8. Confirm the above permissions/licences, `./start.sh --check`, then rehearse P2.
   Backup/restore, if chosen instead of a clean directory import, must use the
   release guide's trusted-backup/isolated-restore procedure and least-privilege
   reprovisioning. No safe wholesale archive-copy shortcut is assumed.

## 5. Actual public deployment — separate approval and engineering gate

**BLOCKED as a public emergency service; not required for a college demo.**
Allow several development/operations days plus unknown permission/validation
lead time; no reliable total estimate exists yet. The local prototype does not
provide a ready public-deployment procedure.

- Select a reviewed host/domain/TLS and a production static server for
  `frontend/dist`, with a same-origin `/api` reverse proxy and managed FastAPI
  process. `start.sh` is loopback development; neither Vite dev nor preview is
  the public production server. [Official Vite deployment guidance](https://vite.dev/guide/static-deploy.html)
  confirms preview is for local inspection (reviewed 10 October 2026).
- Configure exact HTTPS `SHELTER_PUBLIC_ORIGIN`, `SHELTER_COOKIE_SECURE=true`,
  genuine `SHELTER_DIRECTORY_MODE=live`, production secret management, TLS,
  frame-denial/nosniff/referrer headers, restricted database network and least-
  privilege roles. Maintenance connections stay outside API processes. Review
  trusted-proxy/login-limit behavior; do not claim it is solved by HTTPS alone.
- Review patched compatible PostgreSQL/PostGIS dependencies/images, backup/restore,
  monitoring, secret redaction and authorized admin lifecycle. The current
  locally verified 16.4/3.4.3 versions are not a security-patch recommendation.
- Confirm per-source redistribution/deployment rights. Retain OSM/geoBoundaries,
  Copernicus/ESA attribution and GFD **CC BY-NC 4.0** conditions; do not publish
  restricted SOI geometry/withheld derivatives. Open-Meteo free access is subject
  to non-commercial use and rate limits under its [current terms](https://open-meteo.com/en/terms)
  (reviewed 10 October 2026); a commercial/higher-volume source plan and application
  endpoint configuration may require separate work. Public does not necessarily
  mean commercial, and a paid weather API would not remove other source restrictions.
- Independently authorize and verify real shelter facilities, exact entrances,
  usability/capacity and publication-approved contacts before Open. No records
  currently exist; authorization cannot be inferred from an OSM building or map.
- Obtain responsible operator approval, message policy and legitimate Telegram
  destinations. Preserve explicit preview/approval/audit, no automatic ML alerts.
- Keep flood prediction unavailable and rainfall-model limitations visible. The
  current two-point, low-precision model is not validated for public emergency
  decisions. Actual warning-service claims require separate scientific and
  organizational validation; configuration alone cannot resolve that blocker.

## 6. Final readiness matrix

| Capability / requirement | Status | Unresolved manual action |
| --- | --- | --- |
| Existing dependencies, local database/schema and directory | READY | None; do not repeat installation/migration/import on this laptop. |
| Local private connection references and service authentication | READY | None for current laptop; a clone needs private setup. |
| Saved model and retained GIS | READY | None locally; approved exact-asset transfer for another laptop. |
| Token-shaped text in tracked local example | ACTION_REQUIRED | Privately remove it; assess/revoke any genuinely exposed token before use. |
| Citizen presentation session | ACTION_REQUIRED | Start/rehearse at venue; services are currently stopped, internet not venue-tested. |
| Administrator interactive demonstration | ACTION_REQUIRED | Authorized private provisioning; decide genuine empty-live versus isolated demo DB. |
| Genuine public Open shelter destinations | BLOCKED | Actual facility authorization/entrance/usability/capacity evidence; can remain empty for college demo. |
| Live private Telegram demonstration | OPTIONAL | Configure consenting private test and admin; delivery remains blocked pending those actions. |
| Second laptop | ACTION_REQUIRED if used | Local dependencies/database/roles/private profile and exact permitted GIS transfer. |
| Public hosting/secure operations | BLOCKED | Separate production configuration, review, privileges/licences and operator approval. |
| Validated flood prediction / emergency use of AI | BLOCKED | Scientific/operational validation; never substitute the rainfall model or invented thresholds. |

The local citizen demonstration can proceed after P0/P2; interactive admin use
additionally requires P1. Live Telegram, real operational shelters, a second
laptop and public deployment are conditional expansions, not hidden prerequisites.
