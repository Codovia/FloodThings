"""Shared inputs of the river flood model; used by training and by the live service so they cannot drift."""
import math
from datetime import date, timedelta

FEATURES = ['rain_1d', 'rain_3d', 'rain_5d', 'rain_10d', 'rain_30d', 'wettest_cell_3d', 'season_sin', 'season_cos']
WINDOW_DAYS = 30


def river_flood_features(series_by_cell, day):
    """Inputs for `day` from daily rain {cell: {'YYYY-MM-DD': mm}}, using rain up to and including `day`.

    Returns None if any of the 30 days is missing for any catchment cell; values are never filled in.
    """
    days = [(day - timedelta(days=k)).isoformat() for k in range(WINDOW_DAYS)]
    per_cell = []
    for series in series_by_cell.values():
        values = [series.get(d) for d in days]
        if any(not isinstance(v, (int, float)) or v < 0 for v in values):
            return None
        per_cell.append(values)
    if not per_cell:
        return None
    mean = [sum(c[k] for c in per_cell) / len(per_cell) for k in range(WINDOW_DAYS)]
    doy = day.timetuple().tm_yday
    return [mean[0], sum(mean[:3]), sum(mean[:5]), sum(mean[:10]), sum(mean[:30]), max(sum(c[:3]) for c in per_cell),
            math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25)]


def decision_score(model, x):
    """Portable logistic-regression score from saved scaler and coefficients."""
    return model['intercept'] + sum(c * (v - m) / s for c, v, m, s in
                                    zip(model['coefficients'], x, model['scaler']['mean'], model['scaler']['scale']))
