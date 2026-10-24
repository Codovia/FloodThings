# Prediction-time feature methodology — Stage 5

Status: **ml_training_not_ready**. This is a completed methodology review,
not a training dataset or a fitted model. The create-only local product is
`data/working/karnataka_prediction_methodology_v1/`; its reviewed public
metadata is `data/reference/karnataka_prediction_methodology_v1/manifest.json`.

## Prediction question and unresolved definition

The original specification, QandA §6 FR1–FR5, requests district
Low/Medium/High risk, locality refinement, seven daily weather-forecast days
and six-hourly alerts. It does not define whether the outcome is flood
occurrence, impact severity or susceptibility; the issue/valid intervals,
class boundaries and geographic aggregation are also undefined. Its older
completion claims and proxy/synthetic assumptions conflict with the current
README and the verified rebuild. They are not implementation evidence.

The working application retrieves a three-day weather forecast for Bengaluru.
It does not predict risk for 31 districts or verified localities. Provider
lead-time capacity does not establish a flood target. The review assesses a
calendar forecast day within the requested seven-day span and the seven-day
aspiration, without selecting either. The primary horizon is null:
**prediction_horizon_not_yet_trainable**. No new 6/12/48/72-hour target is assumed.

## Availability contract

The canonical register has 37 candidates, including exclusions. Every row
has units, spatial/temporal resolution, source class, latency, availability,
operational counterpart, parity, licence, quality and permission fields.
The taxonomy is STATIC, OBSERVED_PAST, FORECAST, MODELLED_PAST,
RETROSPECTIVE_ONLY, DESCRIPTIVE_ONLY, TARGET_OR_LABEL, UNRESOLVED or EXCLUDED.
There are no confirmed OBSERVED_PAST prediction candidates in this checkout;
the taxonomy does not require inventing an example for every class.

At issuance T, a future feature must retain independently supported first
availability, retrieval, initialization and valid-interval clocks. Publication
must precede T; elapsed observations/modelled intervals must end by T.
Forecast initialization and delivery must precede T even when the forecast
valid interval follows T. Static product/vintage must already exist at T.
All clocks need explicit offsets; a source's undocumented timezone cannot
default to IST. Retrieval is not observation, publication or initialization.
Source/model/geometry versions, masks, units and ensemble members remain explicit.
Calendar-day precipitation totals are not automatically preceding-24-hour rain.

The offline `asof_input` function tests this future contract; it does not
approve a feature, calculate values or assemble a training matrix. Stage 5
approves **zero training features**. The three deployable rows refer solely
to dated research layers already displayed by the application.

## Rainfall

