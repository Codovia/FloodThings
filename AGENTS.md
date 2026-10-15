# Repository agent instructions

Research first: never answer from memory alone on facts, current events, prices, specs, or anything that may be outdated. Verify with reliable, current sources, cross-check key claims, and note disagreements. If unverifiable, say so; never fabricate facts, sources, or statistics.

Clarify rarely: ask only when the request is truly ambiguous and a guess would be unusable, and then only one focused question; otherwise state your assumption and proceed. Be honest: correct earlier mistakes openly, flag uncertainty, and prioritize being right over agreeable. Test suggestions against the actual process and explain when they will not work.

Output: complete answer with evidence, tested behavior and limitations; end with a concise summary. Tone: calm and direct. Never trade accuracy for brevity; cut filler and repetition.

## Current product decision — 2026-10-13

Read [the MVP priorities](docs/FLOODPULSE_MVP_PRIORITIES.md), [the priority addendum](AGENTS_MVP_ADDENDUM.md), and [the implementation handoff](CODEX_START_HERE.md) before work. These supersede previous sprint sequencing; the earlier Sprint 13.1 prompt was not executed. Target demonstration: **16 October 2026**.

FloodPulse's USP is emergency response: citizen alerts, verified shelter administration and navigation, GPS/photo citizen reports, admin moderation, evidence extraction and provenance-aware future datasets. Prediction is a minimal experimental supporting feature. Do not wait for CWC's response; retain the Phase 12G validated-model training NO-GO.

Advance one small P0/P1 vertical slice at a time. State its acceptance test, implement, verify, append results to `update.md`, then commit and push only verified scoped changes. Independently verify the remote hash. Distinguish live evidence from fixtures and report concrete missing dependencies.

## Product decision — 2026-10-16 (supersedes the prediction scope above)

Read [the 4-day plan](docs/FLOODPULSE_4_DAY_PLAN.md). The project is now a **flood and drainage risk prediction and early-alert system with shelter management and navigation**; target demonstration about **19 October 2026**. Risk prediction is a major feature, delivered as a transparent rule-based risk index from real live data (IMD rainfall categories, GloFAS return levels, elevation, historical floods, approved reports), always labelled experimental and never a calibrated flood probability. The Phase 12G NO-GO on training a validated flood-occurrence model still stands. Risk output may *suggest* an alert draft; only an administrator's explicit approval sends it. Research pipeline code is archived in tag `archive/research-2026-10-16`.

## Security and data integrity

- Preserve all existing security controls, authentication, CSRF, authorization, audit history, provenance, freshness and source-validation rules. Reconcile conflicts explicitly; never silently remove controls.
- No default passwords, committed credentials, fabricated forecasts, operational shelters, geographic data, training labels, image-analysis results or delivery receipts. Isolated, labelled test fixtures are permitted.
- Generic navigation is not certified flood-safe. Show route limitations unless independent hazards, closures and access evidence support stronger claims.
- Citizen reports remain USER_REPORTED until moderation. Image suggestions are not observations or training truth. No negatives from missing reports, hindsight leakage or automatic training.
- Require explicit human review and send for Telegram alerts; model outputs never trigger public warnings. A task to implement alerting does not authorize contacting subscribers.
- Protect uploads with consent, type/size validation, generated names, restricted access and privacy-aware metadata handling. Keep sensitive uploads and research data out of Git.
- Preserve unrelated modifications, including `backend/.env.example` and `QandA.md`, original datasets, manifests, migrations and model artifacts. No destructive cleanup or recreation of removed synthetic implementations.
- Use isolated temporary test storage/databases. Never run persistence tests against configured operational data. Report actual failures and unavailable states without fallback inventions.
