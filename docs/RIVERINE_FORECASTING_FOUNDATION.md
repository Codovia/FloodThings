# Phase12F: riverine forecasting foundation

**CONDITIONAL for a bounded riverine experiment; current training remains
NO-GO.** A named official data route and substantial retained station histories
exist. Authoritative historical identity/time/datum/method dictionaries,
QC corrections and release records must make those histories usable before an
independent reviewer approves a target and experiment. No model or baseline
was fitted, no forecast feed was activated and no alerts were sent.

Baseline `877fd40b1accd9fb241e291ec082c4c761559e2c`, branch
`feature/karnataka-data-foundation`; source checks12October2026. This follows
[Phase12E](DIRECT_FLOOD_OBSERVATION_ACQUISITION.md) and preserves the12A–12E
NO-GO decisions, satellite evidence, rainfall model and application.
No Groundsource extraction/clustering or new satellite inventory occurred.

## Measured history actually available

The previously reconciled **1,697 rows are a27-day2019 subset**, not the entire
retained hydrological archive. Four already downloaded NWDP files were streamed
without re-download: manual daily discharge301,293 rows, manual hourly level
2,345,277, the separate daily-gauge resource384,732 and telemetry discharge
799,877. Total **3,831,179 source rows** in **587,011,738 retained bytes**;
exact file byte sizes and SHA-256 are in the aggregate
[inventory](phase12f/measured_series_inventory.json). All four match their
original transfer registry. Only exact documented station aliases nominate
candidate histories; these names do not certify a dated CWC-code crosswalk.

**143,381 candidate rows** occur in the manual level/discharge files. Neither
other file matches the reviewed aliases; this is not proof of data absence.

| Candidate station | CWC documentary ID | Variable | Rows | Unique source times | Extra duplicate rows | Conflicting timestamp groups | Naive source time range |
|---|---|---|---:|---:|---:|---:|---|
| Sadalga | CW1KRU000083 | Level | 36,646 | 34,175 | 2,471 | 929 | 9Oct2012–31Dec2020 |
| Sadalga | CW1KRU000083 | Discharge | 6,534 | 6,513 | 21 | 17 | 1Jan2001–31Dec2025 |
| Huvinhedgi / Huvinahedgi | CW1KRU000339 | Level | 35,385 | 32,894 | 2,491 | 218 | 3Jun2004–31Dec2020 |
| Huvinhedgi / Huvinahedgi | CW1KRU000339 | Discharge | 8,961 | 8,893 | 68 | 62 | 1Jan2001–31Dec2025 |
| Gokak Falls, deferred | CW1KRU000212 | Level | 52,185 | 51,367 | 818 | 816 | 1Jan1991–31Dec2020 |
| Gokak Falls, deferred | CW1KRU000212 | Discharge | 3,670 | 3,656 | 14 | 3 | 1Jan2001–25Nov2025 |

There are **5,883 extra duplicate-time rows** and **2,045 time groups with
differing source values**, within each resource/station candidate. Numeric10
and10.0 compare equal; conflicting values are retained, never preferred,
averaged or deleted. These are different categories from the preserved
**33 disagreements in81 NWDP/Year Book reconciliation cases**.

Date ranges overstate continuity. Huvinhedgi's2004 level history has18 rows on
three dates;2012 has53 on three dates, then the series resumes in2013. Sadalga
has53 level rows on three dates in2012. Nominal hourly exports also contain
multiple schedules and gaps. All selected values are finite in the source
screen; numeric validity is not measurement or quality approval.

The [109-entry station/year matrix](phase12f/measured_station_year_coverage.json)
contains every selected source/calendar-year count and distinct source-date
count. Recent level coverage illustrates the observation gaps:

| Year | Sadalga rows / dates | Huvinhedgi rows / dates | Gokak rows / dates |
|---|---:|---:|---:|
|2013|2,319 /101|3,243 /268|2,810 /265|
|2014|3,814 /213|3,880 /220|3,849 /214|
|2015|4,174 /364|4,306 /365|4,181 /364|
|2016|5,033 /366|5,032 /366|5,030 /366|
|2017|6,014 /365|5,081 /365|5,481 /365|
|2018|6,013 /365|6,052 /365|4,710 /343|
|2019|4,370 /352|3,716 /292|4,665 /332|
|2020|4,856 /340|4,004 /266|4,516 /335|

