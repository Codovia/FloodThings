# Codex: Adopt FloodPulse MVP Decisions and Start Next Slice

The user has **NOT run the earlier Sprint13.1 prompt**. This handoff **supersedes** that prompt, and changes the overall roadmap to an emergency-response MVP before 2026-10-16.

Local repo `/home/pioneer/Projects/FloodPrediction`, expected branch `feature/karnataka-data-foundation`, latest user-reported HEAD `b9e9452d7d6380429747d021bf344aecaa1d01bb`. Inspect actual Git state rather than assuming it.

The user has supplied two documents:

- `docs/FLOODPULSE_MVP_PRIORITIES.md` — product contract and decision log.
- `AGENTS_MVP_ADDENDUM.md` — persistent agent-priority addendum to merge into existing root `AGENTS.md` without overwriting unrelated rules (or link prominently from it).

## Task A — Adopt durable instructions before implementation

1. Review the documents and the latest actual repo state; place the project priority document under `docs/` and merge/link addendum from existing root `AGENTS.md` if present, or create root `AGENTS.md` with essential instructions and link. Never overwrite prior agent directions silently.
2. Add `docs/FLOODPULSE_MVP_PRIORITIES.md` to any existing project onboarding/decision index as appropriate.
3. Record the new priorities as an explicit 2026-10-13 user decision superseding the previous sequencing. Retain original science/quality constraints where compatible.
4. Summarize repo feature readiness and actual missing dependencies for one end-to-end demo; prioritize 2026-10-16 deadline. Do not spend hours auditing archived hydrology sources.

## Task B — First immediate implementation: fix automatic location and Home summary

- Remove blanket 100 m all-purpose GPS gate. Distinguish positioning uncertainty for city label, weather grid point, district association and river-specific flood context.
- Always attempt automatic browser location with permission and bounded time; immediately try an authorized working reverse-geocoding strategy when location evidence supports city/town. Prefer existing approved geocoder if credentials are present; otherwise use a genuinely permitted lightweight location-name source with provider-specific limits and attribution. Do not hardcode fake cities or claim that a ±280 km browser fix is a precise GPS position. Do not turn manual selection into the only ordinary path. A separate permitted approximate network city estimate, if available, must be clearly sourced as approximate.
- Fetch actual Open-Meteo weather for an accepted position/approved previous selection; preserve verified complete next-24-full-hour hourly forecast aggregation, freshness and units.
- Replace generic repetitive “Your Area Emergency Summary” with useful “Local Conditions & Flood Outlook”: location source/uncertainty, actual current weather, real rain-window description, official warning status, verified river outlook if available, otherwise a concise honest unavailable state, and links to next actions.
- Keep Home 1366x768 at 100% browser zoom, ~40/60 split, existing map, no public fake flood forecasts or shelters; keep other four pages unchanged for this slice.
- Run targeted automated tests and real Chrome at 1366x768; report actual browser location provider results separately from fixture tests. If external geocoding key is missing, document concrete setup and make existing manual selection usable, without falsely claiming live auto-naming completion.

## Task C — Immediately after Task B, deliver P0/P1 slices sequentially

Choose the thinnest real end-to-end feature slice and execute, test and commit one at a time:

1. **Shelter navigation/admin:** real admin setup, admin map pins/entrance verification/capacity/open status and public verified shelter listing. Add real routing provider where authorized, source/availability/route cautions. Never promise verified flood-safe routing without road hazard/closure evidence.
2. **Alerts:** admin-authored, reviewed and explicitly sent Telegram messages, delivery/opt-in/dedupe/audit with test-subscriber proof where credentials exist. No raw model output triggers.
3. **Public photo report:** GPS and optional camera/gallery upload with permission, description and event type -> secured backend/PostGIS record -> admin map moderation -> approve/reject -> evidence/data-ready, privacy-aware records. Add only trustworthy image metadata extraction first; optional actual pre-trained image model if runnable without disrupting P0.
4. **Minimal indicator:** separate clearly labelled research-only river/rain indicator. No training on invalid flood labels. API/UI must accurately state limits.

Preserve unrelated `backend/.env.example`, `QandA.md`, original archived data and security protections. No default passwords. Use `update.md` for progress, commit and push only after verification. Focus on working demo over additional plans.

## Report after first execution

Report the priority document/agent instruction installation; exact automatic-location failure and what is fixed/live-tested; updated Home screenshot/browser DOM metrics; per-feature readiness with concrete blocker, immediate next vertical slice; tests and Git commit/push verification. Do not claim complete alerting, route safety or flood ML until independently tested.
