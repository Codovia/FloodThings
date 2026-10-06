# FloodPulse comparison-evidence methodology — Stage 3D

This is an exploratory six-event pilot, not a training dataset. Evidence refers to a specific reviewed geography, GFD event window, raster grid and observation quality. It does not describe current flooding, safety or daily flood occurrence.

## Evidence vocabulary

| Class | Meaning | Pilot use |
| --- | --- | --- |
| `satellite_positive` | Observation-qualified non-permanent floodwater detected in a reviewed GFD event scope | Four existing positive contexts |
| `observed_zero_event` | Adequately observed reviewed GFD scope with zero qualifying floodwater cells | Two comparison contexts; flood absence not established |
| `unlabeled_background` | Screened window without verified positive evidence; absence remains unknown | Future protocol only; no windows collected |
| `insufficient_observation` | Inadequate observation quality for a useful comparison | Excluded; original records retained |
| `candidate_mismatch` | Event association not defensible | Excluded; original records retained |

Original source statuses are preserved separately. This pilot maps `observed_no_qualifying_floodwater` to the project class `observed_zero_event`; it does not rewrite Stage 3B evidence. All six `ml_binary_label` fields are JSON `null`. Strict schemas reject extra label/risk fields and inappropriate classes. `binary_targets()` refuses target construction; a future change requires separately reviewed evidence and methodology. `antecedent_predictors()` returns only the seven approved rainfall fields. Consumers must validate the dataset before using these functions; bypassing its schema is outside the approved workflow.

## Why random non-flood sampling is prohibited

