"""Shared past-only hourly features. Missing values are never filled."""
from datetime import datetime, timedelta, timezone
import math

VERSION = 'rainfall_logistic_v1'
VARIABLES = ['precipitation', 'temperature_2m', 'relative_humidity_2m', 'surface_pressure']
UNITS = {'precipitation': 'mm', 'temperature_2m': '°C', 'relative_humidity_2m': '%', 'surface_pressure': 'hPa'}
FEATURES = {'rain_24h_mm': 'mm', 'rain_72h_mm': 'mm', 'max_hourly_rain_24h_mm': 'mm',
            'temperature_mean_24h_c': '°C', 'humidity_mean_24h_percent': '%',
            'pressure_mean_24h_hpa': 'hPa', 'season_sin': 'dimensionless', 'season_cos': 'dimensionless'}
THRESHOLD_MM = 64.5
THRESHOLD_URL = 'https://www.imdpune.gov.in/hazardatlas/extr_rainfallnew_p2001_2010.html'


class RainfallUnavailable(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RainfallUnavailable(message)


def parse_hourly(payload):
    require(payload['utc_offset_seconds'] == 0, 'Hourly rainfall input must use UTC')
    hourly = payload['hourly']; times = hourly['time']
    require(isinstance(times, list) and times and len(times) < 30000, 'Invalid bounded hourly series')
    for field in VARIABLES:
        require(payload['hourly_units'][field] == UNITS[field], 'Incompatible hourly units')
        require(isinstance(hourly[field], list) and len(hourly[field]) == len(times), 'Mismatched hourly arrays')
    result = {}
    previous = None
    for i, value in enumerate(times):
        timestamp = datetime.fromisoformat(value)
        require(timestamp.tzinfo is None and timestamp.minute == 0 and timestamp.second == 0, 'Invalid UTC hourly timestamp')
        timestamp = timestamp.replace(tzinfo=timezone.utc)
        require(previous is None or timestamp == previous + timedelta(hours=1), 'Duplicate, unordered or missing hourly timestamps')
        values = {field: hourly[field][i] for field in VARIABLES}
        for field, reading in values.items():
            if reading is None:
                continue
            require(isinstance(reading, (int,float)) and not isinstance(reading,bool) and math.isfinite(reading), 'Non-finite hourly data')
            limits = {'precipitation': (0, None), 'temperature_2m': (-100, 70), 'relative_humidity_2m': (0, 100), 'surface_pressure': (300, 1100)}
            low, high = limits[field]
            require(reading >= low and (high is None or reading <= high), 'Invalid physical hourly value')
        result[timestamp] = values; previous = timestamp
    return result


def past_features(series, cutoff):
    require(cutoff.tzinfo is not None and cutoff.utcoffset() == timedelta(0) and cutoff.minute == cutoff.second == cutoff.microsecond == 0, 'Explicit UTC hour cutoff required')
    # Precipitation is the preceding-hour sum. These 72 values end strictly
    # before cutoff; the final precipitation interval ends at cutoff-1h.
    stamps = [cutoff - timedelta(hours=i) for i in range(72,0,-1)]
    rows = []
    for stamp in stamps:
        require(stamp in series and all(series[stamp][v] is not None for v in VARIABLES), 'Incomplete 72-hour antecedent inputs')
        rows.append(series[stamp])
    recent = rows[-24:]
    phase = 2*math.pi*((cutoff.timetuple().tm_yday-1)/365.25)
    values = [math.fsum(r['precipitation'] for r in recent), math.fsum(r['precipitation'] for r in rows),
              max(r['precipitation'] for r in recent), math.fsum(r['temperature_2m'] for r in recent)/24,
              math.fsum(r['relative_humidity_2m'] for r in recent)/24, math.fsum(r['surface_pressure'] for r in recent)/24,
              math.sin(phase), math.cos(phase)]
    return dict(zip(FEATURES, values))


def future_target(series, cutoff):
    # Values stamped cutoff+1 .. cutoff+24 represent intervals [cutoff,cutoff+24].
    values = []
    for i in range(1,25):
        row = series.get(cutoff + timedelta(hours=i))
        require(row is not None and row['precipitation'] is not None, 'Incomplete future target; not a negative')
        values.append(row['precipitation'])
    total = math.fsum(values)
    return total, int(total >= THRESHOLD_MM)
