# GIS_SPEC.md

**Project:** FloodPulse
**Status:** Planning document. No GIS processing is currently implemented.

---

## Coordinate reference systems

### Storage and API exchange

```
EPSG:4326 (WGS 84) — latitude/longitude in decimal degrees
```

All point coordinates stored in the database and exchanged via APIs use EPSG:4326.

### Distance and area calculations

Use an appropriate projected CRS or PostGIS geography type for metric calculations. Do not compute distances or areas using raw latitude/longitude degree values.

Document the CRS used at every spatial operation.

### CRS metadata

Every spatial dataset, geometry column, and spatial join must have its CRS explicitly documented and validated. Mismatched CRS must be detected and rejected or reprojected with documentation.

---

## Administrative boundaries

### Source requirement

Administrative boundaries (state, district, taluk, village) must come from authoritative sources:

- KGIS (Karnataka Geographic Information System / KSRSAC)
- LGD (Local Government Directory)
- Survey of India / NRSC / Bhuvan

### Prohibitions

- No rectangular geographic approximations.
- No hand-drawn or estimated boundaries.
- No bounding-box substitutes for actual administrative polygons.
- No centroid-only representations where polygon geometry is required for spatial operations.

### Validation

- Geometry validity must be tested (e.g., ST_IsValid in PostGIS).
- Topology must be checked (no unexpected overlaps or gaps between adjacent districts).
- Boundary datasets must include provenance metadata.

---

## Point-in-polygon assignment

Location assignment (e.g., "which district does this coordinate belong to?") must use actual spatial containment queries against authoritative boundary polygons.

Do not use lookup tables mapping coordinates to districts via hardcoded ranges.

---

## River and waterbody geometries

- River geometries must come from authoritative sources (KGIS, Survey of India, or equivalent).
- Distance-to-river calculations must use actual geometric distance (ST_Distance or equivalent), not hand-entered values.
- Waterbody geometries (lakes, tanks) should come from verified geospatial datasets.

---

## Terrain

### DEM source

Terrain data (elevation, slope) must be derived from a legitimate Digital Elevation Model:

- SRTM 30m (via OpenTopography or USGS) is the expected open-access source.
- Survey of India DTM if access is granted.

### Derived features

- **Elevation:** Extracted from DEM for point or zonal statistics per spatial unit.
- **Slope:** Calculated from DEM gradient, not hardcoded per district.

### Prohibitions

- No hand-entered slope values.
- No hand-entered elevation values.
- No treating degree differences as metric distances in terrain calculations.

---

## Spatial joins

All spatial joins must:

1. Use actual geometries (not string-based district name matching alone).
2. Document the CRS of both inputs.
3. Handle edge cases (points on boundaries, multi-polygon units).
4. Log join statistics (matched, unmatched, ambiguous).

---

## Coordinate validation

All incoming coordinates must be validated:

- Latitude and longitude within plausible bounds for Karnataka (approximately 11.5°N–18.5°N, 74°E–78.5°E).
- Non-null, non-zero (zero coordinates are almost certainly errors, not real locations).
- Consistent CRS.

---

## Provenance

All GIS datasets must record:

- Source name and authority.
- Download/retrieval date.
- Original CRS.
- Any reprojection or transformation applied.
- Processing version.
