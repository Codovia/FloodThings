# Phase 12A — actual Karnataka flood-outcome foundation

Verified 12 October 2026 against `ca55762d25ab33f58542ff3be0c90120cfc972d4`.
The objective is actual flood occurrence across Karnataka. This milestone is an
offline data foundation, not statewide prediction. The supplied
[blueprint](FLOOD_PREDICTION_IMPLEMENTATION_BLUEPRINT.md) is retained as a proposal;
this document and reproduced counts describe the actual checkout. Historical
product requirements extracted in Stage 5A are context, not evidence of accuracy.
Existing rainfall inference, maps, warnings, shelters and Telegram are unchanged.

## Decision and exact blocking evidence

**NO-GO for supervised flood-occurrence training. No flood model was trained.**

Gate A: four satellite-positive event scopes, zero independently verified
non-flood labels, zero eligible daily occurrence records. The 13 candidate scopes
pass schema validation but remain scientifically ineligible. Seven scopes have
insufficient observation; two contain no qualifying mapped water but lack full
unit/interval absence evidence. IFI has 494 reports, all unresolved for current
geometry; one reversed date pair and one missing/malformed pair leave 492 usable
event windows. None is an independently adjudicated daily label.

Gate B: the riverine and pluvial/flash targets below are proposals; neither has a
signed scientific target/quality protocol with adequate observations.

Gate C: no reproducible flood-label feature table with historically verified
availability/issuance. Reanalysis valid time does not prove availability at issue
time. GloFAS history is modelled retrospective discharge, not observed labels or
historically issued forecasts. Gate D: no independent positive/negative test set,
event/location/time holdout or flood-outcome evaluation. No forecast endpoint is
enabled. Machine-readable blockers are in
[source summary](phase12/source_coverage_summary.json).

## Actual accessible source inventory

All counts below come from retained files; earlier manifests are checked and the
existing source-to-product validators are rerun separately. Source originals and
research derivatives retain their bytes. A publisher's general licence does not
lift separate restricted-boundary or resource-specific publication conditions.

