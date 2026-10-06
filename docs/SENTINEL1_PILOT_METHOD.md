# Sentinel-1 pilot method (Stage 3E)

**Stage 3E2 correction (2026-10-06):** the v1/v2 method below is an archived
specification. Its GlobalSurfaceWater mask gate incorrectly excluded otherwise
usable SAR observations. The old `extract` entry point is disabled; its evaluator
is retained unchanged solely to reproduce the failed v1 and completed v2.
Use `scripts/.venv/bin/python scripts/verify_jrc_auxiliary.py diagnose` or
`validate` for independent auxiliary diagnostics. No new flood classification is
authorized by the mask repair.

This is a feasibility/calibration experiment, not a validated flood map, label
or operational product. GFD counts and rainfall contexts remain separate.

Use `scripts/.venv/bin/python -B scripts/verify_sentinel1_pilot.py coverage`,
then `metadata`, then `extract`; `validate` is read-only and offline. Completed
versions cannot be overwritten. Retained metadata/tile journals permit bounded
recovery before a completed version exists. Partial failures preserve completed
records and identify unreviewed IDs in the manifest; they are not missing rainfall
or flood-negative observations. All detailed outputs remain local.

## Selection and scope

Live Karnataka coverage uses the retained public geoBoundaries ADM1 source ID,
not SOI. Offline IFI filtering preserves original dates/names/codes and requires
valid windows inside actual catalogue coverage. There are no current-LGD guesses.
The pilot rank prefers a new year, new exact public district, earlier start and
original ID. Only unique exact single district tokens, Karnataka-only windows
<=31 days and a full 45-day pre-event search inside coverage are eligible.
Initial three metadata candidates extend to five when pairs are unavailable;
no SAR outcomes influence selection. All unselected/rejected rows are retained.

Each scope is a deterministic 2 km square around the public district polygon's
Shapely representative point, snapped to EPSG:32643 10 m cells. This point is
**not an independently located flood site**. Local cell-centre clipping to the
public polygon prevents out-of-district counts. The square is not an official
boundary or complete event footprint. No SOI geometry is uploaded. A no-signal
result in this tiny window cannot describe the whole reported district/event.

## Acquisition and masks

Use actual IW 10 m VV/VH scenes, same pass, relative orbit, polarization set and
platform. This dual-pol method leaves absent configurations unavailable; it never
fabricates missing bands. Scene footprints must cover >=99.99% of the window;
original pixel masks are still enforced. Scene IDs, original returned IDs,
footprints, processing properties and angle projection are retained locally.

The latest up to four distinct acquisitions strictly before the start, within
45 days, form a per-pixel median **in dB**. Slice products at one timestamp do not
inflate baseline count. The event observation is the earliest matching scene
inside the original IFI window, otherwise within 7 days after its inclusive end.
Timing classes remain explicit; a post-event acquisition is not a confirmed flood
day. Single-baseline availability is recorded as weaker evidence.

Earth Engine GRD is processed sigma0 in dB, not raw SAR: orbit application, border/
thermal noise handling, calibration and terrain correction precede this work.
It does **not** apply radiometric terrain flattening. Nearest-neighbour alignment
to a common 10 m UTM analysis grid does not imply 10 m physical resolution or
preserve native acquisition-grid cell identities. Original masked VV/VH/angle
values for every used scene are retained in clipped raster stacks; baseline,
event and event-minus-baseline products are derived locally.

## Experimental parameters, frozen before pixels

A candidate must jointly darken in VV and VH, have low absolute event backscatter,
pass incidence/terrain/auxiliary masks, and be outside permanent water. No dB
values are divided. No threshold is tuned to an IFI outcome or a visually preferred
map. No spatial smoothing or connected-pixel filtering is applied; speckle remains
an explicit confounder. This is a transparent diagnostic, not a validated detector.

- VV and VH event-minus-baseline threshold: -2, -3, -4 dB.
- Event VV ceiling: -14, -16, -18 dB; VH ceiling -22 dB.
- SRTM slope ceilings: 3%, 5%, 7%, computed as `100*tan(slope_degrees)`.
- Both baseline/event incidence: 30–45 degrees; difference <=1 degree.
- Permanent water: JRC GSW v1.4 `seasonality >=10` months.
- Require valid original occurrence and seasonality masks. Masked JRC land is
  **unknown**, never silently assigned dry/non-permanent. This conservative rule
  can leave little analysable land; report missing auxiliary counts explicitly.

