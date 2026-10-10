# Experimental flood reporting — design only

Reference: [original sketch 05](design/floodpulse_wireframes/05_experimental_report_flood.jpg). No public submission route, photo upload, operational report or training label is introduced by this sprint.

The future screen offers a district/locality search, an opt-in GPS button, a map for adjusting the reported point, a photo/camera control and a review step. GPS must require explicit browser permission and record accuracy, acquisition time and whether the reporter manually adjusted the point. A building centre is not a verified entrance. An unknown district remains unknown; restricted geography is not used to infer identity.

## Proposed pipeline

1. Obtain purpose-specific consent explaining publication, retention, contact use and withdrawal. Request location and camera separately; declining either must not silently acquire it. Do not imply emergency dispatch or guaranteed response.
2. Accept a bounded image upload into private quarantine. Validate actual decoded image type and dimensions, reject dangerous formats, scan and re-encode, strip EXIF/GPS/device identifiers and blur identifiable people/vehicles where required. Preserve only consented, necessary original evidence privately, with an explicit retention schedule and access audit. Never place an unreviewed upload at a public URL.
3. Store report ID, self-reported event time, submission receipt, point/accuracy/source, optional contact consent, text and private image references. Apply rate and size limits, abuse reporting and server-side validation. A submission idempotency token avoids retry duplicates; nearby/time-similar/image-hash matches create review candidates rather than automatically rejecting independent reports.
4. Mark every submission **unverified**. Separate pending, needs clarification, rejected and reviewed states. An authenticated moderator assesses location, date, image plausibility, duplicate evidence and source consistency; additional administrator verification is required before publishing any confirmed-event interpretation. Preserve the original claim and review history separately.
5. Publish only minimized, approved information at appropriate spatial precision. A reviewed community report remains a separately labelled source. It does not automatically become an official warning, shelter assignment, Telegram notification, confirmed flood label or ML training example. Any external notification still requires the existing explicit administrator preview and approval.

## Decisions required before implementation

Assign the data controller/moderator, approve consent wording and jurisdiction-specific retention/privacy rules, establish a review service level and deletion procedure, define what independent evidence permits confirmation, and decide whether anonymous reports can be accepted safely. Document access controls, image quarantine/scanning, moderation capacity, emergency guidance and appeal/withdrawal handling.

Acceptance tests must cover denied permissions, inaccurate GPS, timezone-less event times, upload abuse, metadata stripping, private media access, duplicate retries, concurrent moderation, audit integrity, unauthorized publication and deletion. No report may enter the public evidence feed or training pipeline by default. Approve this workflow before developing it.
