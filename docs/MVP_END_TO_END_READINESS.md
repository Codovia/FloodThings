# FloodPulse MVP operational readiness — 13 October 2026

Target demonstration: **16 October 2026**. Emergency response remains the USP; the Phase 12G flood-model training NO-GO remains in force. CWC is not an application-development dependency.

## Database readiness

The persistent local development database `floodpulse_directory` on `127.0.0.1:55436` runs PostgreSQL **16.4**, PostGIS **3.4.3**. It was initially at `0003_admin_notifications`. Migrations `0004` and `0005` were inspected and tested without changing their source files. New additive `0006_report_position_provenance` records manual versus browser GPS location provenance separately; legacy report provenance is not invented.

Before the development upgrade, a full custom-format database backup and private roles backup were taken. The database archive was inspected, restored into isolated PostgreSQL/PostGIS, and upgraded successively through `0004`, `0005`, `0006`. Ten restored existing tables retained their complete row fingerprints. The maintenance operation then applied only a forward upgrade and finite grants to the existing restricted application role in development. All **11 existing development tables** retained their count/content fingerprints, and all role/password hashes were unchanged. No persistent downgrade, reset, demo seeding or account creation occurred.

The verified private backup is `data/tmp/mvp_readiness_backup_20261013_59f4306a9f/development_database.dump` (53,027 bytes, SHA-256 `67efe2468575f581ab4f5e624c0e063c975ce94db19020f518f6a7fba81dc06a`). The sibling `roles.sql` contains sensitive role material and is owner-readable only; neither belongs in Git. Restore proof and operation receipts remain under `/tmp/floodpulse-readiness-{backup,forward}-result.json` and the ignored backup folder.

The development revision is now `0006_report_position_provenance`. Required privileges on **14 application tables** passed. Audit UPDATE/DELETE remain denied; administrator UPDATE and shelter DELETE are not granted. Location directory access retains its separate read-only role. `start.sh` now checks reporting/subscription tables, provenance tables and required service grants before startup; it does not migrate or seed automatically. `python -m app.mvp_database` performs a read-only service check. Explicit maintenance-only `--grant-to EXISTING_ROLE` supplies the finite grants, creating no account/password.

At verification: **zero active administrators, zero shelters, zero citizen reports** in development. This is an operational setup dependency, not a failed migration.

## Working application features

- Home accepts appropriately attributed automatic or manually selected locations, loads source-timestamped local Open-Meteo model weather, and displays Local Conditions & Flood Outlook. Earlier live Chrome geolocation timed out; BigDataCloud subsequently supplied an explicitly approximate IP-estimated Mysuru point, not verified device-town identity. See [the prior live-location evidence](MVP_EXECUTION_2026_10_13.md). Native GPS reliability remains device/browser dependent.
- Citizen reporting accepts fresh browser GPS **or an explicit manual incident point**. Manual submission requires the user's estimated uncertainty radius; it does not invent GPS accuracy or a GPS acquisition timestamp. Description, observed/received clocks, position source, photo references/hashes and consent are stored transactionally. JPEG/PNG decoding, size/type checks and optional consented EXIF extraction remain in place. Metadata extraction is not image-content analysis; the vision model remains unavailable.
- Evidence is private and SUBMITTED until authenticated moderation. Session/CSRF, revision conflict checks, reasons, audit trails, restricted sanitized photos, withdrawal and retention remain enforced. Demo retention cannot delete live-mode rows. Approval means reviewed citizen evidence, not official flood ground truth.
- Administrators can inspect evidence/location, start review and approve/reject. The approved evidence preview now supports downloading authenticated JSON with provenance. `training_eligible` stays false, `label_eligibility` stays NOT_ASSESSED, environmental snapshots remain not_captured, and private-review image consent does not authorize model training. Export remains restricted; research eligibility needs separate consent/licence/scientific review.
- Shelter administration preserves Pending creation, deliberate entrance selection, four verification confirmations, capacity/occupancy, audit and 24-hour expiry. Only eligible Open destinations are public. Demo environments show a persistent DEMO ONLY header badge and record-level disclaimers.
- Directions require an adequate explicitly selected origin or fresh precise GPS. Network estimates and stale/imprecise fixes cannot produce a directions link. Destination availability is rechecked and the resulting link expires after five seconds. General external directions remain **not verified flood-safe**.
- Saved `rainfall_logistic_v1` inference remains restricted to the exact supported Kundapur/Mangaluru points. UI title: **Experimental Heavy-Rainfall Indicator**. ERA5 proxy/live-input parity, retrospective metrics and no official-warning/flood-probability claims remain visible. No fitting, statewide model or flood-risk probability was introduced.