These are **calendar dates without an established observation timezone**, not
complete hourly or flood/non-flood coverage. A365-date year may still lack
the observations required at issue+6h. Expected schedule and detection quality
remain unknown. Public outputs contain counts and aggregate bounds, not
individual values, restricted polygons or station coordinates.

The frozen pilot remains unchanged: Sadalga552 level/27 discharge rows and
two legacy quality-caveated daily rows; Huvinhedgi517/26 and12; Gokak573/2 and
zero. Those14 caveated rows are not14 certified forecast targets. Legacy source
reconciliation eligibility and new scientific forecasting eligibility are separate.

## Shortlist, geography and restrictions

Prioritize **Huvinhedgi on Krishna** and **Sadalga on Dudhganga**. Documentary
identity supports continued investigation, and both have limited GloFAS model-cell
screening support. **Zero canonical dated coordinates are verified.** Sadalga's
published2025/2026 coordinates differ; earlier histories and other source variants
remain unresolved. Gokak's source river identity and east/west model junction
association remain unresolved, so no primary reach/cell is selected there.

The retained2025 SOP provides warning/danger stage levels for the three stations,
but lists them as **monitoring-only**. It does not prove a publicly available
station forecast, level datum compatibility or2013–2020 applicability. Threshold
values and detailed coordinates remain protected locally. No measured discharge
threshold with independently justified flooding significance is established.

Source administrative identities are **Belgaum and Raichur**, not approved
current-LGD or public-directory joins. Verified forecast reaches: **zero**;
verified predictive districts: **zero**. This is a two-station pathway towards
Karnataka-wide riverine prediction, not current statewide skill or coverage.

A future geographic join must retain station code, dated canonical gauge,
verified named river/reach, along-channel segment, source/version/CRS, review and
reuse rights separately from administrative identity. With rights-cleared,
temporally applicable district polygons, intersect the verified **reach line**
with every district, retaining all intersected IDs and boundary ambiguity rather
than assigning one district by nearest centroid. Distinguish gauge administrative
location from reach influence. No flow prediction applies uniformly to localities;
downstream transfer requires routing, tributary/reservoir and hydraulic validation.
Flow alone cannot create street inundation polygons. SOI polygons and reconstructed
derivatives remain ignored/local; the existing public geographic directory and
Flood Map are unchanged.

## Proposed target and independent evaluation

The [target protocol](phase12f/target_protocol.json) is **proposed, not approved**.
The first defensible experiment is **Target A: instantaneous measured stage at
a verified dated gauge, six hours after issue**. Issue00/06/12/18UTC; last
accepted measured input no more than one hour old and demonstrably available
by issue. Stage is in metres in a stable, verified station datum. Do not apply
guessed gauge offsets or interpolate missing targets. Discharge is a distinct
alternative requiring compatible session/statistic/timing; existing daily manual
sessions do not validate instantaneous six-hour discharge or daily means.

**Target B:** whether that future measured stage is **strictly greater than**
the official danger level effective at the same station/date/datum. Warning-level
exceedance has a separate name. Equality is non-exceedance at that instant.
Both fail closed for unverified/rejected/computed/conflicted/missing evidence.
No percentile, historical HFL or model return-period threshold substitutes for
an official effective danger level. Point-time non-exceedance does not establish
absence throughout the following six hours, and neither target certifies
flooded streets or statewide inundation.

Provisional common-history design: train2013-06-01–2017-06-01,
validate2017-06-01–2018-06-01, test2018-06-01–2020-06-01, half-open UTC after
source-time confirmation. These are nominal blocks, not an assertion of adequate
samples. Maximum24-hour baseline antecedents, no random row splits, complete
feature/outcome windows within split, at least24-hour boundary embargo enlarged
to preserve entire flood episodes. Longer AI context requires its own larger
embargo. Independent review must assess usable wet/dry seasons, effective event
count, missingness, observation bias and uncertainty before any fit.

