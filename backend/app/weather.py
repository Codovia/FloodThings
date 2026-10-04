"""Read-only Open-Meteo adapter: no database, archive writes or fallback values."""
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
    "current": "temperature_2m,relative_humidity_2m,precipitation",
    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
    "timezone": "Asia/Kolkata",
    "forecast_days": 3,
    "temperature_unit": "celsius",
    "precipitation_unit": "mm",
}


class WeatherUnavailable(Exception):
    """The provider failed or returned an invalid response."""


def unavailable(message: str) -> dict:
    return {
        "status": "unavailable", "message": message,
        "location": LOCATION, "source": SOURCE,
        "retrieved_at": None, "observation_time": None,
        "forecast_issued_at": None, "current": None, "forecast": [],
    }


def number(value, *, minimum=None, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Invalid numeric value")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError("Value outside valid range")
    return value


def parse_weather(payload: dict, retrieved_at: datetime) -> dict:
    """Validate provider structure and preserve nulls rather than imputing measurements."""
    if payload["utc_offset_seconds"] != 19800:
        raise ValueError("Unexpected timezone offset")
    current = payload["current"]
    units = payload["current_units"]
    daily = payload["daily"]
    daily_units = payload["daily_units"]
    for field, unit in {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm"}.items():
        if units[field] != unit:
            raise ValueError("Unexpected current units")
    for field, unit in {"precipitation_sum": "mm", "temperature_2m_max": "°C", "temperature_2m_min": "°C"}.items():
        if daily_units[field] != unit:
            raise ValueError("Unexpected forecast units")
    valid_at = datetime.fromisoformat(current["time"])
    if valid_at.tzinfo is not None:
        raise ValueError("Expected local provider time")
    valid_at = valid_at.replace(tzinfo=IST)
    age = retrieved_at - valid_at
    if age < -timedelta(minutes=30):
        raise ValueError("Current timestamp is in the future")
    interval = number(current["interval"], minimum=1)
    if interval is None:
        raise ValueError("Missing current interval")
    values = {
        "temperature_c": number(current["temperature_2m"]),
        "humidity_percent": number(current["relative_humidity_2m"], minimum=0, maximum=100),
        "precipitation_mm": number(current["precipitation"], minimum=0),
    }
    days = daily["time"]
    if not isinstance(days, list) or len(days) != 3:
        raise ValueError("Expected three forecast days")
    for field in ("precipitation_sum", "temperature_2m_max", "temperature_2m_min"):
        if not isinstance(daily[field], list) or len(daily[field]) != len(days):
            raise ValueError("Mismatched forecast arrays")
    dates = [date.fromisoformat(day) for day in days]
    if dates != [dates[0] + timedelta(days=i) for i in range(3)]:
        raise ValueError("Forecast dates are not consecutive")
    if dates[0] != retrieved_at.astimezone(IST).date():
        raise ValueError("Forecast does not start today")
    forecast = []
    for i, day in enumerate(days):
        low = number(daily["temperature_2m_min"][i])
        high = number(daily["temperature_2m_max"][i])
        if low is not None and high is not None and low > high:
            raise ValueError("Inverted temperature range")
        forecast.append({
            "date": day,
            "precipitation_mm": number(daily["precipitation_sum"][i], minimum=0),
            "temperature_min_c": low, "temperature_max_c": high,
        })
    readings = list(values.values()) + [v for day in forecast for k, v in day.items() if k != "date"]
    if all(v is None for v in readings):
        raise ValueError("No weather values available")
    return {
        "status": "partial" if any(v is None for v in readings) else "available",
        "message": "Some values are unavailable." if any(v is None for v in readings) else None,
        "location": LOCATION, "source": SOURCE,
        "grid_location": {
            "latitude": number(payload["latitude"], minimum=-90, maximum=90),
            "longitude": number(payload["longitude"], minimum=-180, maximum=180),
        },
        "timezone": "Asia/Kolkata",
        "retrieved_at": retrieved_at.isoformat(),
        "observation_time": None,
        "forecast_issued_at": None,
        "current": {
            "valid_at": valid_at.isoformat(), "interval_seconds": interval,
            "stale": age > timedelta(minutes=90), **values,
        },
        "forecast": forecast,
    }


class OpenMeteoAdapter:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self) -> dict:
        try:
            response = await self.client.get(API_URL, params=PARAMS)
            response.raise_for_status()
            return parse_weather(response.json(), datetime.now(timezone.utc))
        except httpx.HTTPError as exc:
            raise WeatherUnavailable("Weather provider could not be reached. Try again later.") from exc
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            raise WeatherUnavailable("Weather provider returned incomplete or invalid data.") from exc