All numerical gates above are **experimental**, including the nominal combination
-3/-16/-22 dB and 5% slope. The 27 change/VV/slope combinations are all reported,
not optimized. VH/incidence gates remain fixed feasibility filters and require
future calibration. UN-SPIDER motivates same-pass temporal comparison, permanent
water separation and slope screening, but does not validate these thresholds.
Its example uses a trial-and-error threshold; FloodPulse does not inherit that
value as validated or divide logarithmic dB values.

JRC (1984–2021) is retrospective auxiliary evidence, not a prediction-time feature.
SRTM is a circa February 2000 ~30 m surface model; its slope is not a direct shadow/
layover correction. Side-looking geometry, vegetation, urban double bounce,
incidence differences, radar shadows, smooth soil and speckle remain. Every dark
pixel is not water; slope screening cannot guarantee removal of SAR artefacts.

## Interpretation, workload and validation

Statuses are Sentinel-1-specific. With no independent spatial corroboration,
nonzero candidates or no usable analysis cells remain `sentinel1_ambiguous`.
Usable cells with zero nominal candidates are `sentinel1_no_clear_flood_signal`,
which is not absence or a negative label. Unavailable pairs and failed computations
retain their own statuses. The five-status vocabulary reserves supported-candidate
status, but this unvalidated implementation never assigns it. Binary targets stay
null; no daily flood labels or automatic GFD fusion.

Four half-open 100x100 partitions own each 10 m cell exactly once: 40,000 spatial
cells/window. Up to four baselines + one event give at most 19 float bands,
190,000 band-cells/partition (237,500 with 1.25 planning margin), below the retained
300,000 ceiling. Raster retrieval is <=1 MiB/partition, no remote reductions or
exports. Request deadline 60 s, three attempts with 2/4 s backoff, suspend-aware
900 s per bounded coverage/metadata/extraction phase, and late-result rejection
are inherited from the verified GFD infrastructure. HTTP additionally has 5/15 s
connect/read and a 30 s streaming ceiling. Completed source/tile/evidence files
are checksum-validated; every count/sensitivity result is rebuilt from rasters.

## Sources and publication