IFI is a compilation of reported positive events, not an exhaustive presence/absence survey. Its underlying IMD report coverage and digitization do not establish that every unlisted district-day was flood-free. Missing IFI reports cannot certify non-flood observations. [IFI source record](https://zenodo.org/records/16994648).

GFD describes event-window maximum water extent and cloud-observation conditions. Permanent water must be excluded and observation masks respected. Floodwater can be missed because of unavailable/obstructed observations, compositing, resolution, short duration or geographic scope. A zero finding in one district does not negate flooding elsewhere in the source event. The project’s existing ≥95% valid-spatial-cell gate is a research screening rule, **not a calibrated confidence that flooding was absent**, and does not prove complete daily visibility. [GFD catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1).

Random background dates could contain unrecorded floods. Spatially distant or dry-season comparisons could make classification artificially easy by exposing differences in geography, season or monitoring rather than flood processes. Comparison selection can materially change apparent performance. This is a methodological risk inferred for FloodPulse, not a result measured in this pilot. Presence-only ecological research demonstrates the importance of background-selection bias; that evidence motivates caution rather than directly validating a flood model. [Phillips et al. (2009)](https://www.whoi.edu/cms/files/Phillips_EcolApp_2009_53454.pdf).

## Fixed pilot and rainfall processing

Reuse positives 2728/Udupi (33 cells), 3551/Udupi (23), 3652/Chitradurga (2) and 2758/Kolar (329) from immutable Stage 3C. Independently validate retained Stage 3B2 evidence before using comparisons: 2698/Bijapur (166123 valid, zero qualifying, GFD 2005-07-23–2005-08-16) and 3107/Raichur (132615 valid, zero qualifying, GFD 2007-06-22–2007-07-04). Neither is a matched control for a specific positive: geography, year and season differ. No GFD reduction or catalogue scan is authorized here.

Existing flood processing remains EPSG:32643, 250 m, nearest-neighbour data and masks. Valid masks for `flooded`, `jrc_perm_water`, `clear_views` and `clear_views>0` establish usable evidence; qualifying water additionally requires `flooded=1` and `jrc_perm_water=0`. All raw quality values and source dates stay separate from IFI associations. No daily labels follow from maximum extent, and the two-cell Chitradurga positive is not given the same spatial weight as Kolar.

CHIRPS v2.0 Final supplies native 0.05° EPSG:4326 daily precipitation in mm/day. Retrieve only bounded aligned envelopes, preserve source IDs/versions/masks/checksums and aggregate locally against retained public review geometry. No SOI geometry leaves the workspace. Use exactly Stage 3C’s strict native-cell-centre unweighted mean/min/max and scalar verification; no resampling, centroid substitution, interpolation or fabricated zeros. Valid zero rain remains a source observation; missing rain remains unavailable. [CHIRPS catalogue](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY).

For GFD start T, antecedents are **T−30 through T−1**. Reuse the identical `context.derived()` implementation for both classes: 1/3/7/14/30-day sums of daily regional means, plus previous-7/14-day maximum daily means. No additional comparison-only predictors or rainy-day threshold. Incomplete temporal or spatial coverage produces null affected summaries. Dates T through inclusive GFD end supply a separate `DESCRIPTIVE_ONLY_NOT_PREDICTION_FEATURE` table. Strict schemas and leakage tests prohibit event-start/future observations or descriptive fields in antecedents. IFI dates cannot expand the window. Final CHIRPS release dates at historical prediction times remain unverified; these are retrospective contexts, not operational backtests.

## Future unlabeled-background protocol — no data collected

A separately approved pilot must predeclare its finite candidate windows and selection rules before inspecting rainfall outcomes. Match, as practical, the positive review scope, season/month, historical period, CHIRPS availability, source mask coverage and satellite observation opportunities. Record unavoidable mismatches and exclusions rather than selecting easy distant/dry comparisons. Use identical geometry vintage and features; never select on a desired low rainfall or zero result.

Screen each proposed window, including the full antecedent period, against known IFI reports, GFD windows and verified flood evidence. Ambiguous locations, overlapping events and insufficient observations require review or exclusion with retained reasons. Source coverage periods and reporting gaps must be explicit. Screening cannot certify absence: every accepted background window remains `unlabeled_background`, with a null binary target. Avoid overlapping/dependent windows and plan geographic/temporal evaluation separation and source-release availability checks before any modelling. No random negative generation, background extraction or final selection algorithm is implemented now.

## Scientific readiness

| Future option | Additional evidence required | Present assessment |
| --- | --- | --- |
| Supervised positive/negative learning | Independently supported non-flood observations with comparable geography, timing and observation sensitivity; enough independent events and held-out validation | No defensible negative targets currently available |
| Positive–unlabeled learning | A reviewed representative unlabeled sample, adequate positives, selection-bias analysis, prevalence/identifiability assumptions and independent evaluation evidence | Conceptually relevant, not ready to implement |
| Event ranking / relative likelihood | Defined comparison population, defensible ordering/outcome, comparable covariates, more events and independent evaluation | Potential research option; no calibrated probability or safety claim |

Classic PU learning assumes positive labels are selected independently of their features. Flood reports and satellite quality/selection may violate that assumption; it must be investigated rather than assumed. These six selectively reviewed scopes supply neither representative background nor an identifiable class prevalence. [Elkan and Noto (2008)](https://cseweb.ucsd.edu/~elkan/posonly.pdf).

Recommend **continued evidence collection**, followed by a separately reviewed background/comparison protocol. Do not select a final ML approach, calculate accuracy/AUC, fit rainfall thresholds or claim causation. Rainfall context can depend on terrain, catchments, river conditions, land cover, soil moisture and drainage; these were not assessed in this pilot.

## Reproducibility and publication

`build_event_comparison.py` validates protected inputs, retrieves only the two fixed comparison rainfall windows, writes a new immutable local version and reconstructs every daily/derived value read-only. Resume requires an unchanged plan; bounded failures preserve accepted rasters without publishing a completed dataset. Source rasters, detailed rainfall/evidence tables and restricted geometry stay local. Git delivery contains code, tests, schemas, checksums, this methodology and aggregate provenance. CHIRPS is public domain; geoBoundaries requires CC BY 4.0 attribution. IFI and GFD remain CC BY-NC 4.0 with Saharia/IIT Delhi/HydroSense and Tellman/Cloud to Street/DFO attribution and processing changes identified. Independent current-LGD identity and SOI publication questions remain unresolved.
