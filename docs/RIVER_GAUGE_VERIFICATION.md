# Phase12G: what the retained river gauges can support

**CONDITIONAL on specific CWC documentation/corrections; current forecasting
training remains NO-GO.** There are **zero scientifically eligible forecast
pairs**, compatible official flood thresholds or flood-positive/negative labels.
No model, baseline or statistical estimator was fitted. Neither target nor
evaluation has been approved. The existing rainfall model, application and flood
map are unchanged; this is a two-gauge Karnataka research pathway.

Baseline `6df2514171ef6a28130e4f83db4aa843f27de389`, branch
`feature/karnataka-data-foundation`; review12October2026. This follows the
[Phase12F foundation](RIVERINE_FORECASTING_FOUNDATION.md) and preserves all
Phase12A–12E NO-GO decisions and hydrological restrictions.

## Native observations and frequency

Only the **two already-retained manual NWDP archives** were streamed for Sadalga
and Huvinhedgi. Neither the other two archives, global Groundsource nor new
satellite data were inventoried. No source download occurred. The two original
files total **434,102,798 bytes**, with their prior transfer SHA-256/size intact;
[source register](phase12g/source_register.json) records dataset/resource IDs and
exact original field names. The candidate subset contains **87,526 rows**:
72,031 stage and15,495 discharge. Deferred Gokak is outside this analysis.

Every selected timestamp is literally **`DD-MM-YYYY HH:MM`**, without a timezone:
87,526 minute-precision strings, zero date-only or malformed selected timestamps.
The parser preserves date-only precision if encountered; it does not fabricate
midnight. `Data Acquisition Time` is not proven to be observation time rather
than a session/entry/aggregation boundary. No UTC/IST conversion is applied.
All original fields, strings, row ordinals and conflicting values are preserved
in the ignored local native register, with resource ID and source SHA-256.

| Station / candidate documentary code | Variable | Rows / unique native times | Native coverage | Extra duplicates / conflicting times |
|---|---|---:|---|---:|
| Sadalga `CW1KRU000083` | Stage |36,646 /34,175|9Oct2012–31Dec2020|2,471 /929|
| Sadalga | Discharge |6,534 /6,513|1Jan2001–31Dec2025|21 /17|
| Huvinhedgi `CW1KRU000339` | Stage |35,385 /32,894|3Jun2004–31Dec2020|2,491 /218|
| Huvinhedgi | Discharge |8,961 /8,893|1Jan2001–31Dec2025|68 /62|

Counts agree with the preserved Phase12F inventory. Duplicate counts are extra
rows within one resource/station/native timestamp. Conflict counts are groups
with more than one Decimal-normalized value;10 and10.0 agree numerically.
Same-valued duplicate rows remain duplicated, and **no conflicting value is
preferred, averaged, interpolated or discarded**. All selected numeric values
pass a finite-value screen; this supplies no measured/computed or QC approval.
Stage and discharge are kept separate, including their separate clocks/statistics.