| Source | Accessible records / schema | Precision and permitted role | Rights / access limits |
|---|---|---|---|
| IFI v3 | 494 Karnataka-associated rows and unique UEI IDs; 492 usable windows. Original CSV has 23 columns: UEI, dates, cause, location, district/state tokens/codes, coordinates, impact, sources. 73 district tokens include multi-state/former/misspelled names. | Reported event date ranges, not verified onset/end. All 494 current-geometry joins unresolved. News/cause strings are not adjudicated mechanism labels. | [IFI record](https://zenodo.org/records/16994648), CC BY-NC 4.0; retained rights/schema metadata and publisher MD5 checked by catalogue validator. Detailed originals remain local under existing policy. |
| GFD MODIS V1 | 13 reviewed maps; 4 positive, 2 observed-zero, 7 insufficient; 387 qualifying event-pixels. Bands include flooded, permanent water, clear views, clear percentage and duration. | Original inclusive multi-day event windows; at-least-once mapped non-permanent water, no exact daily onset. Retained 250 m UTM43N analysis grid; catalogue describes 250 m classification while band table says 30 m. | [Official catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1), CC BY-NC 4.0; Cloud to Street/DFO/Tellman attribution. |
| CHIRPS v2 | 11,315 district-date rows, 365 dates, 31 source geometry IDs in 2025. Daily mm, source asset/version, mean/min/max, valid/expected counts. | 0.05° rainfall aggregated using retained SOI 2025 polygons; no flood labels, historical administrative continuity or issue-time availability proved. Four older positive-event rainfall contexts remain research only. | [Official catalogue](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) public domain; SOI-derived detailed tables remain local. |
| Open-Meteo ERA5 / saved rainfall model | Two retained hourly JSONs, **26,424 timestamps each**, 2022-12-28 through 2026-01-01; precipitation, temperature, humidity, pressure, snowfall. Portable JSON scaler/coefficients and metadata. | 0.25° reanalysis/provider grids at Kundapur and Mangaluru; eight transformed predictors. Target remains ≥64.5 mm rolling 24 h rainfall. No flood label, calibrated flood probability or flood skill claim. | [Historical API](https://open-meteo.com/en/docs/historical-weather-api), CC BY 4.0 data, noncommercial free service; model hash `f3fa9b53d7047746f9d26cba8556705fb3fd2328128a236cb4f423575acf4316` retained. |
| CWC/NWDP / Year Book | 1,697 retained July–August 2019 observations: 1,642 hourly water-level records and 55 daily discharge records across 3 stations; 81 reconciliation cases, 33 disagreements. Only 14 discharge rows eligible with caveats (Sadalga 2, Huvinhedgi 12, Gokak 0). | Original acquisition strings, units, values/QC, datum/coordinate alternatives and unknown availability preserved. All 3 water-level datum/threshold joins unresolved; daily aggregation/timezone unresolved. No gauge-to-flood occurrence mapping. | Resource `Other(Open)` not a standard resolved licence; CWC/NWDP policy interaction and official-use Year Book rights unresolved. No detailed republication. See [source semantics](HYDROLOGY_SOURCE_SEMANTICS.md). |
| GloFAS historical v5 | Retained NetCDF 62 × 20 × 70 = 86,800 finite values; 806 extracted cell-day rows (13 cell/station contexts × 62 days). `avg_dis`, m³/s, 0.05° grid. | Valid timestamps 2019-07-02–09-01; interpreted preceding 24 h averages span July–August. No source time-bounds array, measured truth or historical issuance. Sadalga/Huvinhedgi exploratory primary cells only; Gokak unresolved. | [EWDS historical product](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical), separate CEMS-FLOODS licence; static maps CC BY 4.0. Previously retained v5 operational/pre-operational documentation discrepancy remains frozen; no new operational claim. [Pilot method](GLOFAS_PILOT_METHOD.md). |
| Administrative context | 31 NIC directory names, 31 SOI 2025 source IDs; 0 independently current-LGD-reconciled identities, 12 exact NIC candidates/19 unresolved. Public geoBoundaries regions for satellite reviews. | Modern polygons are context, not historical boundary certification. Exact spelling only; **Bijapur remains unassigned**, never silently converted to Vijayapura. No inferred district coordinates. | SOI raw/derived geometry stays restricted/local; public geoBoundaries v6 CC BY 4.0; directory's Dakshina Kannada navigation context uses its separately recorded ODbL source. |
| Groundsource | Verified Zenodo metadata only, CC BY 4.0; `groundsource_2026.parquet` **667,122,400 bytes**, MD5 `cd1b5de6508f7aad8e1d1d0dd4cecea6`. | Karnataka rows **unknown**; parquet schema, CRS and exact column names **unverified**. No data rows downloaded. | [Publisher record](https://zenodo.org/records/18647054) and [metadata receipt summary](phase12/groundsource_metadata_review.json). Full download requires separate explicit approval. |

## Actual spatial and observation coverage

| GFD ID | Source region | Inclusive interval | Qualifying event-pixels | Evidence |
|---|---|---|---:|---|
| 2728 | Udupi | 2005-09-14–09-30 | 33 | positive |
| 3551 | Udupi | 2009-09-25–10-12 | 23 | positive |
| 3652 | Chitradurga | 2010-05-18–05-24 | 2 | positive; 92.680% spatial valid coverage |
| 2758 | Kolar | 2005-10-23–12-09 | 329 | positive; 96.164% spatial valid coverage |
| 2698 | Bijapur (source spelling) | 2005-07-23–08-16 | 0 | observed-zero, 99.819% spatial valid; training UNKNOWN |
| 3107 | Raichur | 2007-06-22–07-04 | 0 | observed-zero, 98.083% spatial valid; training UNKNOWN |
| 3160 | Chikkaballapura | 2007-08-08–08-15 | 0 | insufficient; no valid cells |
| 2690 | Dharwad | 2005-07-07–07-27 | 0 | insufficient; no valid cells |
| 4382 | Raichur | 2016-07-25–08-26 | 0 | insufficient; no valid cells |
| 4508 | Gadag | 2017-08-10–08-26 | 0 | insufficient; no valid cells |
| 2935 | Mandya | 2006-07-28–09-12 | 0 | insufficient; no valid cells |
| 2507 | Dharwad | 2004-06-20–10-07 | 0 | insufficient; no valid cells |
| 4378 | Kodagu | 2016-07-07–08-03 | 0 | insufficient; 5.019% spatial valid coverage |

Public application coverage stays **56 polygons from two Udupi events**, not 56
independent events. Research positives cover three source regions and three years
(2005, 2009, 2010); 387 is a sum of event-pixels, not a unique spatial union.
Mechanisms are UNKNOWN. A scope positive means water somewhere in the reviewed
region/window, never that every district cell/day was flooded.

[District/year matrix](phase12/district_year_coverage.csv): 31 × 57 = **1,767 rows**,
1969–2025 inclusive. Positive/negative/unknown scope counts, event groups,
eligible/ineligible counts and observation status are separate. All **13 candidate
scopes are ineligible**, with **4 positive / 0 verified negative / 9 UNKNOWN**.
Only 12 scopes match current directory spellings; Bijapur's one observed-zero
scope remains in the source summary rather than guessed into the NIC matrix.
Zero record counts are inventory counts, not zero hazard. Unobserved unit-days
cannot be enumerated without a frozen spatial grid/interval universe; their number
is explicitly UNKNOWN, not a fabricated number of negatives.

IFI source-token/year matrix stays local and preserves multi-state and historical
tokens separately. Its district memberships overlap and must not be summed as
independent events. The 494 IFI reports and 387 GFD pixels are different evidence
units and are not concatenated into training examples. Prior IFI/GFD associations
remain provisional, not 494 satellite-confirmed floods.

## Candidate contract and scientific checks

`scripts/audit_flood_label_candidates.py` adapts the starter into a strict v1 CSV
contract. Required fields include original record and source/hash/reference,
geometry/spatial unit, inclusive observation interval and temporal precision,
label/coverage, mechanism, event/source/review groups, quality flags, rights,
review status and a separate scientific-review decision/reference.

`FLOOD_OBSERVED` requires direct observed evidence for its stated unit/interval.
`NON_FLOOD_OBSERVED` requires independently reviewed full-unit, full-interval
absence evidence, detection limitations and a justified method. `UNKNOWN` never
becomes zero. Schema checks reject missing dates, reversed windows, missing
provenance, malformed hashes/rows, unsupported labels and all duplicate copies.
Passing schema does not certify scientific correctness or rights.

Optional JSON receipts are keyed by observation ID. Each must independently
match unit, interval, label, original record/hash, geometry, mechanism, groups,
review/coverage/method references and quality limitations. Original evidence bytes
are checked under an explicit `--source-root`; escaping paths and mismatched hashes
fail. Approvals are supplied by qualified reviewers, never generated from a
candidate's self-declared VERIFIED status. Receipts must describe observed truth,
detection limits, internal-use rights and adjudicated quality flags. Negative
receipts additionally require continuous full-interval coverage. This is a
machine-checkable consistency gate, not automated scientific certification.

Readiness requires eligible positives and verified negatives in BOTH training and
test partitions, a reviewed fixed 24 h occurrence target/protocol, complete finite
predictor values, version/units/join/missingness metadata and verified availability
and as-issued parity. All feature-valid and availability times must precede issue
time; the labelled day and 24 h horizon must match. Chronological non-overlap and
whole event/source/review/spatial-unit holdouts are checked. Group IDs refer to
related-event/source-derivation/review batches, not merely vendor names; merge
cross-source reports of the same physical event into a common event group before
splitting. Manual review must adjudicate ambiguous cross-event relationships and
feature provenance; booleans alone do not establish truth. Even a passing check
permits only a separate non-operational pilot; deployment always remains false.

## Separate proposed targets and next defensible step

**Riverine:** independently verified flooding within a surveyed reach/catchment in
the next 24 h, distinct from measured high-flow or gauge danger exceedance. An
exceedance pilot needs independently measured stage/discharge, stable datum,
station/reach identity, time/QC semantics and historically applicable thresholds;
exceedance cannot itself establish inundation. Exclude Gokak from quantitative
joins until site/confluence ambiguity resolves. All three retained stations lack
adequate outcome/absence/threshold semantics, so **CWC is currently NO-GO even for
a defensible flood-occurrence riverine pilot**. Preserve the 14 discharge rows as
caveated exploratory context. Next obtain authoritative datum/time/QC/site and
rights clarification plus independent inundation observations, rather than
deriving labels from GloFAS peaks. No clarification messages were sent.

**Pluvial/flash:** propose a fixed reviewed grid/locality footprint and UTC calendar
day [00:00, next 00:00), predicting observed non-permanent inundation somewhere in
that unit during the next 24 h. Grid scale must reflect sensor/location precision;
no street-scale claim from a district polygon or MODIS pixel. Flood mechanism
must be adjudicated, not inferred from rainfall or a news headline. Exclude
permanent water, uncertain timing/geometry, unobserved/partially covered absences,
unreviewed SAR thresholds and units outside independently evaluated coverage.
Retain current event-window labels for evidence research only. Obtain dated,
legitimately supplied inundation/observation coverage with detection limits and
review same-unit/day absences before constructing daily targets.

Feature proposals: antecedent rainfall/wetness and versioned terrain, land cover,
catchment/upstream attributes, and genuinely archived issued meteorological runs.
Record original bytes, valid/available/issue times, joins and missingness. Future
observations, delayed reanalysis treated as issued data, rainfall threshold labels
and modelled discharge treated as observed truth are excluded. Reservoir features
require independently time-stamped observations. Initial evaluation should compare
seasonal climatology and reviewed empirical thresholds with Logistic Regression;
only then consider trees. Hold out entire physical floods, later time periods and
independent localities/catchments; embargo overlapping feature/target windows.
Report confusion matrices, precision/recall, PR-AUC and false-alert rate against
simple baselines; calibration/lead time only with adequate independent evidence.
No arbitrary minimum event count is claimed to prove statewide generalization.

**Groundsource next step:** publisher documentation establishes news-derived
localized polygons and event date ranges, not exact flooded streets or universal
negative coverage. [Google's method report](https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/)
reports imperfect location/time agreement, so each Karnataka assignment still needs
review. The linked paper was blocked by a bot challenge here; exact parquet fields,
CRS and row schema remain unverified. A proposed metadata-range inspection was
interrupted; no parquet/schema claim is made. With separately approved access,
verify full checksum/schema/CRS and bounded Karnataka intersections, preserving
original polygon/date uncertainty and ambiguous boundary-crossing assignments.
Do not use centroid or name matching to create exact locality labels. Deduplicate
physical floods across articles, Groundsource/IFI/GFD and retain event holdouts.
News absence supplies no non-flood negatives. No 667 MB download is authorized by
this milestone; no Karnataka count is invented from global coverage claims.

## Reproduction and publication

```bash
python3 scripts/build_flood_outcome_foundation.py build
python3 scripts/build_flood_outcome_foundation.py validate
python3 scripts/audit_flood_label_candidates.py \
  data/working/karnataka_flood_outcome_foundation_v1/candidates.csv \
  --source-root /home/pioneer/Projects/FloodPrediction
backend/.venv/bin/python -B -m pytest -q tests
```

`build` refuses existing output; `validate` checks saved files/code hashes and
reproduces candidates, counts and both matrices read-only. Completed local outputs
are ignored under `data/working/`; public artifacts contain aggregate evidence only.
A fresh clone without original local sources cannot reproduce source evidence;
missing data fails explicitly. CLI exit 0 means valid schema/reproduction, **not GO**;
read `training_readiness.decision`. Exit 1 means invalid candidate rows; exit 2
means an input/source failure. No migrations, UI changes, downloads of new source
observations, cloud services, hazard raster, forecast service or warning activation.
