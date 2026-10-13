"""Local, rights-neutral geometry checks. No SOI files or nearest-place inference."""
from math import cos, hypot, pi
from pydantic import BaseModel, ConfigDict, Field

MAX_GPS_ACCURACY_M = 100  # Application acceptance policy, not a claim of survey accuracy.


class HomePoint(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(default=0, ge=0, le=10000000)


class GPSPoint(HomePoint):
    # A missing GPS radius cannot be interpreted as perfect precision.
    accuracy_m: float = Field(ge=0, le=10000000)


def covers_accuracy(geometry, latitude, longitude, accuracy_m=0):
    """Require the whole reported accuracy circle inside a valid polygon, including holes.

    Local equirectangular distances are a conservative application screen for
    small Karnataka uncertainty circles; they are not certified boundary accuracy.
    """
    if not isinstance(geometry, dict):
        return False
    polygons = [geometry.get('coordinates')] if geometry.get('type') == 'Polygon' else geometry.get('coordinates') if geometry.get('type') == 'MultiPolygon' else None
    if not polygons or not isinstance(polygons, list):
        return False
    count = 0
    inside = False
    distance = float('inf')
    xscale, yscale = 111320 * cos(latitude * pi / 180), 111320
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            return False
        rings = []
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                return False
            count += len(ring)
            if count > 20000:
                return False
            hit = False
            for a, b in zip(ring, ring[1:]):
                for v in (a, b):
                    if not isinstance(v, list) or len(v) < 2 or any(isinstance(n, bool) or not isinstance(n, (float, int)) for n in v[:2]) or not -180 <= v[0] <= 180 or not -90 <= v[1] <= 90:
                        return False
                if (a[1] > latitude) != (b[1] > latitude) and longitude < (b[0]-a[0])*(latitude-a[1])/(b[1]-a[1])+a[0]:
                    hit = not hit
                ax, ay = (a[0]-longitude)*xscale, (a[1]-latitude)*yscale
                bx, by = (b[0]-longitude)*xscale, (b[1]-latitude)*yscale
                dx, dy = bx-ax, by-ay
                fraction = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
                distance = min(distance, hypot(ax+fraction*dx, ay+fraction*dy))
            rings.append(hit)
        inside = inside or (rings[0] and not any(rings[1:]))
    return inside and distance > accuracy_m + 20  # Policy boundary caution, not source accuracy.
