# Stage 4D GloFAS v5 pilot foundation

This is exploratory **modelled hydrology**, not measured discharge, independent
model validation, a flood label or a prediction feature. Detailed evidence lives
in the immutable local `data/working/karnataka_glofas_2019_pilot_v1/`.

## Sources and reproduction

The supplied official [EWDS historical product](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download)
is `cems-glofas-historical`. Its NetCDF `avg_dis` identifies `GRIB_configuration=v5.0`,
`GRIB_stepType=avg`, and `m**3 s**-1`. The user reports LISFLOOD, consolidated,
time_mean, July–August2019, area `[17,74,16,77.5]`, NetCDF/unarchived.
The original API request/job and transfer timestamp were not supplied; these
selection labels are documentary provenance, not an invented API request.
No credentials were read and no new EWDS request was made.

The [official JRC static release](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/LISFLOOD_static_and_parameter_maps_for_GloFAS/v2.1.1_OS-LISFLOOD-v5.x/)
contains the upstream-area file, channel mask and local drainage direction.
The changelog explicitly relates v2.1.0 to the GloFASv5.x model setup; v2.1.1
changes reservoir latitude rows. Its retained README is labelled v2.1.0.
Band1 in the upstream NetCDF has no units attribute; the README explicitly
defines its upstream area as m². Missing is -999999. Native WGS84 axes are
3000 descending latitudes and7200 ascending longitudes, spacing0.05degrees.
They match the historical subset grid without resampling.

The channel file uses1 for mapped channel and0 as its fill/missing value.
Zero/masked channel cells are recorded as not-marked-or-nodata, not verified
absence of a river. Direction fill is255. The [official LISFLOOD code table](https://ec-jrc.github.io/lisflood-code/4_Static-Maps_topography/)
defines N=8,NE=9,E=6,SE=3,S=2,SW=1,W=4,NW=7,pit=5. Local downstream neighbours
and their upstream areas are retained; no infrastructure or catchment geometry
is generated from these model grids.

```bash
uv pip install --python scripts/.venv/bin/python -r scripts/requirements-glofas.txt
scripts/.venv/bin/python -B scripts/build_glofas_pilot.py validate
```

`build` creates a new version only; it refuses an existing directory.
`validate` checks input/code/output hashes and fully reproduces outputs read-only.
Original transfer times are unknown for manually supplied files; filesystem
modification dates are not treated as retrieval times. New auxiliary requests
have actual HTTP/retrieval/checksum logs, including one failed direction download
and its single bounded range-resume. Raw sources remain local.

## Station matching

All four official coordinate variants per station are reconstructed separately
from Stage4C2. Canonical coordinates remain unselected. Distances are great-circle
metres on a sphere of radius6371008.8m, a screening convention rather than a claim
of station datum/positional accuracy.

The 2025 CWC HO metadata PDF pages96/139/90 explicitly label the source column
**Catchment Area (Sq.km)**. Parser checks tie each area to its original station
code/coordinate row; the original values stay in the local provenance table.
This is a 2025 publication,
not proof of an unchanged2019 catchment definition.

The retained protocol was recorded after preliminary area diagnostics, before
automatic selection and series generation: union of ±2 native cells around each
source coordinate, at most12km from a source variant. Retain all reviewed cells.
The10% area-difference cutoff is an explicit exploratory screen, not accuracy,
river identity or calibration proof. A supported primary requires all four
variants to converge to the same nearest cell, a positive official channel flag
and area agreement within that screen. Nearby alternatives are retained.
No discharge magnitude participates in selection.

Sadalga and Huvinhedgi satisfy this limited support rule. Gokak's variants select
east/west cells; both are channels, with materially different upstream areas.
The west cell drains into the east cell in the model, but this does not resolve
the gauge's position relative to model inflows. Both remain candidates; no Gokak
primary is selected even though the west area agrees more closely with CWC.
Series are extracted for coordinate-derived channel candidates and nearby
channel cells meeting the declared area screen, without averaging them together.

## Time and measured comparison gate

Original valid_time runs2019-07-02 through2019-09-01 at00:00, interpreted using
the file's CF epoch. The requested July–August period is not substituted for
those timestamps. [Official model-output documentation](https://confluence.ecmwf.int/spaces/CEMS/pages/242067364/Model+Output)
describes averages stamped at the end of the averaging period. Separate
interpreted preceding24-hour interval columns therefore spanJuly1–August31.
The file lacks time bounds; this interpretation is explicitly flagged rather
than presented as a source-supplied interval array.

Only Stage4C's14 eligible-with-quality-caveat discharge rows enter comparison
review. Their source times, units and QC uncertainty are preserved. CWC timezone
and equivalence to a model24-hour mean are unresolved: paired model value and
numeric difference remain null for every case. There are no quantitative
comparisons, skill metrics, bias correction, threshold exceedances, water-level
comparisons, negative examples or flood labels. Gokak has no eligible measured
flood-period discharge. Calibration participation remains unresolved.

Differences between models and gauges can reflect forcing, routing, catchment
representation, reservoirs, calibration, human water management or grid mismatch.
Neither source is selected as perfect truth. Readiness is
`modelled_hydrology_ready_limited`; comparison status is
`temporal_semantics_unresolved`.

## Publication and product status

The live download schema groups v5 as **pre-operational** and v4 as operational,
while the overview text calls v5 operational. Preserve that discrepancy and
treat this v5 pilot as testing/evaluation, not a production-warning source.
No version fallback or silent change to the frozen access checkpoint.

Static maps have CC BY4.0 terms; historical output uses the separate CEMS-FLOODS
licence. Account acceptance is not independently rechecked. All binaries,
detailed coordinates, rainfall and CWC-derived comparisons stay local under the
existing conservative publication policy. Git contains code, tests, methodology,
source references, checksums and aggregate provenance. No previously withheld
data were newly published.