The level header reports **manual hourly, meter**; discharge reports **manual
daily, m3/sec**. The official [2018 policy](https://www.cwc.gov.in/sites/default/files/hddp2018_0.pdf)
§2.1.3, PDF3, describes general hourly monsoon stage,08:00/13:00/18:00 non-monsoon
stage and daily discharge. Its next section explicitly allows non-uniform
water-level intervals and observed/interpolated/extrapolated discharge. These
general rules do not identify the exact export's seasonal dates, clock or method.
The retained handbook/Year Book explain gauge references, measurement sessions
and computed/discarded flows, but an exact NWDP field/QC dictionary remains absent
from the reviewed evidence. [Source review](phase12g/source_review.json) records
both the evidence and limits of the bounded current browser checks.

Consecutive intervals below use **chronologically sorted unique minute-precision
source times**, never CSV row order or repeated timestamps. Whole-series intervals
include all gaps; year diagnostics separately expose cross-year gaps, assigned
to the later reading's year. Calendar dates lacking any row are coverage counts,
not counts of missed scheduled observations or non-flood dates.

| Stage timing diagnostic | Sadalga | Huvinhedgi |
|---|---:|---:|
| Unique adjacent intervals |34,174|32,893|
|1h intervals|30,424|28,993|
|5h intervals|2,322|2,546|
|14h intervals|1,155|1,262|
|Intervals outside those three general-policy gaps|273|92|
|Intervals longer than24h /7days|13 /3|16 /8|
|Largest interval, minutes|360,720|4,389,180|
|Distinct dates with any stage row|2,469|2,513|
|Dates without any row between source bounds|537|3,543|
|Days with exactly24 integer-hour times|1,059|1,182|
|Days with exactly08/13/18 only|1,150|1,264|
|Days with other observed clock patterns|260|67|

All selected stage times fall on integer hours; no half-hour readings occur.
Mixed schedules are real source structure, but “24 times on a date” does not
certify observational completeness or QC. Huvinhedgi has only18 stage rows on
three dates in2004, no stage rows in2005–2011,53 on three dates in2012, then
resumes in2013. Sadalga2012 likewise has53 rows on three dates. Later years
have partial-day gaps even when365/366 dates are represented. Stage missingness
must be evaluated against a producer-confirmed station/year schedule.

Discharge is not an hourly-stage substitute. Sadalga has5,623 exact24h intervals
among6,512 adjacent unique times; Huvinhedgi has5,144 among8,892. Other intervals
include shifting08:00/09:00/08:45 session clocks and intraday entries. There are
448 and1,711 intervals over24h respectively, with5 over7days at each station.
Their dates lacking any record between source bounds are2,619 and484. These
are observed gaps, not established failures of a validated daily schedule or
proof that the field is a daily mean. The [year coverage](phase12g/station_year_coverage.json)
includes all discharge years and empty intervening stage years.

## Exact future-match feasibility

The [pair-year matrix](phase12g/forecast_pair_year_feasibility.json) records issue
counts, latest available **source-clock** history, exact future matches, missing
diagnostic lags, duplicates/conflicts and temporal/QC/availability uncertainty.
The private candidate register contains actual native candidate issue/target
strings and all original input/target/lag row references; it contains no preferred
conflict value and no approved label. Future targets and antecedents can cross
a year boundary; counts are assigned to **issue year**, not an approved data split.

Two **diagnostic** issue rules are compared:

- **Native grid:**00/06/12/18 on the unverified source clock between first/last
  minute-precision readings, including periods with no input. Use the latest
  prior reading only if its age is≤1h; a conflicted latest reading is retained,
  without falling back to a cleaner older value. Exact future issue+6h/+24h is
  mandatory; there is no interpolation or nearest-future matching.
- **Reading-time issues:**one hypothetical issue at every unique native stage
  time. This exposes the archive structure but assumes instantaneous availability
  for counting; **actual release at issue is unknown**, so these are not live or
  historically eligible forecast cases.

| Station | Issue rule | Candidate issues | Structural +6h /+24h pairs | Singleton finite +6h /+24h pairs | Eligible |
|---|---|---:|---:|---:|---:|
|Sadalga|Native grid|12,020|4,912 /6,029|4,188 /5,196|0|
|Huvinhedgi|Native grid|24,223|4,829 /6,077|4,182 /5,242|0|
|Sadalga|Reading time|34,175|30,334 /33,762|28,146 /31,251|0|
|Huvinhedgi|Reading time|32,894|28,776 /32,438|26,836 /29,931|0|

“Structural” requires a≤1h prior/current reading and an exact future timestamp,
irrespective of their QC or value conflicts. Singleton finite removes duplicate
input/target rows as a conservative diagnostic, without declaring them approved.
For grid+6h,257 Sadalga pairs and79 Huvinhedgi pairs involve value conflicts;
724 and647 involve duplicates of either kind. These categories overlap.
Corresponding grid+24h conflicts are341/118 and duplicates833/835.

Only6,325/6,160 grid issues have a≤1h input. An exact+6h future reading exists
at6,095/6,150 grid issues, but that alone does not establish an input/target pair.
The matrix keeps these counts separate. Missing future matches include internal
gaps and targets beyond the retained archive end; neither is a negative outcome.
No release log or historical latency rule establishes any input as available
at its issue, regardless of a successful native-clock match.

Additional **diagnostic**, unapproved lags are exact issue−1h/−6h/−24h. For
grid+6h,4,420/4,725 structural pairs have all three timestamps;492/104 lack one
or more. Requiring singleton finite current/target/all-three-lag groups leaves
3,338/3,780; grid+24h leaves3,890/4,082. These are **still scientifically
ineligible**. Persistence only needs the reviewed current input, so absence of
the three richer diagnostic lags is reported separately, not used to inflate
or redefine its requirements. Upstream observed rainfall, reservoir timing and
archived issue-time forecast features remain unavailable/uncertified for pairing;
the806 GloFAS rows remain modelled discharge rather than measured stage.

The Phase12F proposal used **00/06/12/18 UTC**, which is not this native grid.
**Zero issue times are verified for that UTC proposal.** If CWC later confirms
the native clock as IST, those UTC issues would be05:30/11:30/17:30/23:30 native;
both+6h and+24h targets would then fall on half-hours absent from these stage
histories. That conditional clock calculation is not an assignment of IST.
It shows why issue-time review must precede selecting or interpolating targets.

## Target alternatives and first-experiment requirements

| Proposed target | Operational meaning | What these histories support | Current review |
|---|---|---|---|
|Six-hour instantaneous stage|Point river level six hours after an actual forecast issue|Many exact reading-issued matches in denser regimes; native-grid matches substantially fewer; source timezone/release and original UTC grid unresolved|Proposed, NO-GO for fitting|
|Twenty-four-hour instantaneous stage|Next-day point level, not next-day maximum or flooding throughout the interval|More same-clock matches and sparse-regime coverage; same timing/datum/QC blockers; may miss rapid peaks between readings|Alternative for scientific review, not approved|
|Producer-scheduled next reading|Known next observation time, e.g.1h monsoon or5h/14h outside monsoon|Observed mixed cadence; exact scheduled examples exist, but dated station schedule and availability must be confirmed|Alternative for review; never predict the retrospectively selected “next row”|

Fixed-lead diagnostics at all reading clocks yield30,424/28,993 +1h matches,
32,674/31,353 +5h matches and31,373/29,796 +14h matches. Those5h/14h totals also
include dense-regime clocks. Restricting+5h to08:00/13:00 produces **4,901/4,990**
matches out of4,917/5,005 hypothetical issues; restricting+14h to18:00 produces
**2,442/2,482** out of2,457/2,501. All eligible counts remain zero.
[Cadence feasibility](phase12g/reported_cadence_feasibility.json) separates these
two denominators rather than counting every5h match as a non-monsoon session.

Keep six-hour stage as the candidate to assess after the dictionary response.
There is no evidence-based reason yet to approve a new target. A next-day target
would serve slower river-level planning; an hourly target would serve frequent
rising-limb monitoring where the documented regime supports it. A scheduled-reading
experiment must specify lead and issue **before** seeing the target, report5h
and14h performance separately and acknowledge the overnight blind interval.
Do not choose an alternative merely because its match count is larger.

Both stations are **CONDITIONAL**, with training **NO-GO**, until these exact
prerequisites pass independent review:

1. Official dated source-name/code/site crosswalk, stable gauge/cross-section
   identity and measurement clock/time role, season/year schedule and statistic.
2. Metre units and stable historical stage datum with benchmark/zero changes;
   no inferred conversion from `RL_of_zeroGauge` or `MeanSeaLevel`.
3. Record-level measurement/QC flags, approved duplicate/conflict correction
   lineage and enough accepted measured observations, across rising limbs and
   seasons. Finite numeric values and equal duplicates are insufficient.
4. Historically applicable input release records/latency and final-target revision
   provenance. A forecast issue must follow actual input availability and retain
   its precise horizon; observation timestamps alone cannot prove this.
5. Resource-specific research/reuse permission and **explicit user approval** of
   an independently reviewed target/evaluation protocol before any model fit.

Start with persistence and a simple training-only statistical baseline. Preserve
the proposed chronological train/validation/test blocks as **unapproved** until
quality/season/event adequacy is measured. Keep all feature/outcome windows inside
their splits, at least24h embargo for a24h antecedent baseline and whole-event
purging; revise the embargo for a longer horizon/context. Test MAE/RMSE/bias,
persistence-relative skill, rising-limb/peak timing and event-block uncertainty.
Do not tune on the final test or count correlated readings as independent floods.
No model skill, metric or sample sufficiency is claimed here.

## Official thresholds, geography and data request

The retained [April2025 SOP](https://cwc.gov.in/sites/default/files/sopapril2025.pdf)
has official stage warning/danger columns in metres, table headed on PDF23, with
Sadalga and Huvinhedigi monitoring entries on PDF38. Visual review and current
official browser text corroborate those rows. However, the threshold rows lack
current CWC station codes and do not establish the gauge datum or effective
2013–2020 threshold history. Existing cross-publication HFL differences remain
unreconciled. [Threshold evidence](phase12g/threshold_evidence.json) records these
limitations: **zero compatible thresholds and zero exceedance comparisons**.
Detailed values/source tables remain protected locally. Stage prediction must
remain a **river-level forecast**, without an effective compatible official
threshold; point-time non-exceedance does not prove non-flood conditions.

Historical identity is strongly supported by official names/agency/river/basin
and history, but an authoritative dated code/coordinate crosswalk remains absent.
Sadalga on Dudhganga has Belgaum source identity; Huvinhedgi on Krishna has
Raichur source identity. Existing coordinate variants and geographic licensing
restrictions are preserved. These are **not approved current district/reach joins**;
verified predictive geographic units remain zero. There is no statewide skill
claim, district-wide flow assignment or inundation-polygon reconstruction.

The [earlier CWC request](phase12f/CWC_STATION_DATA_REQUEST.md) covers the main
unresolved questions. The [final unsent text](phase12g/CWC_REQUEST_FOR_REVIEW.md)
and [submission checklist](phase12g/SUBMISSION_CHECKLIST.md) add exact dataset IDs,
field names, conflicts and sparse-history questions. The2018 policy§6.2 names
the concerned Chief Engineer for missing unclassified data; Annex I identifies
KGBO for Krishna/Godavari, with§6.4 offering the RTI route. Current routing/user
category/applicable policy must be reconfirmed. The retained2026 policy's Final
Draft status is not interpreted as enacted supersession. Browser access to the
current CWC metadata index returned401; no working current contact is invented.

The specific requested augmentation is a **two-station dictionary + dated gauge
history + QC/correction table + historical release/latency evidence**, with
resource IDs `7778f459-0e82-4681-9638-5e494c36fd42` (level) and
`f95150ea-c8fc-4740-8815-d9c34c9d53a3` (discharge). The request does not seek
another basin-wide archive. It is prepared for the user's review, **not sent**.

## Reproduction and protection

```sh
python3 -B scripts/verify_river_gauge_histories.py validate
# Optional focused extraction-completeness replay of the two resources:
python3 -B scripts/verify_river_gauge_histories.py validate --replay-raw
backend/.venv/bin/python -B -m pytest -q tests/test_river_gauge_verification.py
```

Build refuses an existing version. The first extraction streams both original
CSVs once and preserves only the two selected station histories. The candidate
subset is bounded at100,000 rows, each series at50,000 native times; pair JSONL
is streamed. No global CSV is loaded into RAM. Replay uses the bounded private
subset plus whole-file original fingerprints; optional raw replay verifies exact
selection completeness. Diagnostic refinements reused that subset. Original
archives, failed/retrieved source receipts and previous reports remain immutable.

`data/working/river_gauge_verification_phase12g_v1/native_observations.jsonl`
holds all original fields/values; `native_forecast_candidates.jsonl` holds exact
native candidates and all row references. Both are ignored, local-only derived
research records, **not certified training pairs**. No restricted measurement
values, station coordinates, SOI polygons/derivatives or credentials are committed.
Public products contain aggregate counts, bounds, clock/interval histograms and
provenance. Missing records and news silence never become negative labels.

Validation/protected-file results are recorded in
[validation summary](phase12g/validation_summary.json). Exact nanosecond mtime,
size and SHA-256 checks cover3,123 pre-existing files; only the README research
link and chronological root `update.md` append may differ. Original research
datasets, models, application files, unrelated `backend/.env.example` and
untracked `QandA.md` remain unchanged.

**31 focused native-clock/interval/conflict tests and348 complete root research
tests passed.** Backend regression: **1,353 passed, one actual model-fitting
reproduction test deselected, one existing Starlette/httpx deprecation warning**.
All **24 source checks passed**:23 preserved read-only validators plus the
Phase12G aggregate/private-register replay and focused two-resource extraction
completeness check. The previous four-resource full inventory was not rerun;
its selected counts and source fingerprints were cross-checked instead. No
source rewrite, live alert or model fit occurs in these checks. Logs remain in
ignored `data/recovery/phase12g_v1/`.

## Station/year readiness matrix

All native-clock matches below remain unverified for timezone, datum, QC and
issue-time availability. Empty years are retained; no readings or labels are
filled. The full JSON matrix also supplies both issue rules/horizons, past-lag
coverage, missing targets, duplicates/conflicts and every discharge year.

### Sadalga stage calendar years

| Year | Rows | Unique native times | Observed dates | Extra duplicates | Conflicting times | Native-grid issues | Grid +6h pairs | Reading-issued +6h pairs | Reading-issued +24h pairs | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2012 | 53 | 53 | 3 | 0 | 0 | 332 | 7 | 47 | 29 | 0 |
| 2013 | 2319 | 2319 | 101 | 0 | 0 | 1460 | 303 | 2214 | 2295 | 0 |
| 2014 | 3814 | 3814 | 213 | 0 | 0 | 1460 | 605 | 3621 | 3785 | 0 |
| 2015 | 4174 | 4174 | 364 | 0 | 0 | 1460 | 490 | 3420 | 4142 | 0 |
| 2016 | 5033 | 4939 | 366 | 94 | 88 | 1464 | 731 | 4386 | 4916 | 0 |
| 2017 | 6014 | 4944 | 365 | 1070 | 810 | 1460 | 733 | 4390 | 4918 | 0 |
| 2018 | 6013 | 4939 | 365 | 1074 | 26 | 1460 | 730 | 4387 | 4917 | 0 |
| 2019 | 4370 | 4137 | 352 | 233 | 5 | 1460 | 581 | 3482 | 3940 | 0 |
| 2020 | 4856 | 4856 | 340 | 0 | 0 | 1464 | 732 | 4387 | 4820 | 0 |

### Huvinhedgi stage calendar years

| Year | Rows | Unique native times | Observed dates | Extra duplicates | Conflicting times | Native-grid issues | Grid +6h pairs | Reading-issued +6h pairs | Reading-issued +24h pairs | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2004 | 18 | 18 | 3 | 0 | 0 | 847 | 6 | 9 | 12 | 0 |
| 2005 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2006 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2007 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2008 | 0 | 0 | 0 | 0 | 0 | 1464 | 0 | 0 | 0 | 0 |
| 2009 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2010 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2011 | 0 | 0 | 0 | 0 | 0 | 1460 | 0 | 0 | 0 | 0 |
| 2012 | 53 | 53 | 3 | 0 | 0 | 1464 | 7 | 47 | 29 | 0 |
| 2013 | 3243 | 3243 | 268 | 0 | 0 | 1460 | 460 | 2762 | 3116 | 0 |
| 2014 | 3880 | 3880 | 220 | 0 | 0 | 1460 | 613 | 3674 | 3856 | 0 |
| 2015 | 4306 | 4306 | 365 | 0 | 0 | 1460 | 611 | 3667 | 4281 | 0 |
| 2016 | 5032 | 4941 | 366 | 91 | 3 | 1464 | 732 | 4387 | 4920 | 0 |
| 2017 | 5081 | 3990 | 365 | 1091 | 188 | 1460 | 555 | 3175 | 3936 | 0 |
| 2018 | 6052 | 4975 | 365 | 1077 | 19 | 1460 | 739 | 4424 | 4933 | 0 |
| 2019 | 3716 | 3484 | 292 | 232 | 8 | 1460 | 495 | 2965 | 3386 | 0 |
| 2020 | 4004 | 4004 | 266 | 0 | 0 | 1464 | 611 | 3666 | 3969 | 0 |