Compare persistence with training-only regularized regression on reviewed stage
lags/change and upstream rainfall. Evaluate held-out MAE/RMSE/bias in original
units, skill against persistence, peak/rising-limb timing and magnitude, with
event-block uncertainty. Target B additionally needs event misses/false alarms,
lead time, precision/recall and probability calibration/Brier scoring. Fit
scalers/feature selection only on training; reserve final test from tuning.

GloFAS is a modelled-discharge reference, not a direct stage baseline. A conversion
needs an independently verified, dated rating curve and uncertainty. The806
retained v5 cell-day rows (13 candidate series,62 steps) are historical model
output, not measured observations or as-issued forecasts; quantitative measured
comparisons remain zero. Current forecast/reforecast overviews listv4.0 while
historical listsv5.0, so native version/grid/schema parity must be proved.
Twenty-four-hour means cannot validate instantaneous stage peaks. A later-generated
reforecast is a labelled retrospective reference, not proof of historical live
availability; examine calibration/training overlap with test station/events.

[OpenHydroNet](https://github.com/google-research/flood-forecasting) is a real
candidate implementation. Current retrieved README describes forecast LSTM
architectures with meteorological hindcast/forecast sequences, measured-discharge
evaluation and catchment attributes. It now describes modular Caravan Zarr
stores while indexed/older documentation mentions NetCDF; pin actual configuration
and revision before use. Code licence is Apache2.0; weight/data rights and local
training/calibration participation need separate review. No package, weights or
forcing archives were acquired. Compatibility with instantaneous six-hour stage
is not established. Pretrained weights would not establish local skill.

## Official forecast access, separately attributed

The [source/access register](phase12f/source_access_review.json) and exact
[retrieval receipts](phase12f/source_receipts.json) record22 pinned metadata
requests capped at2MiB each:19 retrieved, two HTTP failures and one transport
rejection; **1,275,669 accepted bytes**. The first sandbox attempt produced19
connection failures, retained separately; these are not evidence that publishers
lack data. Explicit network access then succeeded. The PIB302 was resolved with
its published explicit language URL. The IMD SOP was not retained by bounded
transport; official browser text was reviewed, with no local checksum claim.
No hydrological archive, model weight or raster was newly downloaded.

| Source | Verified access finding | Geographic/time/rights finding | Integration |
|---|---|---|---|
| CWC FloodWatch | Official public mobile app; reusable documented feed not established in inspected official scope |2024 launch describes592 national monitoring stations,150 reservoirs and up-to-seven-day forecasts; exact current Karnataka forecast-station coverage, issue clocks and machine cadence unknown; CWC content-republication permission required |Blocked pending documented feed and rights |
| IMD flash-flood guidance |2021 SOP describes authorized password-protected interface; current public API reference does not establish dedicated FFG endpoint |Watershed guidance, not measured river forecasts; SOP has hourly FFG/00,06,12,18UTC forecast threat; current feed/cadence/watershed IDs and rights unverified |Blocked pending authorized FFG product access |
| IMD basin-QPF API |Documented `api/v1/basinqpf`, actual unauthenticated HTTP401 |Rainfall forecast, not flood forecast; reference describes issue date but no complete forecast issuance/interval contract |Not substituted for flood integration |
| KSNDMC |Public pages accessible, no documented approved alert machine feed established |Inspected Flood Alerts page describes2022 spells; not fresh issue-time alerts. Current source-area IDs, clocks/cadence/reuse unknown |Blocked pending documented feed and rights |
| Copernicus GloFAS |Documented EWDS authenticated API/terms; WMS-T/SOS describe selected products but inspected child tree cannot load |Global model includes Karnataka domain, daily forecast overview; init/reference time is not availability. CEMS-FLOODS permits attributed display subject to terms/restricted exceptions and informational status |Conditional on legitimate authenticated native request and reach review |

Primary references: [CWC launch announcement](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2044887&lang=2&noshow=1&reg=48),
[CWC copyright](https://cwc.gov.in/en/copyright-policy),
[IMD API reference](https://api.imd.gov.in/public/api_reference.html),
[IMD SOP](https://mausam.imd.gov.in/imd_latest/contents/pdf/hydrology_sop.pdf),
[KSNDMC flood page](https://ksndmc.org/en/Media/Flood),
[EWDS forecast overview](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview),
[reforecast overview](https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast?tab=overview),
[historical overview](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview),
[CEMS-FLOODS licence](https://ecds.ecmwf.int/licences/cems-floods) and
[web-service description](https://confluence.ecmwf.int/spaces/CEMS/pages/242067472/Web+Services).

The current user `.cdsapirc` file **exists**, unlike the earlier checkpoint;
its contents, validity and terms acceptance were not inspected and no authenticated
request occurred. Do not repeat the old absent-configuration finding as current.
EWDS account owners must confirm applicable terms before a version-pinned native
request. Record actual schema, two supported cells, few dates/members, expected
bytes and space before acquisition; substantial transfers still need approval.

**Zero live integrations are implemented.** No verified source feed currently
satisfies access, original forecast receipts, station/reach semantics and display
requirements. The new **offline receipt validator defaults disabled** and checks
source class, rights/access/geo review, original hash/ID/version, timezone-aware
issue/availability/retrieval/valid/expiry and reviewed freshness. It has no network
endpoint or production router and never sends alerts. A future approved adapter
must be read-only, source-flagged, preserve original provenance, show unavailable
on failure/staleness and distinguish official river forecasts, external modelled
forecasts, evaluated local AI and historical observations. No hidden mobile
interface was scraped and no forecast endpoint invented.

## Exact next evidence and reproducibility

The [unsent CWC request](phase12f/CWC_STATION_DATA_REQUEST.md) names the two station
codes, existing resource IDs, proposed2013–2020 window, field dictionaries,
gauge/threshold history, QC corrections and original release records. The retained
2018 policy §6.2 names a specific obtainable-data route through the Chief Engineer
KGBO; confirm current procedure, then request missing documentation or
station-filtered QC augmentation, **not another full archive**. No new arbitrary
search or weight download can replace these records.

The [predictor matrix](phase12f/predictor_availability_matrix.json) separates
measured stage/discharge lags, upstream observed rainfall, archived issued NWP/QPF,
modelled historical/reforecast GloFAS, reservoir releases and static catchment
context. **Zero complete historically available feature rows** are established.
Publication/retrieval dates cannot be substituted for historical measurement
availability; later reanalysis cannot silently become issue-time input.

Reusable code: bounded-source acquisition, streaming station-history inventory,
observation/pair/threshold/source-forecast gates and deterministic public/local
audit. Validators check supplied evidence, not its authenticity; independent
scientific approval is still mandatory. Original raw products and failed receipts
remain ignored, unchanged and source-hashed. Detailed measurements, source
government geometry and credentials are not published.

```sh
python3 -B scripts/acquire_riverine_source_metadata.py validate
python3 -B scripts/inventory_riverine_station_series.py validate
python3 -B scripts/audit_riverine_forecasting.py validate
backend/.venv/bin/python -B -m pytest -q tests/test_riverine_forecasting.py
```

Build commands refuse existing versions. Inventory replay streams the originals
with a32MiB SQLite cache/file temp store and bounded Python aggregates; no global
CSV is loaded into RAM. A fresh checkout without protected sources cannot verify
local scientific evidence and must not manufacture it. The public
[report](phase12f/report.json) records **zero eligible measured targets, future
pairs, threshold positives/negatives, metrics, fits and verified predictive
districts**. The conditional pathway does not lift the training NO-GO.

## Validation and preservation

**53 focused scientific/streaming safety tests and317 complete root research
tests passed.** Backend regression: **1,353 passed, one actual model-fitting
reproduction test deselected, one existing Starlette/httpx deprecation warning**.
All **24 source checks passed**, including the21 prior read-only validators,
Phase12F metadata integrity and both deterministic replays. No global news
extraction, source rewrite or model fit is part of these checks.

The initial snapshot covers **2,961 existing files**: tracked paths, `QandA.md`
and existing data files, excluding runtime/cache directories and new Phase12F
outputs. SHA-256, size and nanosecond mtime verification allows only `README.md`
and the chronological `update.md` append. Unrelated `backend/.env.example` and
`QandA.md`, research originals/manifests/model artifacts and existing application
files remain exact. Test and source-check summaries are in
[validation_summary.json](phase12f/validation_summary.json); detailed logs,
initial plans, failed receipts and byte-preservation checks remain ignored in
`data/recovery/phase12f_v1/`.