- [Earth Engine Sentinel-1 catalogue](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)
  and [processing documentation](https://developers.google.com/earth-engine/guides/sentinel1).
- [UN-SPIDER temporal flood-mapping practice](https://un-spider.org/advisory-support/recommended-practices/recommended-practice-google-earth-engine-flood-mapping/step-by-step).
- [JRC GSW v1.4](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater),
  European Commission JRC, Pekel et al. (2016), free access with attribution.
- [NASA/USGS SRTM](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003), public domain.
- [Copernicus Sentinel legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice):
  lawful reproduction/adaptation/distribution allowed with source and modification
  notices, without suitability warranty. Use “Contains modified Copernicus
  Sentinel data [actual acquisition years]”.
- IFI: Saharia/IIT Delhi/HydroSense, DOI 10.5281/zenodo.16994648, CC BY-NC 4.0.
  Public geoBoundaries v6/William & Mary geoLab: CC BY 4.0, modern composite,
  not historical administrative verification.

Commit code/tests/method/source IDs/aggregate metadata/checksums only. Original
SOI/restricted geometry, detailed SAR rasters and evidence remain local. Source
rights do not compel publication; no withheld data are released by this pilot.

## Stage 3E2: demonstrated mask error and replacement semantics

The old `raw_image` intersected `GlobalSurfaceWater` `seasonality.mask()` with
`occurrence.mask()` into `water_valid`; `analyze` then required it alongside DEM
validity before any SAR analysis. The old code used no other JRC product/band.
The [official catalogue](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater)
states that never-detected-water areas are masked and documents the special
occurrence-dependent fractional mask. Occurrence is percent water frequency,
seasonality counts months, and max_extent bit 0 records ever-detected water.
These are water-history masks, not general valid-land or SAR-observation masks.
Keep fractional masks separately; count positive support without weighting it
as observation quality or multiplying occurrence twice.

Bounded live checks retrieved original values and masks for all three bands,
[MonthlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory)
`water` and [YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_YearlyHistory)
`waterClass`. The native 30 m EPSG:4326 products were nearest-sampled onto the
**existing** 10 m UTM grids, four half-open 100x100 tiles each. Counts below are
SAR-grid cells, not independent 30 m samples. No restricted geometry was sent.

| Context | Udupi May 2018 | Udupi June 2018 (SAR acquisition month) | Kodagu January 2019 |
| --- | ---: | ---: | ---: |
| SAR valid | 40,000 | 40,000 | 40,000 |
| Monthly 0: no data | 7,052 | 40,000 | 0 |
| Monthly 1: not water | 32,948 | 0 | 40,000 |
| Monthly 2: water | 0 | 0 | 0 |
| Monthly masked | 0 | 0 | 0 |

Both GlobalSurfaceWater occurrence/seasonality bands are masked at all 40,000
cells; their old intersection is zero. In contrast, max_extent is unmasked
everywhere with value 0. This band-specific result supports no detected water
history, not proof of observation availability or absence of flood. The monthly
not-water observations demonstrate why the summary mask cannot identify all
valid Landsat observations. Monthly context is not event-day or SAR verification.

Both event-year waterClass layers are **masked at 40,000 cells**: each explicit
class count 0/1/2/3 is zero. Masked values remain unknown, distinct from explicit
class 0. Zero permanent detections is not evidence of zero permanent water.
Class 3, if observed, is the only conservative event-year permanent exclusion;
class 2 seasonal water is retained. Yearly summaries are retrospective auxiliary
context and can contain observations after event dates.

Replacement functions keep SAR masks/finite values/local geometry independent;
they expose monthly state, yearly class, separate monthly/yearly availability,
permanent-water flag and **whether permanent status is known**. Class 0/masked
values are unavailable, never imputed dry/permanent. Missing JRC cannot make SAR
invalid. For the event-month/year combination, unavailable auxiliary context is
7,052 Udupi and 0 Kodagu; permanent status remains unknown at every cell in both.
These functions provide diagnostics only, not a corrected flood footprint.

## Stage 3E2: event corroboration and calibration decision

The retained IFI records have only district scope, no original coordinates or
locality. Their original single-day windows remain May 29, 2018 and January 4,
2019. Selected SAR acquisitions are June 3 (+5 days) and January 5 (+1 day),
respectively; imagery availability does not establish flooding at the review tile.

The [KSDMA 2021 flood action plan](https://ksdma.karnataka.gov.in/storage/pdf-files/ActionplanforFloodriskmanagement2021.pdf)
(PDF page 39, printed page 11) supports broader 2018 Udupi/coastal impacts and
August 3–10, 2019 statewide flooding. The [official Kodagu 2019 report](https://kodagu.nic.in/en/document/district-disaster-management-authority-kodagu-2019/)
identifies August 8–10, 2019 (PDF page 18), not January 4. Publication/hosting dates
are separate from disaster dates. Searches of inspected government records did
not establish exact dates and the deterministic tiles' spatial correspondence.
The indexed [Flood 2018 report](https://ksdma.karnataka.gov.in/storage/pdf-files/Flood%202018.pdf)
supplies broader Udupi/Kundapura context, but its local download exceeded the
20 MiB bound; it is not retained as fully inspected evidence. A KSNDMC-titled
Blogspot mirror was excluded from authoritative corroboration because official
ownership could not be established. No inference that the IFI events did not occur.

The [public Bhuvan inventory](https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/flood/flood.php?uname=empty)
exposes Karnataka layers for August 9/10/12/13/15 and October 24, 2019, plus
aggregate 2003–2020 maps. Original labels, WMS layer IDs and endpoints are
retained in permitted metadata. No 2018 Karnataka dated layer or January 2019
layer was found in the inspected list. District intersections and layer data
access were not tested; catalogue availability cannot corroborate either pilot.
No restricted map/service data was scraped or redistributed.

Both: `year_event_supported_only`, **`calibration_candidate_temporally_weak`**,
with exact tile correspondence unresolved. These methodological statuses do not
replace stored `sentinel1_ambiguous`. Neither meets `calibration_candidate_supported`,
so **no SAR calculation or 27-setting rerun was performed**, and no threshold was
altered. Next: identify one better Sentinel-1-era anchor with official dated
NRSC/KSDMA spatial evidence, preferably 2019–2021, before separate calibration.

Diagnostics, provenance and retained source checksums live in
`data/working/karnataka_jrc_auxiliary_v1`; raw tiles/government documents remain
local. Reusable `retrieve` preserves originals and skips checksum-validated tiles;
it retains 60-second requests, a 900-second phase budget, three attempts, 2/4-second
backoff and 1 MiB raster cap. Local `validate` reproduces all counts read-only.
Attribution: EC JRC/Google, Pekel et al. (2016), Copernicus; modified context on the
SAR grid. Original IFI provenance/CC BY-NC 4.0 and public geometry attribution
remain with v1/v2; no SOI or derived rainfall publication policy changed.


## Stage 3E3: Belagavi–Chikodi/Sadalgi official event, calibration inconclusive

The independently dated NRSC Radarsat-2 observation is **2019-08-09**.
CWC Sadalga August 7–14 and Gokak Falls August 6–12 remain separate station
records; August 6–14 is a derived union only. MHA August 11 district response
corroboration and ambiguous IFI0041 stay separate evidence. The full source
hierarchy and original document checksums are retained in the new local version
and the existing source register.

No publisher-hosted georeferenced inundation product was obtained: the published
NRSC map is visual/event corroboration only, and public WMS capabilities returned
HTTP 400. No PDF digitization or reference labels. Scope is a documented 2 km
retrieval window near official CWC Sadalga station CW1KRU000083, not an official
flood boundary. Approximate 2025 station coordinates are not historical flood
measurements; the window can include adjacent Maharashtra.

Two same-window Earth Engine metadata checks, UTM and geographic coordinates,
returned **zero Sentinel-1 scenes** for July 1–August 18, 2019. No homogeneous group,
usable pair or best temporal scene exists for this query. This is not a claim
about every Belagavi location. Statuses are `sentinel1_pair_unavailable`,
`calibration_spatial_reference_insufficient`, `calibration_inconclusive`.
No imagery, continuous statistics or thresholds were computed live.

The new separate adapter defines prospective median baseline VV/VH and dB change,
incidence and terrain context. Its controlled fixture tests enforce same-orbit,
pass/platform/IW/VV+VH pairing, multiple baselines, exact-date priority and the
local station interval. Event scenes after August14 cannot substitute for an
in-window observation. These functions were tested with isolated arrays only;
no live continuous-processing result is claimed. Raster processing refuses to
initialize a provider when the metadata has no pair.

SAR validity stays independent of JRC. Monthly0/masked and yearly0/masked retain
unknown/no-data; observed yearly class 3 alone supports permanent exclusion; yearly2
seasonal water remains. The original27 settings are preserved without rerunning
or choosing any threshold. Threshold analysis requires a separately reviewed
machine-readable independent reference and separate calibration/assessment;
no pixel truth or binary/daily labels are created here.

`calibrate_belagavi_sentinel1.py freeze` refuses completed output/reference paths.
`validate` reproduces anchor, scope, IFI association, empty grouping, source
checksums and unavailable outcome offline. Original documents and local geometry
are withheld; Git receives only code/tests/method/source metadata/checksums.
Next: obtain a permitted georeferenced reference plus usable SAR imagery for this
event, or separately authorize a better supported acquisition anchor.


## Stage 3E4: July 2021 official anchor and incremental availability gate

The primary official observation is WorldView-3 on 2021-07-26; the broader
Resourcesat-2A LISS-III map is 2021-07-28. Both listing and issue dates are July 29;
PDF creation and unspecified analysis/acquisition-hour metadata stay separate.
Both PDFs contain GEO registrations. Programmatic viewport extraction records
source corners/WKT (declared main-map UTM45N); it supplies map coverage only,
never digitized flood shapes or pixel labels. Reference status is
`official_map_reference_available`. Original optical clouds and official-use/
International Charter restrictions remain. IFI exact-token/date overlap yields
no association. July 26–28 is a project-derived observation bracket; broader
source language supports fourth-week flooding, not exact daily occurrence.

Availability starts with date+footprint only (June 15–August 15). Public OSM
Hulagabali coordinates define nested 2/25/90/180 km retrieval windows, not official
boundaries: counts 11/11/11/30. Record each area, bound, earliest/latest time and
all unfiltered scene footprints before grouping. IW/VV/VH branches retain 30;
ascending 2/descending 28; orbit 136:18, 63:10, 71:2; platform A28/B2. Preserve original
numeric histogram keys alongside normalized comparison keys. Intersections and
denominators must use the same area convention; projected area is separate.
Raw responses and completed AOIs survive local validation errors; cached
metadata can be assembled offline without repeated provider initialization.

Group by exact mode/polarizations/pass/relative orbit/H/10m and strict platform.
Retain all frames but use at most two distinct baseline dates, so adjacent
same-pass frames are not independent baselines. Narrow diagnostic footprint must
be covered by each selected scene. Temporal ranking prefers July 26, then the
observation bracket, then up to 7 days after July 28. Selected relative 63/A/descending
uses July 5+17 and July 29: shortly-after, not exact flood-date evidence. No scene
inside July 26–28. Metadata availability never establishes flood presence.

Both gates passed for one continuous-only extraction: 2 km/10m EPSG:32643, four
half-open 100x100 tiles, 13 source bands, 130000 band-cells/162500 with safety factor 1.25;
250000 target/300000 ceiling/bestEffortFalse unchanged. SAR medians, event values
and dB differences remain continuous. JRC Monthly 2021_07/Yearly 2021 are flags,
not SAR validity. Unknown/masked/class 0 stay unknown; yearly 3 known permanent,
yearly 2 seasonal retained. Source SAR VV/VH 10 m grid, approximate angle nominal
~16.083 km and JRC 30 m metadata remain distinct from 10 m processing grid.

Result 40000 valid SAR cells. All angle differences meet the unchanged ≤1 degree
diagnostic; angles 45.55–45.70 lie outside the unchanged 30–45 degree range.
Original combined-range/agreement count 0 is preserved. These diagnostics were
separated for interpretation without changing any cutoff. No flood threshold,
sensitivity rerun, classification, label or promotion. Independent scalar
medians/changes/math.fsum and raster mask/georeferencing checks reproduce every
valid pixel. Continuous pipeline established; methodological calibration remains
inconclusive without independent categorical spatial reference and separate
review of near-event timing/incidence limitations.

Original products, footprints and rasters remain local. Permitted source/schema/
aggregate/checksum metadata are versioned separately. `evaluate_belagavi_2021.py`
provides metadata, extract, freeze, validate; completed versions refuse overwrite,
validation is offline/read-only. No prior 2019 result or archived v1/v2 method is
rewritten. Next: obtain legitimate inundation reference for this event and
predeclare calibration/assessment and incidence treatment in a separate task.


## Stage 3E5: incidence audit and official reference acceptance

The Stage 3E4 source rasters and 40,000-cell continuous product stay immutable.
Use `scripts/.venv/bin/python -B scripts/audit_belagavi_incidence.py validate`
for offline read-only reproduction. New `discover`, `terrain` and `freeze` commands
are bounded and refuse completed outputs; they do not authorize classification.

The legacy 30–45° rule originated as a project heuristic, not a documented universal
SAR validity criterion. Earth Engine's angle is approximate ellipsoid incidence;
local incidence requires the terrain normal and radar line of sight. Official IW
characteristics extend to 46°. A Google tutorial's 30–39° AOI is not a universal rule.
Stage 3E5 classifies the exact legacy range as `legacy_angle_filter_unsubstantiated`.
Archived values/results are unchanged, and no replacement absolute-angle filter is
introduced. All three original angle distributions and the per-pixel baseline/event
absolute differences are reported without absolute-range filtering. Source angle
metadata's coarse nominal scale remains distinct from the 10 m analysis grid.

Use original finite/masked VV/VH and angle cells separately, reporting intersection
counts. Linear quantiles, means and float32 median differences have independent
sorted-scalar/statistics.median/math.fsum checks. Ellipsoid geometry agreement is
40,000/40,000 within the pre-existing ≤1° diagnostic, with mean difference 0.008451°.
The 45.6° values support an explicitly inferred far-range interpretation; full source
footprints and projected boundary distances are retained, with no invented edge
threshold or automatic rejection. This does not determine local terrain incidence.

Existing SRTM source is queried only for the exact 2 km tile. Native four-connected
slope is computed before nearest sampling; it is contextual February 2000 DSM
information, not local-incidence/layover/shadow correction. 160,000 band-cells,
200,000 safety workload, 250,000 target and 300,000 ceiling; no bestEffort or limits
raised. Original source masks/nodata stay explicit. No steepness cutoff, fraction
or terrain mask introduced. Elevation 522–542 m and slope median 1.85°, P95 4.76°,
P99 15.10°, maximum 20.57° retain localized terrain uncertainty.

Public NRSC landing-page capability links only: WFS disabled, WCS/WMS incomplete
bounded responses, WMTS HTTP 400 configuration mismatch. Stop after these attempts.
A service advertisement, HTTP 200 response header, portal zoom rectangle or WMS
rendered image is not independent flood-class data. Accept a WFS/WCS original
subset only after official identity, July 2021 date, actual tile overlap, CRS/grid,
class/nodata semantics, legitimate retrieval and internal-use conditions pass.
Otherwise retain `machine_readable_reference_unavailable`; the georeferenced optical
PDF maps remain `official_map_reference_available`, without tracing their floodwater.

Final `ready_for_unlabelled_sar_method_research` is methodology readiness only.
Machine-readable reference access is blocked; no threshold calibration, candidate
polygons or evidence promotion. Obtain a permitted dated GIS subset for this exact
anchor, then separately predeclare temporal/terrain/incidence treatment before any
bounded calibration. Keep originals/local geometry/rasters outside Git.