[CHIRPS v2 documentation](https://wiki.chc.ucsb.edu/CHIRPS2_FAQ) places Final
release in the third week of the following month. Preliminary release two
days after a completed pentad is a different product. Neither establishes
same-day Final availability. The retained 0.05° daily mm/day district/scope
means are useful retrospective research, not locality gauges. Strict
pre-event dates in Stage 3C/3D prevent event-window leakage but do not prove
the Final values were available at those anchors. Event-window rainfall
remains **DESCRIPTIVE_ONLY_NOT_PREDICTION_FEATURE**.

The [producer](https://chc.ucsb.edu/data/chirps/) plans to end v2 production
after December 2026. A transition to v3 needs a separate version/parity
review; no automatic substitution is authorized.

[Open-Meteo historical weather](https://open-meteo.com/en/docs/historical-weather-api)
provides reanalysis, including ERA5 and ERA5-Land, with a stated five-day
delay. IFS historical analysis is a different model product. No retained
Open-Meteo historical extraction was found in this checkout; that capability
is catalogue verified only. [Live forecasts](https://open-meteo.com/en/docs)
and current model estimates differ from reanalysis. The existing adapter
preserves valid times and retrieval time, but its forecast issue time is
null and it does not retain pinned model-run snapshots.

[Stitched historical forecasts](https://open-meteo.com/en/docs/historical-forecast-api),
[fixed-lead previous runs](https://open-meteo.com/en/docs/previous-runs-api)
and [initialization-pinned single runs](https://open-meteo.com/en/docs/single-runs-api)
are distinct archives. Single IFS runs begin 14 March 2024; other single-run
archives begin 2 April 2026. Model initialization is not first delivery.
No confirmed precipitation forecast archive covers the four positive
2005–2010 anchors. Matching JSON formats is not training/serving parity.

[Open-Meteo terms](https://open-meteo.com/en/terms) distinguish CC BY 4.0 data
from the hosted free service's noncommercial use and request limits. A data
licence does not grant an operational service guarantee or resolve model
distribution differences.

## Hydrology

Stage 4F restrictions remain unchanged: supported Sadalga/Huvinhedgi model
cells have spatial/calibration caveats; Gokak has no canonical cell. The CWC
coordinate conflicts, NWDP temporal semantics, water-level datum, revision
and reuse uncertainties remain separate. Preserve 1,697 measured records,
81 reconciliation cases, 14 quality-caveated eligible rows and 33 unresolved
disagreements. Quantitative CWC/GloFAS comparisons stay prohibited.

The retained [GloFAS historical](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview)
v5 consolidated simulation uses ERA5 and is retrospective. Its 2019
values did not exist as this v5 product in 2019. The catalogue distinguishes
monthly consolidated updates from daily ERA5T intermediate updates; neither
frequency establishes exact product publication latency.

[GloFAS forecasts](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview)
use NWP ensembles and list v4, daily initialization and a 30-day EWDS series.
The documented discharge archive starts 5 November 2019, after the pilot's
August flood period. [Current forcing documentation](https://confluence.ecmwf.int/spaces/CEMS/pages/265028598/GloFAS+meteorological+forecasts)
distinguishes 15-day medium-range and 46-day subseasonal products from this
legacy download series. Global geographic scope includes Karnataka, but
local flood relevance, reliable delivery and model/static-version parity
still need verification. The official download form's time-critical-use
advisory is retained as web-page evidence, not a delivery guarantee.

Official pages disagree on v5 status: the retrieved historical catalogue
calls v5 operational (15 July 2026), while the
[29 July API note](https://confluence.ecmwf.int/spaces/CEMS/pages/699325478/Changes+to+the+EWDS+API+Request+to+download+GloFAS+Historical)
calls it pre-operational/testing and v4 operational; the forecast catalogue
lists v4. No source is silently preferred and no version is substituted.
Operational v5 forecast parity is unresolved.

[Reforecasts](https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast?tab=overview)
are later-created hindcasts, not proof of forecasts issued historically.
Any future use needs version-matched forcing/initialization, causal
availability and calibration-overlap review. The original historical
preceding-24-hour mean and UTC period-end timestamps remain unchanged.
Modelled hydrology never replaces measured gaps or acquires measured status.
CEMS-FLOODS terms and static-map licences remain source specific.

## Existing spatial context and labels

SAFE_NOW is limited to the existing 3 km Udupi research window: Copernicus
DSM elevation, its Horn slope and dated 2021 WorldCover. They are available
as current research context, not a validated statewide flood feature set.
[Copernicus GLO-30](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1)
is a surface model with EGM2008 vertical reference, not underground drainage
or bare-earth flow verification. Its 2010–2020 acquisitions and 2024 edition
cannot silently describe the 2005–2009 surface. [WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200)
describes 2021, not current land cover or the older events. Attribution and
adaptation notices remain attached to existing layers.

Version-compatible GloFAS network context and public reviewed boundaries
are validation candidates. Restricted SOI geometry, its rainfall statistics
and current-LGD identities remain local/unresolved under repository policy.
No new river proximity, reservoir, locality profile or drainage-capacity
feature is proposed without data. Zero returned OSM drain/ditch geometries
means unknown infrastructure coverage; [ODbL](https://www.openstreetmap.org/copyright)
does not supply missing measurements. Full-history JRC occurrence contains
future information relative to earlier events and has no static exemption.

Four [GFD](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)
event scopes retain qualifying non-permanent floodwater: 2728 Udupi 33,
3551 Udupi 23, 3652 Chitradurga 2, 2758 Kolar 329. They span three regions,
with two Udupi events, and describe event-window maxima rather than daily
onset/occurrence. The two-cell Chitradurga evidence retains its limited
spatial strength. Observed-zero maps 2698/3107, absent IFI records, missing
or unusable observations and arbitrary background dates do not certify
non-flood. All existing binary training targets remain null. IFI reports,
post-event SAR/NRSC diagnostics and GFD pixels remain outcome/context evidence,
never predictors. No Sentinel-1 diagnostic is promoted. GFD/IFI CC BY-NC
conditions do not authorize unrestricted commercial/model redistribution.

## Decision and next stage

| Dimension | Result | Remaining requirement |
| --- | --- | --- |
| Feature readiness | LIMITED | Only dated local static context is approved now |
| Labels | NOT_READY | Independently dated outcomes and defensible comparison evidence |
| Temporal alignment | NOT_READY | Define target intervals and demonstrate first availability |
| Training/serving parity | NOT_READY | Validate one pinned operational product and historical counterpart |
| Licence/deployment | UNRESOLVED | SOI/CWC and source-specific derivative/service rights |
| Sample size | NOT_READY | Four dependent, selectively reviewed scopes cannot support risk classes |

SAFE_AFTER_VALIDATION comprises pinned operational weather/forecast archives,
version-matched operational hydrology and compatible static context.
RESEARCH_ONLY includes delayed CHIRPS Final antecedents, reanalysis,
consolidated historical GloFAS, unresolved measured records and restricted
geometry. PROHIBITED includes post-anchor event rain/peaks/outcomes as
inputs, canonical Gokak, unsafe CWC/model alignment, datum thresholds,
invented infrastructure and absence-derived negatives.

Recommend **Stage 5A: bounded operational-source and issuance-preserving
archive validation, with an explicit outcome/geographic/horizon protocol**.
In parallel in the scientific plan, develop independently time-resolved
flood-positive/comparison evidence in a compatible archive period. Include
upstream catchments across state borders when specifying hydrological units.
Do not assemble a training matrix or fit a model until those gates pass.

## Reproduction and preservation

Twenty bounded, unauthenticated official documentation responses and their
unchanged bytes, HTTP receipts, retrieval times and SHA-256 hashes remain
local under `data/raw/reference/stage5_v1/`. Catalogue availability is not
data retrieval; Stage 5 downloads no environmental observations.

`scripts/.venv/bin/python -B scripts/review_prediction_availability.py build`
creates a new version and refuses an existing one. `validate` reproduces
all JSON bytes read-only, checking original documentation, input, processing
code and output hashes plus prior Stage 4F safeguards. `publish-metadata`
uses exclusive creation and publishes only own methodology, source references,
checksums and aggregate statuses. Raw source pages, restricted geometry,
measured values and detailed rainfall/model tables stay local.

Offline tests use controlled temporary fixtures and cover taxonomy, leakage,
timezone, publication evidence, measured/modelled separation, permissions,
null labels and immutable/read-only reproduction. Existing dataset validators
and a starting-file hash/size/nanosecond-mtime inventory independently guard
the frozen research data and application files.
