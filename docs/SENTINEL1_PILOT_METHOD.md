# Sentinel-1 pilot method (Stage 3E)

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
