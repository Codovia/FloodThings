# FloodPulse — Karnataka Flood Prediction Implementation Blueprint

**Status:** Implementation proposal + label-audit starter; NOT a trained flood model or statewide forecast.
**Repository to integrate into:** `/home/pioneer/Projects/FloodPrediction` (not available in the current execution environment).
**Reference reported HEAD:** `ca55762d25ab33f58542ff3be0c90120cfc972d4` (verify actual HEAD before working).
**Primary objective:** Predict genuine flood outcomes, not rainfall-threshold labels, and make the Karnataka-wide coverage and limitations explicit.

## 1. What is genuinely distinctive?

The fundamental technologies—ML hydrology, inundation models, flood maps, public warnings and shelter management—are not novel individually. FloodPulse's proposed contribution is a *Karnataka-focused, auditable, integrated* decision-support workflow in which:

1. Authentic flood observations are differentiated from hydrological simulations, published hazards, forecasts and community reports.
2. A model produces flood outcome forecasts only at spatial/temporal units for which its quality has been independently validated.
3. Outputs explain prediction target, horizon, observation and input provenance, coverage and uncertainty, with an explicit **not assessed** state.
4. Results are connected to human-verified operational shelters and administrator-approved notifications without misrepresenting route safety or official authority.
5. Riverine and pluvial/flash processes remain distinct research targets.

This is currently a **proposed integrated contribution**, not established algorithmic novelty or demonstrated statewide prediction skill.

## 2. Research findings and implementation implications

| System | Verified type of prediction | Implications |
|---|---|---|
| CWC FloodWatch | Station-level river flood conditions/forecasts | Monitoring locations and river state must be distinguished from district-wide outcomes. |
| Google Flood Hub / OpenHydroNet | River-discharge forecast model + separate inundation model | An LSTM discharge output does not by itself imply a flooded locality. Pretrained weights use 1982–2023 without temporal holdout; avoid in-sample testing. |
| Google flash flood model | Weather-plus-geography-based flash flood occurrence at ~20 km grid resolution | Flood targets require actual events and rigorous observation-process treatment; coarse grids are not street-level predictions. |
| Groundsource | News-derived historical flood-event positives | Regional coverage, duplicate events, date/location accuracy and licence require verification; it provides no universal verified negatives. |
| GloFAS | Modelled discharge and forecasts/reforecasts | Can provide baseline/context, not independent measured gauge labels. Match versions and issuance times. |
| NRSC / IFI / GFD | Reviewed historical flood event/satellite observation evidence | Many events have imprecise timing/geometry; GFD flood cells from one event are correlated, not independent events. |

Primary sources: https://github.com/google-research/flood-forecasting ; https://support.google.com/flood-hub/answer/16811681 ; https://zenodo.org/records/18647054 ; https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical ; https://cwc.gov.in/ .

## 3. Preserve existing FloodPulse state

- Application already has React/Leaflet, FastAPI, PostgreSQL/PostGIS, real Open-Meteo weather, experimental heavy rainfall Logistic Regression, 31 selectable district names (not 31 forecast-covered districts), five verified point localities, 56 public historical flood raster-cell polygons from two Udupi events, no verified potential-hazard polygons, shelter administration and approval-controlled Telegram.
- Existing rainfall model only predicts >=64.5 mm in the next rolling 24 hours, eligible at Kundapur and Mangaluru; its prediction must NOT be relabelled as flood occurrence.
- No reliable statewide flood-negative observations currently confirmed; historical flood record absence is not proof of no flooding.
- The 56 public flood polygons are not independent events or enough by themselves to validate a statewide flood model.

## 4. Implementation phases and exact gates

### Phase 12A — Inventory and typed flood-label evidence contracts (implement now)

1. Audit actual repo structures, manifests, IFI/GFD, GloFAS, CWC and rainfall inventories; verify licences and permissions. Do not assume the untracked `QandA.md` is correct.
2. Add versioned **candidate** label contract with: source identifier, original record, verified location and precision, spatial unit, event ID/group, observation time interval, label (`FLOOD_OBSERVED`, `NON_FLOOD_OBSERVED`, `UNKNOWN`), **actual observed coverage**, confidence/quality, adjudication/review and provenance.
3. Implement a label-audit CLI and tests that **reject missing-as-negative**, missing dates, duplicated IDs and invalid evidence. The included starter tool covers only schema checks; Codex must adapt it to actual project contracts, and not interpret its output as scientific validation.
4. Produce a coverage matrix by district, mechanism (if verified), year and label type, tracking unknown/unobserved areas. Keep review status distinct from training eligibility.
5. Investigate Groundsource dataset schema via **metadata-first inspection**, checksum and licence, then bounded Karnataka extraction only after confirming legal download and file size. 667 MB full-file download needs explicit approval if not already present; no silent large fetches.
6. Inspect GloFAS forecast vs historical/reforecast time semantics; do not merge simulated labels into observed outcomes.

