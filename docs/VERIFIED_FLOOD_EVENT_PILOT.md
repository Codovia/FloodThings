# Phase 12D: verified flood event pilot

**Experimental flood-model training remains NO-GO.** This phase adds a proposed
target, reproducible review discovery, an inspected small evidence batch and
fail-closed observation contracts. It produces **zero eligible positive labels
and zero defensible negative labels**. No model is trained, replaced or deployed.
The existing rainfall model keeps its rainfall target and application behaviour.

## Proposed target, before label construction

The machine-readable [target protocol](phase12d/target_protocol.json) is
**PROPOSED_REQUIRES_INDEPENDENT_SCIENTIFIC_REVIEW**. Its initial domain is the
pre-existing public Udupi 3 km research window, not an administrative boundary.
Use whole **250 m EPSG:32643 cells**, aligned to origin (0,0), entirely covered
by that window. Freeze cell geometry and its hash before sampling outcomes.
This is a bounded methodological pilot towards Karnataka coverage, not a
validated statewide target or a certified district identity.

Issue a forecast at **00:00 UTC**; predict occurrence during the following
**half-open 24 hours**. Proposed occurrence means at least one independently
confirmed contiguous temporary-inundation patch of **2,500 m² inside the cell**,
on previously non-permanent-water land, observed within the interval. This
threshold is an explicit candidate operational definition, **not an established
sensor detection limit**. Local validation must determine its detectability,
registration error and sensitivity. Narrow urban flooding, flooded vegetation
and smaller incidents may be missed; this cannot yet represent every flood.

Positive evidence needs independent observed water, validated permanence and
quality, fixed cell support, exact observation time and external scientific
adjudication. A partially observed cell can support an existential positive
only if the confirmed patch itself meets the target definition. Negative
evidence needs an independently reviewed observation process capable of
detecting that target throughout the **same complete cell and complete interval**.
Discrete dry passes, news silence and missing coverage remain UNKNOWN.

Acquisition-time classification is a different target. A possible future
overpass target would require a schedule archived before issue time and issue
24 hours before acquisition; it needs its own approval. A satellite acquisition
in July is not itself a forecast made before that July acquisition.

Independent evaluation must hold out adjudicated physical events, spatial
regions and later time blocks. Unresolved group relationships must not be
treated as independent examples across train/evaluation partitions. Archive
forecast run, publication and availability times; all predictors must have
been available by issue time. Delayed reanalysis and target-window water maps
cannot stand in for such forecasts. Evaluate event/unit sensitivity, precision,
calibration and uncertainty against independent observations and simple
baselines. Sampling bias, seasonal coverage, power and geographic transfer
require independent scientific review; an arbitrary row count is not a GO gate.

## Reproducible review grouping

Only the frozen Phase 12C **19,854-row Karnataka subset** is processed. The
2.6-million-row global archive is neither downloaded nor re-extracted. Its
checksum is verified read-only. Original WGS84 WKB is preserved in that immutable
archive and addressed by source ordinal, UUID and original geometry hash.
Local SQLite native geometry is explicitly derived screening geometry. Every
original UUID, raw date and provenance pointer survives in the member register.
No union polygon is generated and no original polygon is treated as flood extent.

Rules fixed for this discovery version:

- Merge eligibility requires state/sole-source-district containment, positive
  reported support at most 10 km² and reported interval at most three days.
  Broad, cross-state, multi-district and longer intervals remain singletons.
- Each pair must share its fixed source district, have a date gap at most one
  day, start difference at most two days and combined span at most seven days.
  Dates use the Phase 12C inclusive-end discovery assumption, not verified onset.
- Require positive-area intersection, IoU at least 0.30, intersection/smaller
  area at least 0.50, area ratio at most four and centroid distance at most 2 km.
- **Every member must satisfy the pair rules against every other member**.
  Deterministic source-ordinal order resolves discovery order. If a new report
  fits multiple existing complete-link groups, retain a new ambiguous singleton
  and record alternatives. No connected-component or transitive event merging.
