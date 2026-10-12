# Phase 12C: Groundsource Karnataka extraction

This is an offline event-inventory audit. News-reported locations and dates remain
distinct from satellite-observed inundation and independently approved predictive
labels. **Flood-model training remains NO-GO. No model is trained, replaced or
deployed by this workflow.**

## Acquisition and input integrity

The explicitly approved source is [Groundsource v1 on Zenodo](https://zenodo.org/records/18647054),
**Groundsource: A Dataset of Flood Events from News**, Rotem Mayo and 14 named
coauthors, published 15 February 2026. The publisher record and Google's own
method report were cross-checked; author attribution is retained in the public
source metadata. Our spatial screening and aggregates are derived analysis,
not publisher validation of individual events.
DOI `10.5281/zenodo.18647054`, archive `groundsource_2026.parquet`, **667,122,400
bytes**, publisher MD5 `cd1b5de6508f7aad8e1d1d0dd4cecea6`, CC BY 4.0.
The v1 designation is in the official HTML; the API omits a version field and
its record revision is a different concept. Publisher identity/licence/file
metadata and free space were checked before the approved transfer. Receipts stay
under ignored `data/raw/groundsource/zenodo_18647054_v1/`.

The acquisition utility accepts only that official pinned archive. Interrupted
responses preserve written bytes. Small HTTP 206 ranges must match requested
offsets, total size and response length; ignored ranges are rejected. At most
eight workers stream separate segments to disk, while a single locked parent
appends in order. An exclusive file lock and an append-offset check prevent
competing writers. The final name is assigned only after full publisher MD5 and
size verification. SHA-256 is retained for subsequent reproduction. No other
large dataset is downloaded.

PyArrow 26.0.0 is the isolated reader dependency. Its Linux/Python 3.12 wheel was
verified against the [official PyPI metadata](https://pypi.org/project/pyarrow/26.0.0/)
SHA-256 `6a628922ba20705fa964ca73e4ef959c2fb2f14b9bbec5589a6a1e68e6257c85` and
extracted into new ignored `data/working/groundsource_runtime_v1/`. Existing
application/research environments remain intact. This is a software dependency,
not another research dataset. The optional requirements file pins this wheel.

## Bounded scan and geographic interpretation

The schema remains five data columns plus a stored dataframe index: `uuid`,
`area_km2`, WKB `geometry`, `start_date`, `end_date`, `__index_level_0__`.
The reader checks GeoParquet encoding/CRS and exact columns, scans **1,024 rows
per batch**, disables threaded prefetch and never materializes the global table.
Global UUID counts/conflicts, candidate provenance and spatial indexes are kept
in SQLite, with a 32 MiB cache and disk-backed temporary work. The result records
actual maximum batch size/bytes and peak process RSS.

The boundary basis is the retained **Survey of India ABDB2025 release**, validated
read-only against original component hashes and its frozen geometry checks.
All 31 source district polygons are valid; their union covers the same release's
Karnataka state polygon without positive-area overlaps. Groundsource WGS84
polygons are transformed to the **actual SOI `.prj`**, using XY axis order. The
source CRS is not silently replaced with the metadata's differing EPSG assertion.
Original boundary coordinates/Z values/files are never edited; topology analysis
uses a derived 2D representation locally.

**Administrative identity limitation:** 0/31 independently current-LGD identities
are verified. Only 12 names have exact NIC-name candidate matches; 19 source name
cases remain unresolved. Original names, including unusual source characters,
and supplied unverified codes are preserved. Stable matrix keys use the source
release's object IDs, not guessed LGD IDs. These are fixed-release geographic
units, not certified event-year boundaries or current administrative identities.

Source: Survey of India, Government of India. The [current SOI policy](https://surveyofindia.gov.in/pages/copyright-policy)
retains written-permission requirements for reproduction. SOI geometries,
coordinates and detailed derived spatial products remain local. Public outputs
contain audit code, factual metadata, counts and checksums only.

Candidate categories:

| Status | Meaning |
|---|---|
| `DEFINITE_WITHIN_SOURCE_STATE` | Valid transformed polygon fully covered by the source Karnataka state polygon |
| `CROSS_STATE_INTERSECTION` | Positive-area intersection but some reported polygon lies outside the source state |
| `STATE_BOUNDARY_TOUCH_ONLY` | Topological contact with zero intersection area; no positive-area Karnataka assignment |
| `INVALID_OR_AMBIGUOUS_BBOX_SCREEN` | Bounding box warrants review, but invalid coordinates/geometry, unsupported geometry, projection failure or potential antimeridian interpretation prevents a trusted predicate |

Every global geometry is screened. Empty/missing/unparseable geometries are
counted globally; an unlocatable row cannot be asserted absent from Karnataka.
No geometry is repaired or clipped to manufacture a definite match. District
intersections require positive area. Sole district containment is recorded
separately; polygons spanning districts remain multiple assignments. Source
polygon area bins describe reported spatial support, **not measured location
accuracy, inundation area or sensor resolution**.

## Date, duplicate and inventory checks

Dates must be exact ISO date strings, valid calendar dates, ordered and no later
than the audit cutoff, 12 October 2026. Temporal usability means an interpretable
reported date range for **screening**. It does not establish exact onset,
acquisition time or flooding on every day. Inclusive-end interpretation is an
explicit discovery assumption for interval-length/overlap calculations, not a
verified publisher temporal convention. Coverage is assigned to start year;
spanning intervals are not expanded into daily outcomes.

Geographic/temporal screening usability requires full state containment and a
usable date range; single-district usability additionally requires sole district
containment. Cross-state, invalid and ambiguous records remain separately
enumerated. Usable inventory candidates remain scientifically unreviewed.

Duplicate checks preserve all rows:

- Global repeated UUIDs, excess rows and conflicting geometry/date/area payloads
  are counted on disk, including occurrences outside Karnataka.
- Candidate repeated UUIDs and normalized 2D geometry/date groups are counted
  separately. Exact duplicates are not automatically deleted or merged.
- A bounded spatial/date overlap screen uses an R-tree followed by exact
  positive-area intersection. At most 250,000 pair comparisons are performed;
  the report states whether it was exhaustive. A capped count is explicitly a
  lower bound. Overlapping records are possible associations, not certified
  duplicates of one physical flood.

IFI comparisons use retained usable date ranges and exact normalized source
district tokens. They do not invent missing IFI geometries or spelling aliases.
GFD comparisons use retained review-region/date contexts. Unreconciled source
names limit this screen and are listed explicitly. Two checksum-verified Udupi
GFD pixel sets support an additional actual spatial/date overlap check; this
does not extend pixel-level verification to other GFD events. Potential links are
stored with their method; **confirmed same-event counts remain UNKNOWN**.
No uncertain cross-source association is merged.

## Evidence status and protocol advancement

[Google's method report](https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/)
describes automated extraction from news and imperfect location/time agreement.
The released schema supplies no per-record confidence or article URL. Global
validation rates cannot be assigned as individual candidate probabilities.
Reported location polygons are not independently confirmed inundation boundaries.

Candidates with usable geography/dates can enter **manual positive-evidence
review**. They cannot advance automatically into the approved observation
contract: obtain an independently verified dated flood report/reference, review
location and mechanism, reconcile event/source groups and uncertain date ranges,
and match a fixed geographic unit and actual observation timing/quality.
Acquisition-time satellite labels need matched categorical water/permanence and
quality evidence; daily occurrence needs evidence appropriate to its whole target
window. Reference receipts, rights, detection limits and scientific adjudication
remain mandatory under [Phase 12B](FLOOD_OBSERVATION_FEASIBILITY.md).

Negatives require meaningful independently verified same-unit observation
coverage throughout the relevant interval. Missing news, missing records or an
unreported year are UNKNOWN, never non-flood labels. Complete historically
available feature joins, independent event/spatial/time holdouts and protocol
approval are still required before any model fit. This task authorizes none.

## Local artifacts and reproduction

Completed local version: `data/working/karnataka_groundsource_2026_v1/`.

- `candidate_events.csv`: complete candidate register, original IDs/date strings,
  source-row ordinals, geometry hashes, geographic/temporal status, duplicate and
  possible-match counts, review requirement and explicit zero label eligibility.
- `audit.sqlite`: on-disk global duplicate index and candidate/intersection/match
  evidence; derived geometry stays local.
- `district_year_coverage.csv`, `district_coverage.csv`, `year_coverage.csv`:
  exact source-unit/start-year counts. Multi-district intersections are
  non-additive; yearly candidates count each source row once.
- `possible_inventory_matches.csv`: complete possible-link register with methods,
  kept local to preserve existing source publication restrictions.
- `report.json`, `manifest.json`: aggregate results, all source/output/code hashes,
  runtime versions, scientific limitations and NO-GO decision.

The manifest pins completed outputs and inputs. `build` refuses existing partial
or complete versions. `validate` is read-only; `--replay` streams the global
archive again to reproduce candidate inclusions, exclusions and every registered
candidate's original-row attributes/predicates. Public aggregate checks compare
bytes to the local completed version.

```bash
python3 -B scripts/acquire_groundsource.py verify
PYTHONPATH=data/working/groundsource_runtime_v1 scripts/.venv/bin/python -B scripts/audit_groundsource_karnataka.py validate --replay --public docs/phase12c
PYTHONPATH=data/working/groundsource_runtime_v1 backend/.venv/bin/python -B -m pytest -q tests
```

The archive, runtime, full candidate register, database, raw receipts and
restricted source records are ignored and never staged. Public aggregates and a
small deterministic candidate metadata sample are exported only after successful
full-file verification and extraction. The verified extraction results follow; full replay and preservation checks are
recorded with validation evidence below.

## Verified Karnataka results — 12 October 2026

The complete publisher-checksummed archive contains **2,646,302 rows**. Exact
source-geometry screening yields **19,854 Karnataka candidate records**, with
19,854 distinct nonempty UUIDs. These are news-derived report records; the number
of independently verified physical floods is **UNKNOWN**.

| Screening outcome | Records |
|---|---:|
| Fully contained in source Karnataka state and temporally usable | 18,194 |
| Cross-state positive-area intersections | 1,660 |
| Boundary-touch-only candidates | 0 |
| Invalid/ambiguous Karnataka bounding-box candidates | 0 |
| Fully contained in one source district and temporally usable | 17,296 |
| Contained in state but spanning source districts | 898 |
| All candidates intersecting multiple source districts | 1,479 |
| Single partial district intersections | 1,079 |
| Valid reported date ranges | 19,854 |
| Manual verification required | 19,854 |
| Eligible predictive positive / defensible negative labels | 0 / 0 |

The multi-district and cross-state categories overlap and must not be added as
independent exclusions. Across the global archive, 2,646,268 geometries are valid
areal geometries and 34 have ambiguous antimeridian interpretation; none of those
34 intersects Karnataka's bounding-box screen. No missing, empty, malformed,
invalid-coordinate or topologically invalid geometry was encountered. This is
geometric consistency of released locations, not validation of news/event truth.

All Karnataka candidates have calendar-valid, ordered reported dates. Start dates
range **26 July 2005–14 December 2025**. There are 9,712 one-day reported intervals
and 10,142 intervals of 2–7 days under the stated inclusive assumption. No
candidate starts in 2000–2004, 2006 or 2026; these are missing report coverage,
not flood-free periods. The release contains later global dates, so Karnataka's
actual date extent must be reported separately.

### District coverage

Every one of the 31 **source-release district polygons** has positive-area
candidate intersections and sole-district contained candidates. The 837-row
[complete district/year matrix](phase12c/district_year_coverage.csv) preserves
source object IDs, original names, unverified codes and zero label eligibility.
The [district aggregate CSV](phase12c/district_coverage.csv) contains all fields.
Names below are verbatim SOI strings, not corrected/current-LGD identities.
Intersections are non-additive; sole-district usable records sum to 17,296.

| SOI source district name | Intersecting records | Sole-district contained, date-usable |
|---|---:|---:|
| `B<galkot` | 755 | 517 |
| `Bengal#ru (Rural)` | 399 | 115 |
| `Belag<vi` | 1,906 | 1,590 |
| `Chikkamagal#ru` | 550 | 440 |
| `Ball<ri` | 232 | 157 |
| `Ch<mar<janagara` | 392 | 173 |
| `Chitradurga` | 210 | 131 |
| `Koppal` | 287 | 189 |
| `Vijayanagara` | 313 | 175 |
| `Raich#r` | 464 | 300 |
| `Chikkaball<pura` | 98 | 70 |
| `D<vanagere` | 248 | 161 |
| `Dh<rw<d` | 597 | 437 |
| `Gadag` | 422 | 221 |
| `H<veri` | 447 | 294 |
| `H<ssan` | 398 | 241 |
| `Kalaburagi` | 899 | 713 |
| `Bengal#ru (Urban)` | 5,816 | 5,489 |
| `Kol<ra` | 339 | 154 |
| `Mandya` | 369 | 261 |
| `Mys#ru` | 733 | 492 |
| `Shivamogga` | 455 | 365 |
| `Dakshina Kannada` | 1,598 | 1,374 |
| `Uttara Kannada` | 993 | 670 |
| `Vijayapura` | 561 | 394 |
| `Y<dgir` | 380 | 249 |
| `R<managara` | 430 | 169 |
| `Udupi` | 940 | 719 |
| `Tumak#ru` | 292 | 190 |
| `Kodagu` | 844 | 558 |
| `B\dar` | 404 | 288 |

### Start-year coverage

The [year aggregate CSV](phase12c/year_coverage.csv) counts each source row once.
These counts describe retained reporting coverage; increases do not establish
changes in flood incidence. Zero years remain UNKNOWN for observed flooding.

| Start year | Candidate records | State-contained, date-usable | Sole-district, date-usable |
|---|---:|---:|---:|
| 2000 | 0 | 0 | 0 |
| 2001 | 0 | 0 | 0 |
| 2002 | 0 | 0 | 0 |
| 2003 | 0 | 0 | 0 |
| 2004 | 0 | 0 | 0 |
| 2005 | 19 | 16 | 16 |
| 2006 | 0 | 0 | 0 |
| 2007 | 5 | 4 | 4 |
| 2008 | 1 | 0 | 0 |
| 2009 | 89 | 77 | 72 |
| 2010 | 65 | 58 | 55 |
| 2011 | 67 | 60 | 60 |
| 2012 | 159 | 145 | 140 |
| 2013 | 327 | 309 | 297 |
| 2014 | 264 | 234 | 230 |
| 2015 | 207 | 187 | 182 |
| 2016 | 250 | 230 | 224 |
| 2017 | 875 | 841 | 823 |
| 2018 | 892 | 789 | 747 |
| 2019 | 2,257 | 2,088 | 1,951 |
| 2020 | 1,972 | 1,819 | 1,704 |
| 2021 | 1,618 | 1,485 | 1,399 |
| 2022 | 2,797 | 2,600 | 2,455 |
| 2023 | 1,116 | 1,012 | 985 |
| 2024 | 3,016 | 2,719 | 2,600 |
| 2025 | 3,858 | 3,521 | 3,352 |
| 2026 | 0 | 0 | 0 |

### Location support, source confidence and duplicate ambiguity

Projected reported-location areas: <1 km² **9,177**; 1–10 km² **6,941**;
10–100 km² **2,575**; 100–1,000 km² **339**; ≥1,000 km² **822**. These sizes
provide review context, not accuracy or confirmed inundation measurements.
All 19,854 candidates lack released per-record confidence and article URLs.

**0** repeated UUID groups globally or within Karnataka; **0** identical
normalized geometry/date groups within Karnataka. Nevertheless, the exhaustive
bounded spatial/date screen found **10,470 positive-area/date-overlap pairs**
from **16,041** exact pair comparisons. The 250,000 comparison cap was not reached.
Overlaps can be separate floods, related reports or broader/narrower location
statements: confirmed duplicate physical-event counts remain UNKNOWN. No rows
were automatically merged or deleted.

### IFI/GFD comparison

| Method | Possible pairs | Groundsource candidate records | Distinct retained IDs |
|---|---:|---:|---:|
| IFI exact source district token + date overlap | 2,829 | 1,651 | 61 |
| GFD source review-region token + date overlap | 3 | 3 | 1 |
| Actual overlap with two retained Udupi GFD event-water pixel sets + dates | 0 | 0 | 0 |

IFI has unresolved original geometries. Name-only comparisons are incomplete
where district identities cannot be reconciled. Seven GFD source scopes lack an
exact source-name link: IDs 3160, 2690, 4382, 2507, 2698, 2758 and 3107. No aliases
were guessed. Date-only screens yielded 19,577 IFI and 424 GFD pairs, which are
**not spatially certified links**. The absence of matches to the two Udupi pixel
sets cannot establish absence of Karnataka/GFD overlap elsewhere. Confirmed
same-physical-event counts for all cross-source methods remain **UNKNOWN**.
GFD review contexts include insufficient and observed-zero evidence; a possible
inventory association does not nominate a positive or negative label.
The three GFD name/date links all concern **event 4508, Gadag**: its retained
scope has **0 valid observed pixels** and `insufficient_observation` status.
These links therefore supply **no satellite confirmation of flooding or absence**.

### Advancement and training decision

**18,194** state-contained/date-usable candidates can enter manual positive-
evidence review, including **17,296** with sole-source-district containment.
All candidates need an independent dated reference and review of geographic
precision, event mechanism, timing and physical-event grouping. The 1,660
cross-state candidates require geographic adjudication before that nomination.
No candidate has advanced automatically into a scientifically eligible label.

**NO-GO remains unchanged: 0 eligible predictive positives, 0 defensible
negatives, no independently eligible event holdouts and no complete verified
issue-time feature joins.** News locations do not establish sensor-observed
inundation, acquisition-time truth or full-day flood occurrence. Positives need
independent source/reference validation, a reviewed fixed unit/target window,
native observation quality/water/permanence evidence where applicable, and
scientific adjudication. Negatives need explicit adequate same-unit/full-window
absence evidence and detection limits; missing news is insufficient. Resolve
current/event-year identities and protocol approval, then obtain T-available
features and event/spatial/temporal holdouts before any future training decision.
No model was trained, replaced or deployed during this extraction.

### Resource and output evidence

**2,585 batches**, maximum **1,024 rows**, maximum visible Arrow batch allocation
**2,759,076 bytes**. SQLite cache is 32 MiB; actual peak process RSS is **824,828
KiB (805.5 MiB)**, including native decoder/row-group buffers and geometry work.
The row batch size does not imply that total process RAM is 32 MiB or 2.7 MB.
All 2.6 million rows were streamed; the global table was never materialized.
The disk-backed index is 452,358,144 bytes; the full local candidate CSV is
9,750,417 bytes. Full archive SHA-256:
`77c266ba5a5176d983edca989a81ff73f21c556fd98c82e2131c2f8d172546ce`.

Public [aggregate report](phase12c/report.json), [publisher attribution/receipt
summary](phase12c/publisher_metadata_review.json) and [25-row metadata
sample](phase12c/candidate_metadata_sample.csv) accompany the three coverage CSVs.
The sample uses the first 25 candidate source-row ordinals and is not
representative or independently adjudicated; it omits original/derived geometries
and per-record district intersections. Full register, geometries and potential
cross-inventory links remain protected local research artifacts.

### Validation and preservation

**35 focused extraction tests**, **173 complete root tests** and **1,354 backend
tests passed**, with one existing Starlette/httpx warning. Fixtures are synthetic,
use temporary paths and block network. All **17 retained source validators**
passed, including IFI/GFD/SOI, hydrology, GloFAS, SAR, Udupi history, saved rainfall
and frozen Phase 12A/B. The full **2,646,302-row read-only replay** reproduced every
candidate inclusion/payload and the global exclusion counts. Independent CSV/
SQLite checks reconciled all 19,854 register rows, 31 district totals and 837
matrix rows; every candidate remains review-required and label-ineligible.
Public aggregates/sample match completed local bytes. Completed output hashes
and timestamps remain unchanged; details: [validation summary](phase12c/validation_summary.json).

The initial protection snapshot covered 2,548 files. Excluding the four
authorized existing documentation/log paths, **2,543 files retain exact SHA-256,
size and nanosecond mtime**, including all original scientific data/model files
and `QandA.md`. The remaining environment template changed during the task;
Phase 12C did not edit it, retained its observed contents and excludes it from
Git staging. Its values are not reproduced in receipts or documentation. Earlier
`update.md` bytes remain an exact prefix after the chronological append. No
frontend or operational application changes were made, so no new browser/build
claim is made. Only audit code/tests, this documentation and small permitted
metadata are committed; archive, runtime, full register, geometry and restricted
source records remain ignored/protected locally.
