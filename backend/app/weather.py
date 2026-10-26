"""Read-only Open-Meteo adapter: no database, archive writes or fallback values."""
import asyncio
from email.utils import parsedate_to_datetime
from datetime import date, datetime, timedelta, timezone
from math import isfinite

import httpx

API_URL = "https://api.open-meteo.com/v1/forecast"
IST = timezone(timedelta(hours=5, minutes=30))
LOCATION = {
    "name": "Bengaluru, Karnataka",
    "latitude": 12.9767936,
    "longitude": 77.5900820,
    "source_url": "https://wiki.openstreetmap.org/wiki/Bengaluru",
}
SOURCE = {
    "name": "Open-Meteo",
    "url": "https://open-meteo.com/",
    "documentation_url": "https://open-meteo.com/en/docs",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "data_kind": "weather_model_output",
}
PARAMS = {
    "latitude": LOCATION["latitude"],
    "longitude": LOCATION["longitude"],
    "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
    "hourly": "precipitation",
    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,weather_code",
    "timezone": "Asia/Kolkata",
    "forecast_days": 7,
    "temperature_unit": "celsius",
    "precipitation_unit": "mm",
}


class WeatherUnavailable(Exception):
    """The provider failed or returned an invalid response."""

    def __init__(self, message, *, kind="provider_unavailable", upstream_status=None, retry_after_seconds=None):
        super().__init__(message)
        self.kind = kind
        self.upstream_status = upstream_status
        self.retry_after_seconds = retry_after_seconds


def unavailable(message: str, failure: WeatherUnavailable | None = None) -> dict:
    return {
        "status": "unavailable", "message": message,
        "location": LOCATION, "source": SOURCE,
        "retrieved_at": None, "observation_time": None,
        "forecast_issued_at": None, "current": None, "forecast": [],
        "failure_kind": failure.kind if failure else "provider_unavailable",
        "upstream_status": failure.upstream_status if failure else None,
        "retry_after_seconds": failure.retry_after_seconds if failure else None,
    }


def number(value, *, minimum=None, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Invalid numeric value")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError("Value outside valid range")
    return value


def local_time(value):
    """ISO provider clocks are local, resolved using the validated IST offset."""
    result = datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError("Expected local provider time")
    return result.replace(tzinfo=IST)


def parse_hourly(payload):
    """Keep hourly evidence separate: a bad/missing series cannot erase current weather."""
    base = {"timezone": "Asia/Kolkata", "unit": "mm", "interval_seconds": 3600,
            "interval_semantics": "preceding_hour", "source": SOURCE}
    if "hourly" not in payload:
        return {**base, "status": "missing", "message": "Hourly precipitation was not supplied.", "intervals": []}
    try:
        hourly, units = payload["hourly"], payload["hourly_units"]
        if units.get("time") != "iso8601" or units.get("precipitation") != "mm":
            raise ValueError("Hourly timestamps must be ISO local time and precipitation units mm.")
        times, values = hourly["time"], hourly["precipitation"]
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values) or len(times) > 168:
            raise ValueError("Hourly precipitation arrays have invalid lengths.")
        ends = [local_time(t) for t in times]
        if any(t.minute or t.second or t.microsecond for t in ends):
            raise ValueError("Hourly timestamps are not aligned to full IST hours.")
        if any(b <= a for a, b in zip(ends, ends[1:])):
            raise ValueError("Hourly timestamps are duplicated or out of order.")
        intervals = [{"start": (t - timedelta(hours=1)).isoformat(), "end": t.isoformat(),
                      "precipitation_mm": number(v, minimum=0), "unit": "mm"} for t, v in zip(ends, values)]
        return {**base, "status": "available", "message": None, "intervals": intervals}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return {**base, "status": "invalid", "message": f"Hourly precipitation unavailable: {exc}", "intervals": []}