- Retain cross-group near-date/spatial associations for adjudication, including
  broad geometry associations. A 250,000-comparison cap fails the build instead
  of claiming complete counts from partial work.

These thresholds are cautious, uncalibrated review heuristics. They can fragment
one real flood or suggest an incorrect association. Software grouping does not
certify physical-event independence or make groups model examples.

| Discovery result | Count |
|---|---:|
| Original report records retained | 19,854 |
| Candidate review groups | 19,814 |
| Singleton / two-report groups | 19,774 / 40 |
| Reports meeting grouping support/date gates | 14,076 |
| Broad/admin-ambiguous singleton groups | 5,778 |
| Groups with unresolved cross-group relationships | 9,055 |
| Multiple complete-link alternatives in this actual run | 0 |
| Near-date positive-area related pairs | 11,626 |
| Related pairs across different review groups | 11,586 |
| Exact geometry comparisons, cap not reached | 18,138 |
| Independently certified physical groups | 0 |

All 19,814 groups need physical-event adjudication. **Actual independent physical
flood count is UNKNOWN**, not 19,814. The previous exact-date overlap count was
10,470; this version additionally allows the documented one-day discovery gap,
so its relation count measures a different screen.

## Bounded documentary inspection and manual review

Selected **eight news groups**, four per reference context, plus **two Udupi
GFD controls**: ten review items, below the 50-item limit. Candidates first need
date/geographic proximity to available independent evidence, then short dates
and smaller reported support. Report count is not the ranking criterion.

Udupi uses its retained geoBoundaries public research district geometry as
context only. Belagavi uses the retained official NRSC post-image viewport
registration, **only to prioritize map coverage**. A viewport is not a water
mask, measured location accuracy or corrected flood boundary. The source's
unusual projection metadata is not silently changed. Neither reference is
used to invent current LGD aliases for the separate SOI source districts.

The contextual pool contains 77 Udupi and 19 Belagavi review groups. All eight
selected groups are singletons with one-day reported intervals and reported
supports between 0.023 and 0.094 km². Those are polygon-support statistics,
not verified geographic/time accuracy. Each original UUID/date/hash and source
link is retained locally; their absence from public documentation respects
source geographic redistribution restrictions.

Four official PDFs were retrieved successfully, hash-bound and inspected as
text **and rendered pages**. Original PDFs, HTTP receipts and all detailed
review exports stay ignored locally. Receipts record response date, URL,
publisher, file size/SHA-256, inspected pages, evidence/issue date and limitations.
No publisher checksum is asserted where none was supplied. Response headers
are restricted to HTTP/content/date metadata; session cookies are not retained.