## Browser evidence and validation

The reproducible runner `scripts/verify_mvp_e2e.py` creates only a UUID-named disposable database, imports the genuine reviewed directory, provisions an administrator with a random ephemeral password, and gives the API restricted reader/application connections. The API does not receive maintenance credentials; Vite receives no database/test passwords. Telegram settings are removed from the runner environment, so verification cannot send messages.

Run with an explicitly supplied private `LOCATION_DIRECTORY_ADMIN_URL`:

```sh
backend/.venv/bin/python -B scripts/verify_mvp_e2e.py
```

It uses loopback ports 18040/14173 and cleans up only its own database/roles. No fixture shelter is imported into development. Screenshots and local evidence files are under `/tmp/floodpulse-mvp-readiness`; credentials are never captured.

The combined real-browser journey passed in 13.2 seconds; the separate GPS/photo/moderation/withdrawal journey passed in 4.1 seconds. Actual HTTP requests and PostGIS transactions use restricted roles, a genuinely provisioned isolated administrator, opaque sessions, CSRF and real decoded image bytes. The main journey has **no API/provider mocks**: it uses an explicitly chosen manual point, an owned 2×2 PNG and conspicuously labelled fictitious shelter authorization/capacity. OSM tiles and Open-Meteo are live. The separate GPS test injects a controlled browser GPS fix; this does not prove native device GPS/camera hardware availability.

The joined journey verified: manual point+photo submission; anonymous photo access denied401; authenticated photo retrieval200; moderation without CSRF denied403; UNDER_REVIEW→APPROVED with audit reason; authenticated JSON download with position provenance and training_eligible=false; deliberate map click supplying entrance coordinates; Pending excluded from public view; Open included only after four renewed confirmations; directions encode the explicit origin and exact selected entrance after availability recheck; Closed immediately disappears on public refresh. No live Telegram configuration means disabled composition and no send. The export retained the approved incident independently of closing the demo shelter.

Live selected Kundapur weather and saved experimental inference both returned **HTTP200**. Screenshots show actual rendered application pages, including Home's **1366×768 document/viewport with no page overflow** and persistent demo identity. No browser page errors were recorded. The model artifact hash remains `f3fa9b53d7047746f9d26cba8556705fb3fd2328128a236cb4f423575acf4316`; inference used live hourly inputs, not fitted weights or invented probabilities.

| Artifact under `/tmp/floodpulse-mvp-readiness` | Evidence |
| --- | --- |
| `01-home.png`, `weather.json` | Live selected-point Home weather, local conditions, exact desktop layout |
| `02-experimental-indicator.png`, `indicator.json` | Saved, scope-limited rainfall inference using live inputs |
| `03-private-submission.png` | Explicit manual point+owned image, private receipt |
| `04-admin-moderation.png`, `reviewed-evidence.json` | Real moderation/audit and restricted provenance export |
| `05-admin-shelter.png` | Map-selected entrance, isolated demo shelter management |
| `06-shelter-directions.png`, `browser-results.json` | Verified Open directory and exact origin/entrance navigation contract |
| `07-telegram-unconfigured.png`, `08-alert-subscriptions.png` | Honest unavailable send/subscription states; no delivery claim |
| `09-external-google-maps.png`, `external-route.json` | Live Google walking directions for fixture points, provider attribution |

These local screenshot/export artifacts contain isolated private fixture evidence and stay out of Git. The Google screenshot is provider UI with attribution; it never certifies a real shelter or flood-safe road.

