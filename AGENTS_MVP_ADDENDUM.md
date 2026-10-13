# FloodPulse Codex Agent Priority Addendum — 2026-10-13

**Read `docs/FLOODPULSE_MVP_PRIORITIES.md` before any further work.** This is a newer user-approved priority/scope decision. Follow existing root `AGENTS.md`, security/data integrity rules and specifications in all nonconflicting matters. If existing instructions conflict, surface and reconcile the conflict; do not silently remove safety controls.

## Core priority

The USP is **emergency alerts + verified shelter map/directions + admin map management + citizen GPS/camera incident reporting + admin moderation + provenance-aware future training dataset**. Flood prediction is a **small experimental supporting feature**, not a deadline blocker. Target working MVP by **2026-10-16**.

### Immediate work

1. Fix the Sprint13 automatic location regression (unnecessarily mandatory manual selection, disabled geocoder, repetitive Home summary). Use honest accuracy-aware town naming, actual weather, clean 16:9 Home UI.
2. Audit and finish admin shelter management and citizen map/directions; never claim a public route is flood-safe without independently verified hazards/closures.
3. Deliver human-approved Telegram alert preview/send/receipts and one real subscribed-user test where configured.
4. Build GPS + camera/gallery citizen report -> database -> admin approve/reject pinned on map -> optional genuine image attribute extraction -> versioned evidence/dataset rows.
5. Include minimal research-only experimental rainfall/river indicator using real model data; no fabricated training labels or automatic public warnings.

### Rules

- No fake environmental, shelter, geographic or training data in production.
- No raw citizen reports auto-labelled as true; no unsupported image-derived flood depth or risk.
- No automated evacuation safety assurance from generic routing.
- Keep Phase12G validated flood-model training NO-GO and CWC response pending, but **do not block MVP implementation on it**.
- Focus on small vertical slices and measurable end-to-end demonstrations, not more exploratory studies or multi-week refactors.
- Preserve unrelated files, avoid credentials in commits, keep independent audit and test reports.

At start of each Codex task, state which P0/P1/P2 slice it advances and its acceptance test. At end, give tested behavior, known blockers, live vs fixture-based proof, remaining deliverables and commit hash if pushed.
