# Citizen GPS/photo reporting — private MVP slice

Decision: [13 October emergency MVP](FLOODPULSE_MVP_PRIORITIES.md) authorizes implementation of the formerly documentation-only [reporting sketch](design/floodpulse_wireframes/05_experimental_report_flood.jpg). This supersedes that earlier document's instruction to wait for workflow approval. Existing security and scientific data integrity rules remain.

## Working path

Home → **Report an incident** (`/report`) → explicit **Use GPS for this report** → event type/description/device-local observed time → optional camera/gallery photo → private-review consent → review → submit. GPS and camera are separate user actions; no network city estimate or weather point is silently used as report GPS. Missing GPS blocks submission honestly. Photos are optional. Receipts give a UUID and USER_REPORTED/SUBMITTED state. No emergency dispatch, public feed, Telegram send or ML label is implied.

Authenticated Admin → **Citizen reports** → select a list item or map pin → inspect actual image format/dimensions/hash and consented EXIF → enter review reasons → **Start review** → **Approve as reviewed citizen evidence** / **Reject report**. The state path is SUBMITTED → UNDER_REVIEW → APPROVED/REJECTED; revision checks reject stale/concurrent moderation. Private photo access requires the existing opaque admin session. Each preview access and state transition records an audit event; submit and audit writes are transactional.

**Inspect approved evidence export** returns bounded, authenticated JSON with source, observed/server-received time, GPS uncertainty, photo hash/metadata, consent version and review provenance. APPROVED remains a reviewed citizen claim. `training_eligible=false`, `label_eligibility=NOT_ASSESSED`, no negative labels, no official warnings. Environmental feature/issue-time snapshots are not captured yet; the export states that explicitly. No trained or pretrained image model is installed and no water depth/road closure/risk is invented. Later dataset work must independently assess labels, image licences and time leakage.

## Privacy and abuse controls

Anonymous, restricted evidence only; no submitter identity/contact is collected. The citizen confirms rights for private photo review. Only JPEG/PNG is accepted, with a 5 MiB decoded-size, 7 MiB JSON-body, 15-second upload and ten-megapixel/single-frame limit. Actual image decoding/MIME matching rejects corrupt files, SVG, animation and spoofed content. At most two image decodes run concurrently. A generated UUID replaces filenames; raw original names are not stored.

A new JPEG preview strips EXIF/GPS/text/device metadata. Original bytes and extracted EXIF are retained only with the separate metadata consent; otherwise only the sanitized preview, decoded attributes and original input cryptographic hash remain. EXIF is user-supplied metadata, not independently verified location/time. Missing EXIF stays missing; timezone-less capture timestamps are flagged, never guessed. Supported EXIF GPS/time discrepancies create flags, not labels. No public photo is served; unblurred previews remain admin-only and are not approved for publication.

Application retention policy: photos become inaccessible after seven days; private descriptions/GPS/EXIF are hidden from admin responses after 30 days. **Apply expired-evidence retention** physically removes expired photos and erases expired private text/position/metadata, retaining status/source/hash/reviewer/reason audits. Configure the operator's regular purge procedure before accepting actual reports; no background scheduler is invented. Reasons must omit personal identifiers. The citizen can **Withdraw private evidence** using a random per-submission secret kept only in page memory; it erases the photo and precise location/text while retaining the status audit. Reload loses that key; administrator-assisted withdrawal after key loss and a permanent self-service recovery flow remain dependencies.

Submission UUIDs are idempotent only for unchanged content. Client retries reuse the original UUID/key; changed content with the same UUID is rejected. The server stores only the withdrawal key's hash. Same-origin checks/custom JSON header, bounded rate buckets (five per peer/15 minutes, sixty application-wide), no-store responses and redacted validation errors apply. Peer keys use an in-memory HMAC salt; global rate limiting remains shared across workers, but peer-specific buckets reset on process restart. Production ingress/distributed peer-rate policy still requires deployment review.

## Setup and dependency boundaries

Use existing provisioned admin, `SHELTER_DATABASE_URL`, `SHELTER_PUBLIC_ORIGIN` and HTTPS cookie/CSRF configuration. There are no default passwords. Install the pinned `Pillow==12.3.0` dependency from backend/requirements.txt. Apply additive Alembic revision `0004_citizen_reports` through the already documented **maintenance** connection, after database backup/review. This execution migrated disposable test databases only; it did not migrate the operational database or change the user's environment file.

Give the separately provisioned application role only these additional table permissions in the intended database (substitute its actual role name):

```sql
GRANT SELECT, INSERT, UPDATE ON citizen_reports TO floodpulse_shelter_app;
GRANT SELECT, INSERT, DELETE ON citizen_report_images TO floodpulse_shelter_app;
GRANT SELECT, INSERT ON citizen_report_audit TO floodpulse_shelter_app;
```

Existing session/login-limit grants remain necessary. The role must not own tables or update/delete audit history. PostGIS POINT uses longitude as X, latitude as Y, checked against numeric fields. There are separate GIST/receipt/expiry indexes. Demonstration and live records are filtered separately; test fixtures are not operational events. Public report lists/images are absent by design until a separate minimized-publication workflow is explicitly built.

## Verification

Actual disposable PostGIS tests cover submit/photo privacy/moderation/export/audit, geometry order, duplicate retries/conflicts, origin/CSRF, withdrawal, rejection, photo expiry, physical retention, image spoof rejection and persistent rate limits. An actual browser→HTTP→disposable PostGIS→authenticated admin flow submits a labelled generated image and fixture GPS, approves evidence, verifies no training label and withdraws the record. All external browser traffic is blocked in this end-to-end test; it is real persistence/authentication with synthetic isolated input, not live citizen proof. Desktop and mobile screenshots are under /tmp/floodpulse-citizen-report-*.png and /tmp/floodpulse-admin-report-desktop.png.

Image implementation references checked on 13 October 2026: [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html), [Pillow package](https://pypi.org/project/Pillow/). No antivirus, face-blurring or model inference capability is claimed. The private-only scope avoids public image publication pending those controls.