**Gate A:** Evidence records are traceable and valid. A validated absence set is separately reviewed. If negatives are not defendable, label **NO-GO supervised occurrence training**; continue research pipeline only.

### Phase 12B — Define specific real flood targets and the area/time unit

Choose independently for each track:

- **Riverine:** river reach / catchment time-window high-flow / flood exceedance. For high-flow threshold labels, independent measured gauges and local threshold definitions are required. A modelled discharge baseline may be compared but not called observed flood occurrence.
- **Pluvial / flash:** verified flooded-vs-observed-nonflood within a spatial unit (e.g. sufficiently observed grid cell) in a fixed 24-hour horizon. A verified unreported day is not assumed non-flooded. For satellite labels, account for acquisition coverage and permanent water; source timestamps and observation limits matter.
- Karnataka administrative district is primarily a visualization/filtering level. A district forecast must be explicitly derived from validated prediction units, not one coordinate or an average rainfall proxy.

**Gate B:** Freeze target semantics and label-review rules before training.

### Phase 12C — Align only issue-time features

Possible antecedent rainfall (CHIRPS, ERA5), soil wetness, terrain/land cover, watershed area, upstream hydrology, reservoir state where genuinely observed, and **historically issued** meteorological forecasts when the model is intended for forecasting. Retrospective reanalysis values alone do not establish real-time forecast skill. Record forcing version, issue timestamp, temporal and spatial join and missingness. No forward-looking variables.

**Gate C:** Reproducible feature table with data leakage tests, source/units/geography, documented missingness and coverage.

### Phase 12D — Train only when A-C pass

Use simple empirical baselines first (seasonal climatology/threshold and Logistic Regression, class-weighted tree as justified), then Random Forest / gradient boosting. Compare with hydrological baselines and consider OpenHydroNet separately if independently measured flows and compatible features exist.

Hold out **entire flood events, time periods and locations/catchments** where practical. Count independent events/groups, not just correlated pixels. Publish confusion matrices, precision, recall, PR-AUC and false-alert rate; calibration and lead-time metrics only if suitable. Verify skill against simple baselines; abstain if performance/coverage is inadequate.

**Gate D:** A signed-off evaluation report establishing what type of flood is predicted, where and when. No unsupported claim of statewide accuracy.

### Phase 12E — Guarded product integration (only after D)

Build a **separate** `flood_prediction` service/route, never reuse `/api/ai/rainfall-outlook` as a flood predictor.

Every successful prediction response must include: `target`, `mechanism`, `spatial_unit_id`, `issue_time`, `valid_from`, `valid_to`, `model_version`, `forecast_value`, `unit`, `observed_validation_coverage`, `verification_status`, `source_metadata`, `limitations`. If no validated model: `status=UNAVAILABLE` and coverage reason (not `low risk`, not `0%`).

Frontend Home and Flood Map show a distinct **experimental actual-flood prediction** layer only in supported locations. Keep original historical polygons, zero verified hazard polygons and current rainfall model labels separate. Shelter routing and Telegram do not automatically trigger from this model.

## 5. First practical work sequence for Codex

- Check repository HEAD/status and existing flood data contracts/tests.
- Incorporate or adapt `scripts/audit_flood_label_candidates.py` and its tests only where compatible.
- Create a **source+label coverage matrix** from actually inspected files; explicit empty/unknown coverage.
- Record verified Groundsource metadata and a plan for bounded Karnataka extraction.
- Do NOT train or expose flood predictions until the Gate A/ B requirements are satisfied.
- Run relevant tests and full regression suites; append root `update.md` before commit; protect raw/restricted data, credentials, ignored files and untracked `QandA.md`; stage only authorized files, push and verify `git ls-remote`.

## 6. Acceptance criteria for Phase 12A

- [ ] Original project objective restored as **actual flood outcome** target, rainfall model still separate.
- [ ] Candidate label schema and validators covered by tests.
- [ ] No implicit negative assignment or leakage.
- [ ] Source/district/year/coverage table from **real inspected datasets**.
- [ ] Groundsource access/licence/schema checked without unapproved full download.
- [ ] Separate riverine and pluvial/flash applicability assessment.
- [ ] Explicit GO/NO-GO with missing-data reasons.
- [ ] No change to operational warnings, existing models or historical polygon counts.

## 7. Truth in reporting

A completed Phase 12A is a real implementation milestone for data governance and target construction. It is **not** completed Karnataka-wide flood forecasting and must not be presented as such.