| Official evidence | Verified finding and limits |
|---|---|
| [MHA 22 September 2020 report](https://ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=NEW308), pages 1,5,6 | Udupi is named in affected coastal districts and rescue response. The enclosure was received **21 September**, not a new observation on the 22nd. Coastal totals are not assigned wholly to Udupi. Regional response context; exact Udupi flood footprint/onset remains UNKNOWN. |
| [MHA 27 July 2021 report](https://ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=D322), pages 1–3 | Explicitly reports villages flooded along rivers in Belagavi/Bagalkot/Gadag and attributes the regional situation to Upper Krishna reservoir discharge. This is flood-outcome evidence beyond rainfall; it supplies no candidate-specific grid footprint or onset. |
| [NRSC 26 July 2021 map](https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/Karnataka_floods_26jul_VAP_tile1.pdf), page 1 | WorldView-3 inundation annotations near Hulagabali/Halyal/Sankaratti; issued 29 July, map 2021/01. Acquisition **date** known, exact clock and validated target-cell mask absent; visible cloud and external imagery rights limits. |
| [NRSC 28 July 2021 map](https://www.nrsc.gov.in/nrscnew/assets/pdf/maps_dms/Maharashtra_floods_28jul_VAP_tile6.pdf), page 1 | Resourcesat-2A LISS-III map annotates floodwater in parts of Maharashtra/Karnataka; issued 29 July, map 2021/06. Cloud obscuration, date-only acquisition and map-only extent remain limitations. |

The latter three documents independently corroborate **one regional July 2021
flood-episode context**, not three independent physical floods. It may encompass
multiple local incidents. Candidate-group correspondence and source-chain
independence still require adjudication. The Udupi 2020 document is retained
conservatively as response context, not a certified cell/day inundation event.

The Groundsource release supplies no article URLs; the IFI candidates supply
agency/event references rather than recovered original articles for this batch.
No original news reference was recovered or invented. All eight group outcomes
remain **UNKNOWN**, with inspected regional evidence but no approval receipts,
no verified candidate-specific location/time and no confirmed satellite-mask
link. This is an initial documentary inspection, **not an external expert review**.
One-day news ranges are not independently verified one-day floods.

Two original Udupi GFD reference windows remain satellite-observed positive
composites: event 2728, 14–30 September 2005, **33 cells**; event 3551,
25 September–12 October 2009, **23 cells**. Both have **zero Groundsource
reports intersecting the public reference geography within the retained window**.
They are useful reference controls, not forced news matches or daily labels.

## Inventory linkage, observation quality and negative test

IFI discovery links cover **1,648 review groups / 61 retained IFI IDs**;
GFD links cover **three groups / one ID**, 4508, whose retained Gadag scope has
zero valid pixels. All links retain their original Phase 12C method and remain
possible, with **zero confirmed same-event associations**. Exact source-name
matching is incomplete; no alias-based reconciliation or uncertain merge occurs.

Of 494 IFI rows, 492 have usable retained ordered date windows. **42 exceed seven
days and 17 exceed 31 days**. Some month-like source windows have broad or
uncertain temporal meaning. For example, raw `09-01-2020 00:00` to
`30-09-2020 00:00` is retained as January 9–September 30 under the existing
day-first parser. Its source convention/meaning needs review; this is **not a
proven parser bug** and it is not silently changed to September 1. The eight
review groups do not inherit exact timing from these IFI windows.

This pilot evaluates **20 observation contexts**: 13 retained GFD scopes,
three retained Sentinel-1 acquisitions and four inspected official documents.
All are UNKNOWN for the proposed daily target. This is the selected pilot
assessment, not an exhaustive new audit of every satellite asset; frozen
Phase 12B checks also preserve the existing OPERA metadata limitations.

| Observation type | Why daily labels remain unavailable |
|---|---|
| GFD: four positive composites | Temporary-water cells within event windows are research evidence; exact acquisition/time, approved fixed cell and independent reference remain unresolved. |
| GFD: two zero-water composites | Spatial valid fractions approximately 99.819% and 98.083% still leave missing support and do not establish complete 24-hour absence. |
| GFD: seven insufficient scopes | Zero valid observations do not imply dry conditions. |
| Sentinel-1: 5,17,29 July 2021 | Exact retained UTC acquisitions and 40,000 valid VV/VH cells per scene are continuous backscatter, not categorical inundation. The 26/28 July maps do not validate floodwater at the 29 July acquisition. |
| Two optical map products | Documentary observed inundation, but acquisition date only, cloud gaps, no validated cell mask/permanence and unresolved rights. |
| Two MHA reports | Independent regional documentation, not same-unit continuous observations or precise target-clock flood masks. |

The validators require checksum-bound external review receipts. Group approval
binds originals, geographic support, timing and independent source families.
Daily observations bind exact protocol, fixed cell, source/reference bytes,
target interval and interpretation. Positive patches must meet area/contiguity/
cell/time gates; negative processes must cover the exact complete cell/interval.
Changed bytes, reused approvals, wrong units/times, partial/dry passes and
unapproved protocols fail closed. **These are consistency gates, not automated
certification of reviewer identity, source independence or scientific truth.**
Passing an observation contract would still not prove forecasting readiness:
issue-time feature availability and independent evaluation remain separate gates.
Tests use isolated synthetic fixtures; no test approval is a project label.

## Geographic rights and coverage

SOI ABDB2025 polygons retain [SOI's written-permission policy](https://surveyofindia.gov.in/pages/copyright-policy).
No restricted polygon, reconstructed spatial derivative, location-level group/
UUID/district linkage, original imagery or detailed review register is published.
NRSC's for-official-use notices and commercial imagery rights are retained;
public availability is not a redistribution grant. Public products contain only
code, protocol definitions, citations, factual document metadata and aggregate
counts. The existing public location directory and unresolved source identities
remain separate. No current/event-year LGD mapping is approved by this phase.

Candidate groups intersect **all 31 fixed source district units**. Verified
current-LGD identities remain **0/31**. The public
[district counts](phase12d/district_coverage.csv),
[31 × 21 district/start-year matrix](phase12d/district_year_coverage.csv) and
[start-year counts](phase12d/year_coverage.csv) cover **2005–2025**. Multi-district
counts are non-additive; a group's year is its earliest reported start year.
Zero in 2006 indicates no retained report groups, not absence of flooding.
Eligible positive and negative counts are zero in every unit/year. Independently
documented reference coverage is regional July 2021 Belagavi, with Udupi 2020
response context and Udupi 2005/2009 composite controls; no statewide observed
label coverage has been created.

## Local outputs and reproduction

New ignored immutable version: `data/working/karnataka_verified_event_pilot_v1/`.
It contains `candidate_event_groups.jsonl`, `group_members.jsonl`,
`possible_group_relationships.csv`, `manual_reviews.json`,
`reference_controls.json`, `source_linkage.jsonl`, `source_receipts.json`,
`ifi_temporal_precision.json`, `observation_quality.json`, aggregate coverage,
`report.json` and `manifest.json`. The manifest binds source/output/code/runtime
hashes. `build` refuses existing versions; `validate` is read-only. Replay uses
only the frozen Karnataka subset, not a new global extraction. Development
drafts are retained separately in ignored recovery storage.

```bash
PYTHONPATH=data/working/groundsource_runtime_v1 scripts/.venv/bin/python -B scripts/build_verified_flood_event_pilot.py build
PYTHONPATH=data/working/groundsource_runtime_v1 scripts/.venv/bin/python -B scripts/build_verified_flood_event_pilot.py validate --replay --public docs/phase12d
PYTHONPATH=data/working/groundsource_runtime_v1 backend/.venv/bin/python -B -m pytest -q tests
backend/.venv/bin/python -B -m pytest -q backend/tests -k 'not real_training_reproduction'
```

The retained research/runtime dependencies are reused without installation or
environment changes. Do not run `build` against the completed version. Detailed
registers and document receipts deliberately have no public-export command.
Only the explicit aggregate allowlist can be compared with public copies.

## Readiness and next evidence required

**NO-GO: zero certified physical news groups, zero eligible positive labels,
zero defensible negatives, zero independent eligible event holdouts and no
verified complete issue-time feature joins.** One documented regional flood
episode and existing water pixels do not satisfy those prerequisites.

Next, obtain original reports or independently documented local incidents,
recover exact observation timing and verified geography, adjudicate candidate
relationships, obtain native masks and permanence/quality evidence where
appropriate, resolve rights, and independently approve the proposed target.
Acquire or validate a complete same-unit/full-interval observation process
before any negative label. Then assemble T-available predictors and independently
review event/spatial/temporal evaluation and sample power. Further enlargement of
the news inventory is not the priority.

Exact validation, preservation and delivery evidence is recorded in
[validation summary](phase12d/validation_summary.json) and the chronological root
`update.md` append. No live frontend/browser deployment claim is made by this
offline data-foundation change.
