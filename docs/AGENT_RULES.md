# AGENT_RULES.md

**Project:** FloodPulse
**Status:** Active. These rules apply to every agent session (human or AI) working on FloodPulse. They are not optional.

---

## 1. Required reading order — every session

Before touching any code, read in this order:

1. `docs/HANDOVER.md` — current state and next task
2. `docs/CONSTRAINTS.md` — non-negotiable rules
3. `docs/ARCHITECTURE.md` — system design
4. The domain spec relevant to today's task (`DATA_SOURCES.md`, `GIS_SPEC.md`, `ML_SPEC.md`, `API_SPEC.md`, etc.)

Do not start implementation before doing this, even if the task seems obvious.

---

## 2. Before coding

- Inspect the repository state (`git status`, relevant files).
- Inspect the current state of files you intend to modify.
- Understand the existing architecture and conventions.
- Identify your assumptions — and verify them.
- Read the task specification completely before starting.

---

## 3. The work cycle

```
INSPECT     — look at current repo state before changing anything
PLAN        — state what you're about to do and why (3–5 lines)
IMPLEMENT   — one logical change only
TEST        — run the relevant tests, not just "it compiles"
INSPECT DIFF — read the actual diff before calling it done
UPDATE DOCS — update any spec/doc this change affects
UPDATE HANDOVER — append to docs/HANDOVER.md if the project state changed
COMMIT      — one commit per logical change, clear message
```

---

## 4. While coding

- Make one logical change at a time.
- Do not fabricate environmental data — not even for testing convenience.
- Do not invent APIs or assume endpoints exist without verification.
- Do not silently change architecture or introduce new technologies.
- Do not introduce unnecessary dependencies not listed in ARCHITECTURE.md.
- Preserve data provenance at every step.
- Write tests for meaningful behavior.
- Update documentation when decisions change.
- Do not make unrelated changes in the same commit.

---

## 5. When uncertain

```
STOP
REPORT    — say exactly what's missing and what you tried
DO NOT INVENT
```

This applies especially to:
- Environmental/weather/hydrology data
- API response shapes
- Coordinates and geographic data
- Historical flood records
- Shelter locations and occupancy numbers

Fabricated data in any of these categories is the single failure mode this process exists to prevent.

---

## 6. Scope discipline

- One agent mission = one logical unit of work.
- Do not implement features from a later phase because they seem easy or related.
- If you notice a good idea for later, write it in `docs/DECISIONS.md` under a new entry rather than building it.
- Never introduce a new technology, library, or service not listed in `docs/ARCHITECTURE.md` without it being logged as a decision first.

---

## 7. Data integrity rules

- Missing data is `NULL`, never `0`, never a median/mean fallback, never a plausible-looking placeholder.
- Every stored value that isn't a raw sensor/API reading must be tagged with its classification (REAL, DERIVED_FROM_REAL, MODEL_OUTPUT, USER_REPORTED, UNKNOWN).
- Official warnings and AI predictions are never merged or displayed as the same thing.

---

## 8. Before finishing

- Run relevant tests.
- Inspect your Git diff (`git diff --stat`, `git diff`).
- Verify no secrets were introduced.
- Verify no generated/fabricated data was accidentally created or tracked.
- Summarize what you changed and why.
- Report any limitations or things you could not verify.
- Stop at the assigned task boundary.

---

## 9. Hard stop rule

```
An agent must never continue into the next phase without a new task assignment.
```

When the current task is complete:
1. Report results.
2. Stop.
3. Wait for the next task.

Do not assume what comes next. Do not "helpfully" start the next phase.

---

## 10. Commit messages

Use clear, descriptive commit messages:

```
<type>(<scope>): <description>

Examples:
feat(backend): add health check endpoints
fix(gis): correct CRS mismatch in district boundary import
docs(decisions): record D-010 routing service selection
chore(deps): pin fastapi to 0.115.5
test(ml): add temporal leakage detection test
```