Complete frontend: **275 passed**; backend: **1,443 passed**, **one actual model-fitting reproduction deliberately deselected**; production build and `bash -n start.sh` passed. The original full PostGIS run had64passes plus one stale hardcoded migration-head assertion; replacing it with the actual Alembic head made all19location tests pass. Final manual/provenance/grants/retention tests12passed; **complete PostgreSQL/PostGIS suite65passed**. The initial full browser regression had74passes/7failures: obsolete Home text/reload expectations and fixture-origin/district/editor selectors were corrected while retaining all security, freshness, unavailable-state and layout assertions. All25tests in the five affected files then passed. **Final complete Playwright suite81passed in2.4minutes**, including the real joined journey and controlled-GPS browser-to-PostGIS workflow. The full suite uses clearly identified API/weather/Telegram fixtures in regression tests; its integrated main journey uses live weather/inference and actual restricted-role persistence. Telegram provider responses in local tests are mocked, never actual delivery receipts. Existing Starlette/httpx deprecation and Vite's >500kB bundle advisory remain.

Protected baseline verification found **zero changes** across78 SHA-256/size/mtime-tracked data/model/original-migration/design/unrelated files, and **zero changes** across3,849 existing data files' size/mtime records (launcher runtime logs excluded). This distinguishes hashed coverage from metadata-only coverage. The pre-existing update.md prefix remains byte-for-byte preserved; progress is append-only. Private backups are new ignored files; no original archives were rewritten. Unrelated `backend/.env.example` and `QandA.md` remain untouched/uncommitted.

## External dependencies and exact remaining blockers

1. **Persistent administrator:** none is provisioned. A designated staff member must choose a private password (16–128 characters) and run the existing interactive `python -m app.provision_shelter_admin --username CHOSEN_USERNAME` using an explicitly configured maintenance connection. There is no default password/public registration. Disposable browser-test provisioning does not create an operational account.
2. **Real shelters:** no genuine facility authorization, entrance verification, usability or capacity has been supplied. Development/public availability remains zero. Demo fixtures cannot establish real emergency destinations.
3. **Telegram live send:** no `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DESTINATIONS`, `TELEGRAM_WEBHOOK_SECRET` or `TELEGRAM_BOT_USERNAME` is configured. A real bot, explicitly authorized private test destination, HTTPS webhook and that single recipient's `/start floodpulse` opt-in are required. The administrator must preview exact content and explicitly approve before sending. `/stop` withdraws consent; delivery is rechecked and recorded. Local mocked provider tests establish behavior, not delivery. No live message was sent or recipient reading confirmed.
4. **Routing:** `OPENROUTESERVICE_API_KEY` is absent; no in-app road geometry/provider service is configured. Google Maps external directions encode the selected origin and freshly verified entrance. A separate live headless Chrome check opened this exact directions URL: Google Maps returned HTTP200, route geometry and walking directions of 450m/6minutes via Kundapura Main Rd between the selected public locality and isolated fixture entrance. Google resolved its own nearby building labels; those labels confer no shelter authorization. No device GPS permission was granted. This is genuine external-provider route output, not in-app route geometry or an access/safety assessment. Authoritative current hazards, road closures and access evidence are absent; route safety cannot be certified.
5. **Optional imagery:** authorized MapTiler satellite/hybrid/building search configuration is absent; actual street-map/manual entrance tools work. No image analysis/classification/depth estimation is implemented.
6. **Research:** export collects provenance-aware citizen evidence only. Separate research rights, privacy review, environmental issue-time joins and scientific label eligibility remain required. No training starts automatically; the existing research NO-GO is unchanged.

The integrated demo can prove application/database behavior with conspicuously labelled isolated fixtures. Full operational acceptance still requires real administrator provisioning, genuinely authorized shelters and a configured, consenting Telegram recipient; these cannot be fabricated.

## Verified delivery

Database slice `9aab89cfd23a6f5486c9ede25561d20fca9e0c72` and citizen-evidence slice `83b79ed4a66c6b0cd04cd346054eb61a389ca3f2` were each pushed to `git@github.com:Codovia/FloodThings.git`, branch `feature/karnataka-data-foundation`, then separately compared with an independent `git ls-remote` query. Both matched exactly. The final integration/documentation commit hash is reported after publication outside this document to avoid a self-referential hash.
