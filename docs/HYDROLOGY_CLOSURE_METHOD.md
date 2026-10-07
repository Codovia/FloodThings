# Stage 4E — Hydrology semantic closure

This investigation reads preserved Stage 4A–4D evidence and creates a separate
`data/working/karnataka_hydrology_closure_v1/` version. It does not change source
observations, station coordinates, datum, eligibility or disagreement statuses.
The public manifest contains source references, checksums and aggregate statuses;
detailed topology, coordinate histories, PDF notes and source documents stay local.
No credentials, new discharge downloads, features, labels or metrics are involved.

## Gokak model-network evidence

Reuse the official JRC
[v2.1.1 OS-LISFLOOD v5.x release](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/LISFLOOD_static_and_parameter_maps_for_GloFAS/v2.1.1_OS-LISFLOOD-v5.x/Catchments_morphology_and_river_network/):
upArea_repaired_correctedmetadata_3000.nc, chan_Global_03min.nc and ldd_repaired.nc.
The original Stage 4D source manifest retains transfer records and release
README/changelog evidence. Upstream-area units are m² from the README, not an
attribute inferred from magnitude. All three native 0.05° axes must match exactly.
CC BY 4.0 attribution applies to static maps; model reanalysis has separate terms.

Use the union of ±2 native cells around the original western/eastern Gokak
candidates: 30 cells total, four official coordinate variants and eight distances.
No coordinates are averaged. All candidate evidence remains explicit. Positive
channel values are 1; other/fill values remain unknown. PCRaster drainage codes
1–9 are decoded against descending latitude: 6 east, 2 south, 9 northeast,
5 pit; missing direction is not replaced. Inspect immediate channel predecessors
and trace at most eight downstream steps inside the retained window. A window
exit is incomplete local topology, not the end of a catchment.

Both candidates are positive model channels. West drains east; east has three
immediate channel predecessors, including west. Their upstream-area difference
is consistent with additional model inflows and local area. These grids contain
no river-name/station crosswalk. CWC documents Ghataprabha and the gauge catchment,
but the reviewed evidence does not place the gauge on a specific side of this
model junction. Therefore **station_grid_match_ambiguous**, no selected cell.
Drainage-area agreement, distance, connectivity or discharge resemblance cannot
alone resolve it. Station-coordinate conflicts remain independently unresolved.

## CWC/NWDP temporal evidence

[CWC Krishna Water Year Book Volume I 2019–20](https://cwc.gov.in/sites/default/files/stage-dischargecompressed.pdf),
March 2021, PDF pages 21–23 (printed x–xii), §§1.4.2, 1.4.3, 1.5.1:
observations generally commence about 08:00 using area–velocity measurements;
non-observed/discarded values use rating curves against the 08:00 gauge. Extrema
refer to the measurement session, not absolute daily flood peaks. This supports
session-based observed/estimated flow, not a demonstrated 24-hour mean or an
instantaneous reading exactly at 08:00. Timezone is not stated in reviewed notes.
Gokak history is on PDF page 590 (printed 564).

[CWC Hand Book of Hydro-Meteorological Observations](https://cwc.gov.in/sites/default/files/hand-book-hydro-meteorological-observations._1.pdf),
June 2020: §3.2.2/PDF23 addresses gauges at session start/end; §4.6/PDF57 records
08:00 discharge and eSWIS entry timing; RD2/PDF139 separates time, mean gauge,
MSL level, discharge and observed/computed status. ADCP instructions/PDF188–189
start at 08:30 and average measurement transects. Neither mean gauge nor session
average proves a daily discharge mean. Do not apply the 2020 procedure to each
2019 record or infer its historical availability latency.

Exact [NWDP resource](https://nwdp.nwic.gov.in/dataset/river-discharge-manual-dailly-central-water-commission-cwc/resource/f95150ea-c8fc-4740-8815-d9c34c9d53a3):
`f95150ea-c8fc-4740-8815-d9c34c9d53a3`, dataset
`08fa3fd0-7861-471d-a295-27c1b239d1fa`. Advertised catalogue/Preview confirm
`Data Acquisition Time` and `Manual Daily River Water Discharge (m3/sec)` but
provide no exact field definition, observation timezone or aggregation bounds.
Portal update UTC is not measurement UTC. No equivalence to the Year Book
revision/semantics is established. Bounded research does not prove a dictionary
or gauge crosswalk cannot exist; questions remain for the producing agency.

## GloFAS temporal evidence and comparison gate

[ECMWF CEMS Model Output](https://confluence.ecmwf.int/spaces/CEMS/pages/242067364/Model+Output)
describes GloFAS river discharge as a 24-hour average timestamped at period end.
The preserved v5 file declares CF-1.7; its valid_time units omit a timezone.
[CF-1.7 §4.4](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/cf-conventions.html)
explicitly defines the omitted timezone as UTC. The 62 original timestamps,
2019-07-02 through 2019-09-01 00:00 UTC, remain unchanged. Separately documented
preceding intervals span July 1–August 31. File time bounds are absent: interval
semantics come from documentation, not explicit bounds stored in the file.

**temporal_semantics_partially_resolved**: model meaning and CWC procedures are
clearer, but exact NWDP semantics are not. Zero aligned quantitative comparisons.
A future gate requires separately documented discharge means, matching explicit
24-hour UTC bounds and the exact source-field definition. Date-only alignment,
water-level substitution or timezone guesses are forbidden. Metrics and automatic
feature/label generation are disabled even if a future comparison gate passes.
The 14 quality-caveated rows and all 33 unresolved disagreements remain unchanged.

## Reproduction and next evidence

Using the existing research environment:

```sh
scripts/.venv/bin/python -B scripts/close_hydrology_semantics.py build
scripts/.venv/bin/python -B scripts/close_hydrology_semantics.py validate
scripts/.venv/bin/python -B scripts/close_hydrology_semantics.py publish-metadata
```

Build refuses an existing version; validation reproduces all retained evidence
read-only and verifies input/code/output hashes. Metadata publication is also
create-only. No network request is made by these commands. PDF extraction uses
searchable original text; referenced pages were rendered and visually checked.

Final status: **hydrology_semantics_ready_limited**, a limited evidence checkpoint,
not permission for feature engineering. Next obtain official Gokak gauge/reach
mapping and NWDP field/timezone/aggregation clarification. Unsent questions are
included locally. Neither source is ground truth; no calibration/independent model
skill, absolute water-level compatibility or flood-negative evidence is claimed.