def parse_weather(payload: dict, retrieved_at: datetime) -> dict:
    """Validate provider structure and preserve nulls rather than imputing measurements."""
    if payload["utc_offset_seconds"] != 19800:
        raise ValueError("Unexpected timezone offset")
    current = payload["current"]
    units = payload["current_units"]
    daily = payload["daily"]
    daily_units = payload["daily_units"]
    for field, unit in {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm"}.items():
        if current.get(field) is not None and units.get(field) != unit:
            raise ValueError("Unexpected current units")
    for field, unit in {"precipitation_sum": "mm", "temperature_2m_max": "°C", "temperature_2m_min": "°C"}.items():
        if daily_units[field] != unit:
            raise ValueError("Unexpected forecast units")
    valid_at = local_time(current["time"])
    if units.get("time", "iso8601") != "iso8601" or units.get("interval", "seconds") != "seconds":
        raise ValueError("Unexpected current timestamp or interval units")
    age = retrieved_at - valid_at
    if age < -timedelta(minutes=30):
        raise ValueError("Current timestamp is in the future")
    interval = number(current["interval"], minimum=1)
    if interval is None:
        raise ValueError("Missing current interval")
    values = {
        "temperature_c": number(current.get("temperature_2m")),
        "humidity_percent": number(current.get("relative_humidity_2m"), minimum=0, maximum=100),
        "precipitation_mm": number(current.get("precipitation"), minimum=0),
    }
    current_code = number(current.get("weather_code"), minimum=0, maximum=99)
    if current_code is not None and (int(current_code) != current_code or units.get("weather_code") != "wmo code"):
        raise ValueError("Invalid current weather code or units")
    wind = number(current.get("wind_speed_10m"), minimum=0)
    if wind is not None and units.get("wind_speed_10m") not in {"km/h", "m/s", "mp/h", "kn"}:
        raise ValueError("Unexpected current wind units")
    field_status = {field: "missing" if current.get(field) is None else "available"
                    for field in ("temperature_2m", "relative_humidity_2m", "precipitation", "weather_code", "wind_speed_10m")}
    days = daily["time"]
    if not isinstance(days, list) or len(days) > 7:
        raise ValueError("Expected at most seven forecast days")
    for field in ("precipitation_sum", "temperature_2m_max", "temperature_2m_min"):
        if not isinstance(daily[field], list) or len(daily[field]) != len(days):
            raise ValueError("Mismatched forecast arrays")
    dates = [date.fromisoformat(day) for day in days]
    start = retrieved_at.astimezone(IST).date()
    expected_dates = [start + timedelta(days=i) for i in range(7)]
    if any(raw != day.isoformat() for raw, day in zip(days, dates)) or dates != sorted(set(dates)) or any(day not in expected_dates for day in dates):
        raise ValueError("Forecast dates must be unique, ordered and within the requested local week")
    codes = daily.get("weather_code", [None] * len(days))
    if not isinstance(codes, list) or len(codes) != len(days):
        raise ValueError("Mismatched weather-code array")
    if "weather_code" in daily and daily_units.get("weather_code") != "wmo code":
        raise ValueError("Unexpected weather-code units")
    forecast = []
    for i, day in enumerate(days):
        low = number(daily["temperature_2m_min"][i])
        high = number(daily["temperature_2m_max"][i])
        if low is not None and high is not None and low > high:
            raise ValueError("Inverted temperature range")
        code = number(codes[i], minimum=0, maximum=99)
        if code is not None and int(code) != code:
            raise ValueError("Weather code must be an integer")
        forecast.append({
            "date": day, "weather_code": code,
            "precipitation_mm": number(daily["precipitation_sum"][i], minimum=0),
            "temperature_min_c": low, "temperature_max_c": high,
        })
    readings = list(values.values()) + [v for v in (current_code, wind) if v is not None] + [v for day in forecast for k, v in day.items() if k != "date"]
    if all(v is None for v in readings):
        raise ValueError("No weather values available")
    valid_dates = {day["date"] for day in forecast if any(v is not None for k, v in day.items() if k != "date")}
    missing_dates = [day.isoformat() for day in expected_dates if day.isoformat() not in valid_dates]
    partial = bool(missing_dates) or any(v is None for v in readings)
    grid = {"latitude": number(payload["latitude"], minimum=-90, maximum=90),
            "longitude": number(payload["longitude"], minimum=-180, maximum=180)}
    if any(value is None for value in grid.values()):
        raise ValueError("Provider grid coordinates unavailable")
    return {
        "status": "partial" if partial else "available",
        "message": "Forecast coverage or some values are unavailable." if partial else None,
        "forecast_coverage": {"requested_days": 7, "returned_days": len(forecast), "valid_days": len(valid_dates),
                              "missing_dates": missing_dates, "complete": not missing_dates,
                              "start_date": start.isoformat(), "end_date": expected_dates[-1].isoformat(),
                              "timezone": "Asia/Kolkata", "day_definition": "local_calendar_day"},
        "forecast_units": {"precipitation_mm": "mm", "temperature_min_c": "°C", "temperature_max_c": "°C", "weather_code": "wmo code"},
        "location": LOCATION, "source": SOURCE,
        "grid_location": grid,
        "timezone": "Asia/Kolkata",
        "retrieved_at": retrieved_at.isoformat(),
        "observation_time": None,
        "forecast_issued_at": None,
        "current": {
            "valid_at": valid_at.isoformat(), "interval_seconds": interval,
            "stale": age > timedelta(minutes=90), **values,
            "weather_code": current_code, "wind_speed": wind,
            "wind_speed_unit": units.get("wind_speed_10m") if wind is not None else None,
            "field_status": field_status,
            "precipitation_window_start": (valid_at - timedelta(seconds=interval)).isoformat(),
            "precipitation_window_end": valid_at.isoformat(),
        },
        "forecast": forecast,
        "hourly_precipitation": parse_hourly(payload),
    }


def retry_after(value, now):
    if not value:
        return None
    try:
        seconds = float(value) if value.strip().isdigit() else (parsedate_to_datetime(value) - now).total_seconds()
        return max(0, seconds) if isfinite(seconds) else None
    except (ValueError, TypeError, OverflowError):
        return None


async def fetch_weather(client, params):
    """One bounded call per session attempt; browser owns bounded transient backoff."""
    try:
        async with asyncio.timeout(10):
            response = await client.get(API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        kind = "rate_limited" if status == 429 else "provider_unavailable" if status >= 500 else "provider_http_error"
        message = ("Open-Meteo's free usage limit for this network was reached (HTTP 429); weather returns automatically once it resets."
                   if status == 429 else f"Open-Meteo request returned HTTP {status}.")
        raise WeatherUnavailable(message, kind=kind, upstream_status=status,
                                 retry_after_seconds=retry_after(exc.response.headers.get("retry-after"), datetime.now(timezone.utc))) from exc
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise WeatherUnavailable("Weather provider could not be reached: request timed out.", kind="timeout") from exc
    except httpx.HTTPError as exc:
        raise WeatherUnavailable("Weather provider could not be reached: network failure.", kind="network_failure") from exc
    try:
        return parse_weather(response.json(), datetime.now(timezone.utc))
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError) as exc:
        raise WeatherUnavailable(f"Weather provider returned incomplete or invalid data: {exc}", kind="invalid_response", upstream_status=response.status_code) from exc


class OpenMeteoAdapter:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self) -> dict:
        return await fetch_weather(self.client, PARAMS)
