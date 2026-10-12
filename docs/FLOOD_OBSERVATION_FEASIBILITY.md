# Phase 12B: Karnataka flood observation feasibility

This is the frozen Phase 12B review. The subsequently authorized
[Phase 12C extraction](GROUNDSOURCE_KARNATAKA_EXTRACTION.md) supersedes its
UNKNOWN Groundsource coverage with 19,854 verified candidate records, including
18,194 state-contained/date-usable records. These remain unreviewed news locations;
the original NO-GO decision and observation requirements remain unchanged.

Verified 12 October 2026 against retained manifests and bounded publisher
responses. Baseline: `ce6a3517449ea493433a1066bc91f4d2dd65c8bd`.

**NO-GO for experimental flood-occurrence training:** **0 eligible positives,
0 defensible negatives, 0 independent eligible events and 0 complete verified
issue-time feature joins**. Four GFD source-event groups provide positive
event-window research evidence. No flood model was trained. The objective remains
actual flood occurrence across Karnataka; rainfall inference remains separate.

This phase implements offline receipt inspection, observation/absence consistency
checks and reproducible coverage. The pilot protocol below is a proposal requiring
independent scientific approval. Passing software checks does not certify labels.

## Groundsource schema and Karnataka coverage

[Zenodo](https://zenodo.org/records/18647054) and its
[API metadata](https://zenodo.org/api/records/18647054) identify
`groundsource_2026.parquet`: **667,122,400 bytes**, CC BY 4.0, publisher MD5
`cd1b5de6508f7aad8e1d1d0dd4cecea6`. Two honored HTTP 206 Range responses supplied
the last 8 bytes and 7,727-byte footer: **7,735 Parquet bytes total**.
No event rows/data pages or full archive were downloaded. Footer SHA-256 is in
the [public report](phase12b/report.json); full-file MD5 remains **unverified**.

The bounded decoder follows the primary [Parquet metadata specification](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift)
and [Apache Compact protocol](https://github.com/apache/thrift/blob/master/doc/specs/thrift-compact-protocol.md).
Schema names independently agree with redundant pandas metadata in the footer.

| Stored field | Physical / logical type | Interpretation and limits |
|---|---|---|
| `uuid` | optional BYTE_ARRAY / UTF8 | Record identifier; uniqueness and physical-event identity unverified |
| `area_km2` | optional DOUBLE | Supplied polygon area; values not row-validated |
| `geometry` | optional BYTE_ARRAY | GeoParquet WKB Polygon/MultiPolygon, EPSG:4326 / WGS84 |
| `start_date` | optional BYTE_ARRAY / UTF8 | Source string; not a timestamp or verified onset |
| `end_date` | optional BYTE_ARRAY / UTF8 | Source string; timezone/inclusive convention unverified |
| `__index_level_0__` | optional INT64 | Stored dataframe index, not an administrative identifier |

There are five data columns plus a stored index. There are **no explicit
latitude/longitude, country/state/district, news URL, per-record confidence,
acquisition timestamp or flood-mechanism columns**. Coordinates could be derived
from polygons; centroids would be derived summaries, not surveyed flood locations.
CRS and coordinate precision do not certify an inundation footprint.

The footer gives **2,646,302 global rows** in groups of 1,048,576, 1,048,576 and
549,150. Date-string extrema across groups span **2000-01-01 to 2026-02-03**;
these are metadata statistics, not checked individual event dates. GeoParquet
0.4.0 declares global bounds, but geometry chunks have no min/max spatial
statistics or per-group bounding boxes for Karnataka pruning. All three groups
must be scanned: compressed geometry totals **547,739,602 bytes**. Adding dates
and IDs approaches the full archive cost. No publisher Karnataka partition was
verified.

**Karnataka count: UNKNOWN.** District counts, invalid geometries, duplicate UUIDs,
overlapping reports and Groundsource/IFI/GFD relationships are also UNKNOWN.
A full checksum-verified archive or provenance-complete supplied subset is needed
to resolve them. The Phase 12B instruction explicitly requires user authorization
before the full download; bounded footer permission does not authorize it.

[Google's method report](https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/)
describes news-derived polygons and imperfect location/time matching: 60% of
manually reviewed extractions matched both accurately; 82% met a broader
practical-use criterion. These global results do not validate Karnataka records.
News coverage is not a flood census; reporting silence cannot create negatives.
This Parquet schema supplies no article URL for record-level reproduction.

After authorization: verify full MD5 and freeze the input; validate WKB/CRS/dates;
intersect a reviewed versioned Karnataka boundary locally; distinguish
intersection, containment and ambiguous cross-border polygons. Reconcile
historical names/boundaries before district assignment. Inspect duplicate UUIDs
and normalized geometry/date pairs while preserving originals. Review spatial
overlap and temporal uncertainty across Groundsource/IFI/GFD to group possible
shared physical events; preserve ambiguous links. Do not automatically certify
matches or expand date ranges into daily labels. Obtain independent dated flood
evidence before accepting individual news-derived records.

## Actual satellite coverage

The [observation matrix](phase12b/observation_coverage.csv) reproduces **21 source
contexts**: 13 GFD scopes, three Sentinel-1 acquisitions and five OPERA catalogue
records. These are different record types, not 21 independent events.
The [existing district/year matrix](phase12/district_year_coverage.csv) retains
31 district names × 57 years (1969–2025), **1,767 rows and 0 eligible daily
labels**. It counts retained evidence, not observed district-days. Current LGD
reconciliation remains unresolved. Unenumerated unit-days remain UNKNOWN.

| Source / geographic context | Dates | Actual retained evidence | Eligible acquisition / 24 h labels |
|---|---|---|---|
| GFD Udupi | 2728: 2005-09-14–09-30; 3551: 2009-09-25–10-12 | 33 / 23 qualifying event-pixels; 41,352 valid observed pixels per historical summary | 0 / 0 |
| GFD Chitradurga | 3652: 2010-05-18–05-24 | 2 qualifying event-pixels; 125,242 / 135,134 spatial valid pixels | 0 / 0 |
| GFD Kolar | 2758: 2005-10-23–12-09 | 329 qualifying event-pixels; 63,302 / 65,827 spatial valid pixels | 0 / 0 |
| GFD Bijapur, original spelling | 2698: 2005-07-23–08-16 | 0 qualifying water; 166,123 / 166,424 spatial valid pixels; no interval absence proof | 0 / 0 |
| GFD Raichur | 3107: 2007-06-22–07-04 | 0 qualifying water; 132,615 / 135,207 spatial valid pixels; no interval absence proof | 0 / 0 |
| Seven further GFD scopes | Chikkaballapura, Dharwad twice, Raichur, Gadag, Mandya, Kodagu; 2004–2017 | Six have 0 valid pixels; Kodagu 3,314 / 66,031 (~5.02%) | 0 / 0 |
| Sentinel-1 Belagavi 2 km tile | 2021-07-05/17 at 00:47:32 UTC; 07-29 at 00:47:33 UTC | 40,000 valid VV/VH and angle-intersection cells per acquisition; no categorical flood truth | 0 / 0 |
| OPERA Udupi public 3 km box | August 1, 6, 13, 18, 30, 2025 | All five CMR metadata matches inspected; water/quality pixels UNKNOWN | 0 / 0 |

GFD positives total **387 event-pixels**, not a unique spatial union, in **three
district contexts**, years **2005, 2009 and 2010**, across four GFD source IDs.
Physical-event independence and cross-inventory relationships require review.
All mechanisms remain unknown. Bijapur is not silently remapped to Vijayapura.
Udupi counts come from retained historical summaries; no missing full-unit
denominator is invented.

[GFD documentation](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)
defines event maximum extent, 3-day MODIS composites, clear-view indicators and
JRC permanent-water masks. CC BY-NC 4.0 restrictions remain. Classification uses
250 m resolution while band listings show 30 m storage; retained processing uses
250 m, and resampling supplies no new observed detail. Event-window start/end
metadata are not individual acquisitions. Duration/clear-view aggregates cannot
certify continuous 24 h absence. Original count/percentage units remain intact.

[Sentinel-1 GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)
supplies backscatter rather than flood classification. Belagavi's 10 m processing
samples are not independent flood observations. Diagnostics retain 1,586
permanent-water cells and 36,529 with unknown annual permanence. Monthly
land/no-water is not daily absence. The incidence audit confirms ≤1° agreement
for all 40,000 cells; the unsupported original 30–45° gate remains unchanged.
Exact categorical NRSC truth matched to July 29 is unavailable; July 26–28 is an
official-map bracket, not a daily label. [Existing pilot restrictions](SENTINEL1_PILOT_METHOD.md)
remain in force.

### OPERA feasibility and unresolved processing alert

[NASA](https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-S1_V1) and
[Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/OPERA_DSWX_L3_V1_S1)
describe 30 m water classifications/confidence and roughly 6–12 day revisits.
Detection targets open-water bodies larger than 3 ha and 200 m wide. WTR includes
water, inundated vegetation, not-water, HAND and layover/shadow masks; land-cover
masking can produce class 0. Class 0 alone therefore cannot certify dry conditions.
Confidence/diagnostic layers and version-specific masks require review. Separate
permanent/seasonal baseline water from temporary inundation.

A bounded public CMR query for the retained Udupi box and August 2025 returned
five products. `cmr-hits: 5` proves all five metadata matches were inspected.
Acquisition intervals and catalogue update times remain distinct. Box containment
establishes catalogue geometry only. No raster was retrieved: **valid pixels,
water and absence counts are UNKNOWN**. No district-wide coverage is inferred.

The current NASA HTML receipt contains an alert about sometimes combining
different platform/acquisition dates: May 20–November 7, 2025 issue, December 9
fix, and planned replacement through December 9 by January 2026. All five
inspected records have August 2025 update timestamps. Neither those timestamps
nor a planned completion date proves correction. **Product-specific replacement
and input-acquisition provenance remain unverified.** Require a verified
replacement or reject affected products.

Catalogue dates disagree: NASA archive start December 2023, Earth Engine August
2024, forward production September 2024. These do not establish Karnataka
backfill. Open EOSDIS sharing/citation terms apply; PO.DAAC protected rasters
require legitimate Earthdata access, while metadata are public. No credentials
were used and no source-owner messages were sent.

## Proposed pilot target and negative protocol

First research target: independently reviewed, detector-resolvable **temporary
open surface water at a scheduled future acquisition** in the existing public
Udupi 3 km window. Freeze 250 m EPSG:32643 square cells and a geometry hash before
outcome inspection (origin E=0, N=0; cells fully contained in the reviewed window).
Evaluate native patches/masks before aggregation. Review must establish minimum
detectable patch size/width and local limitations, including OPERA's detection
domain. This excludes unsupported narrow, urban, obstructed and sub-detection
floods; these cells are not district labels.

Set **T = nominal scheduled acquisition − 24 h**, using an archived schedule
available at T. Predeclare ±15 minutes around that scheduled time as the
acquisition acceptance interval. Missing, delayed or differently dated products
become UNKNOWN. Do not select a later wet image after seeing outcomes.
The proposed schedule/tolerance and scientific detection protocol still need
independent approval. Until genuine T-available features and schedule receipts
exist, acquisition classification is retrospective research, not future prediction.

| Target | Positive | Defensible negative |
|---|---|---|
| Acquisition temporary inundation | Reviewed resolvable temporary-water patch intersects the fixed cell at acquisition | Entire same cell adequately classified free of such water at that acquisition, with reviewed permanence/land-cover interpretation |
| Flood occurrence in `[T,T+24 h)` | Independently verified flooding somewhere in the unit during the interval | Independently reviewed adequate monitoring establishes absence throughout that same unit and full interval |
| Susceptibility | Spatial propensity over a specified climatological horizon | Requires its own exposure/horizon definition; not a daily observed label |
| River discharge exceedance | Compatible measured discharge above a reviewed reach/station threshold in a defined interval | Measured discharge below that threshold throughout its reviewed interval; does not prove no flood elsewhere |

Every candidate needs original bytes/hash, product/run/algorithm versions, exact
UTC acquisition, processing/publication/valid times, grid/geometry, grouping,
rights and independent matched reference. Preserve disjoint denominators:
valid + unknown = unit; temporary + permanent + dry = valid. Unknown permanence,
nodata, shadow/layover, ambiguous land-cover masking, sensor limitations and poor
alignment remain UNKNOWN. Unmasked backscatter is insufficient quality evidence.

Verified positive water is existential, so a reviewed positive may survive partial
unit coverage within its detection domain. A negative requires **all pixels of
the same frozen unit adequately classified**, with no 95%/98% shortcut. Permanent
water and expansion require separate adjudication. A 24 h negative also requires
an independently supplied monitoring receipt bound to the same unit/geometry/
start/end and full-interval observation process. One dry overpass, even clear,
cannot provide this. Revisit gaps currently prevent certification. Reporting
silence, random background points and GFD observed-zero scopes provide no negatives.

`audit_satellite_observations.py` verifies structural/time consistency and a
separate checksum-bound independent review receipt for source/unit/time/counts/
interpretation references. The builder never manufactures review receipts.
Duplicate IDs or same-source-hash/geometry/time aliases invalidate all copies.
Returned eligibility is a **consistency nomination**, not automated scientific
certification, a GO decision or operational label. Test fixtures are synthetic
and isolated. There are currently no independently reviewed real acquisition
classification records to nominate.

## Inputs, evaluation and separate riverine track

Each predictor requires values, source/version/hash, units, spatial support/join,
missingness policy, valid interval, initialization/publication and verified
availability at T. Obtain audited antecedent rainfall/soil wetness/water state,
archived issued rainfall forecasts and versioned terrain/drainage/land-cover/
baseline-water context. Future target imagery cannot be a predictor. Retained
CHIRPS/ERA5 retrospective data do not prove availability at T; reanalysis may
support explicitly qualified hindcasts, not genuine issued forecasts. Static
products published after T also require retrospective qualification.

The new contract distinguishes antecedent observations (valid and available by
T) from forecasts (run/availability by T, possibly valid after T). It checks
issue time precedes the target and schedule availability. A reference string
alone does not certify full predictor lineage. Phase 12A's frozen complete-feature,
event/source/review/spatial/chronological holdout gates remain intact.

Obtain both independently adjudicated classes over enough distinct physical
events and monitored non-event periods for a justified sample-size plan. Four
source groups and their correlated pixels cannot supply it. Predeclare whole
event/cross-source groups, spatial blocks and chronological holdouts with
appropriate feature/target embargo. Keep shared storms/sources/reviews in one
partition; fit transformations only on training data. Hold threshold/reference
development separate from evaluation. Compare persistence/climatology and simple
hydrological baselines; report unknown rates, precision/recall, PR-AUC and
calibration only on eligible independent labels. An Udupi pilot cannot support
all-Karnataka claims.

CWC remains **1,697 observations / 81 comparisons / 33 disagreements**, with
only **14 caveated discharge rows** (Sadalga 2, Huvinhedgi 12, Gokak 0). All three
datum/threshold joins remain unresolved; station/reach identity, timezone/daily
aggregation, QC, availability and publication rights remain restricted under
[the hydrology review](HYDROLOGY_SOURCE_SEMANTICS.md). No incompatible comparison
or reach flood label was added. GloFAS v5's 806 modelled cell-days remain context,
never measured truth.

[EWDS reforecast documentation](https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast)
describes later-generated historical forecasts, 11 members, twice-weekly
initialization and 24 h steps through 46 days. Its page lists v4 and 2003–2022
reference years; retained historical data are v5. Resolve versions and measurement
compatibility before a qualified hindcast; later creation is not 2019 availability.
Archived operational issuance needs separate receipts. The river-reach forecasting
track remains **NO-GO** with this measured subset. Discharge threshold exceedance
would be a separate target requiring reviewed thresholds and timing.

## Reproduction and next acquisition requirements

The immutable local version is
`data/working/karnataka_flood_observation_feasibility_v1/`, with source receipts,
output hashes and code fingerprints. Public artifacts omit original footprints,
restricted geometries and measured CWC values. Old scientific versions are intact.

```bash
python3 -B scripts/build_flood_observation_feasibility.py validate --public docs/phase12b
backend/.venv/bin/python -B -m pytest -q tests
```

`build` refuses an existing version. Inspection is offline and bounded, rejecting
ignored Range responses, truncated/oversized metadata and count inconsistencies.
The scripts do not fetch data, install dependencies or train models.

Next requirements:

1. Explicit authorization for the 667,122,400-byte Groundsource archive, or a
   provenance-complete supplied subset, then boundary/date/duplicate/cross-source
   review. This improves positive discovery; it cannot provide negatives.
2. Legitimate OPERA raster access, verified product-specific correction/input
   timing for the August 2025 records or verified unaffected-period acquisitions.
   Retain water, confidence/diagnostic masks, original checksums, baseline water
   and full spatial denominators.
3. Licensed independent references matched to acquisitions/cells, reviewed
   detection limits and scientific protocol approval. True 24 h occurrence needs
   an adequate continuous observation process beyond isolated overpasses.
4. T-available predictor/sampling receipts and independent labelled holdouts.
   Resolve CWC datum/time/QC/reach/rights separately before any riverine fit.

The defensible next step is acquiring/reviewing evidence. Current data do not
support experimental flood-occurrence training or calibrated Karnataka forecasts.
