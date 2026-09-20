"""
HTTP client for Open-Meteo Historical Weather API (ERA5 Reanalysis).
"""

from __future__ import annotations

import json
import random
import time
from typing import Any
import urllib.parse

import httpx

from app.ingestion.historical.models import ExtractionChunk, ExtractionConfig


class HistoricalExtractionError(Exception):
    """Base exception for historical extraction errors."""

    def __init__(self, message: str, retryable: bool = False, http_status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.http_status = http_status


class RateLimitExceededError(HistoricalExtractionError):
    """Raised when HTTP 429 Too Many Requests is received."""

    def __init__(self, message: str = "HTTP 429 Too Many Requests"):
        super().__init__(message, retryable=True, http_status=429)


class ServerError(HistoricalExtractionError):
    """Raised when HTTP 5xx server error is received."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(
            f"HTTP {status_code} Server Error: {message}",
            retryable=True,
            http_status=status_code,
        )


class MalformedResponseError(HistoricalExtractionError):
    """Raised when response body is not valid JSON or violates expected structure."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class HistoricalOpenMeteoClient:
    """
    Dedicated HTTP client for querying Open-Meteo Historical Weather API.

    Enforces:
    - Explicit `models=era5`
    - Explicit `timezone=UTC`
    - Explicit `precipitation_unit=mm` and `temperature_unit=celsius`
    - Strict timeouts, retry backoff with jitter, and 429 cooldown.
    """

    BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(
        self,
        config: ExtractionConfig | None = None,
        client: httpx.Client | None = None,
    ):
        self.config = config or ExtractionConfig()
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        timeout = httpx.Timeout(
            connect=self.config.connection_timeout,
            read=self.config.read_timeout,
            write=15.0,
            pool=15.0,
        )
        return httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "FloodPulse-HistoricalExtractor/1.0"},
        )

    def build_query_params(self, chunk: ExtractionChunk) -> dict[str, str]:
        """Build deterministic query parameters for a given extraction chunk."""
        lats_str = ",".join(str(c.lat) for c in chunk.cells)
        lons_str = ",".join(str(c.lon) for c in chunk.cells)
        hourly_str = ",".join(self.config.hourly_variables)

        return {
            "latitude": lats_str,
            "longitude": lons_str,
            "start_date": f"{chunk.year}-01-01",
            "end_date": f"{chunk.year}-12-31",
            "hourly": hourly_str,
            "timezone": self.config.timezone,
            "precipitation_unit": self.config.precipitation_unit,
            "temperature_unit": self.config.temperature_unit,
            "models": self.config.model,
        }

    def build_request_url(self, chunk: ExtractionChunk) -> str:
        """Construct full request URL with encoded query string."""
        params = self.build_query_params(chunk)
        query_string = urllib.parse.urlencode(params)
        return f"{self.BASE_URL}?{query_string}"

    def fetch_chunk_payload(
        self, chunk: ExtractionChunk
    ) -> tuple[bytes, dict[str, Any], int, float]:
        """
        Fetch chunk data with conservative retry, backoff, and rate limit handling.

        Returns:
            (raw_bytes, parsed_json, http_status, latency_seconds)
        """
        url = self.BASE_URL
        params = self.build_query_params(chunk)
        client = self._get_client()

        attempt = 0
        last_exception: Exception | None = None

        while attempt < self.config.max_retries:
            attempt += 1
            t0 = time.time()
            try:
                response = client.get(url, params=params)
                latency = time.time() - t0
                status = response.status_code

                if status == 200:
                    raw_bytes = response.content
                    try:
                        parsed_json = json.loads(raw_bytes.decode("utf-8"))
                    except Exception as json_err:
                        raise MalformedResponseError(f"Failed to decode response JSON: {json_err}") from json_err

                    return raw_bytes, parsed_json, status, latency

                elif status == 429:
                    wait_time = 60.0 + random.uniform(1.0, 5.0)
                    if attempt < self.config.max_retries:
                        time.sleep(wait_time)
                        continue
                    raise RateLimitExceededError("HTTP 429 Rate limit exceeded after maximum retries")

                elif 500 <= status < 600:
                    wait_time = min(60.0, (self.config.backoff_factor ** attempt) * 2.0) + random.uniform(0.5, 2.0)
                    if attempt < self.config.max_retries:
                        time.sleep(wait_time)
                        continue
                    raise ServerError(status, response.text[:200])

                else:
                    # Client errors (400, 404, etc.) are non-retryable
                    raise HistoricalExtractionError(
                        f"HTTP {status} Client Error: {response.text[:200]}",
                        retryable=False,
                        http_status=status,
                    )

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as net_err:
                last_exception = net_err
                if attempt < self.config.max_retries:
                    wait_time = min(60.0, (self.config.backoff_factor ** attempt) * 2.0) + random.uniform(0.5, 2.0)
                    time.sleep(wait_time)
                    continue
                raise HistoricalExtractionError(
                    f"Network error after {attempt} attempts: {net_err}",
                    retryable=True,
                ) from net_err

            except MalformedResponseError:
                raise

            except HistoricalExtractionError:
                raise

            except Exception as unk_err:
                raise HistoricalExtractionError(
                    f"Unexpected client error: {unk_err}",
                    retryable=False,
                ) from unk_err

        raise HistoricalExtractionError(
            f"Extraction failed after {attempt} attempts. Last error: {last_exception}",
            retryable=True,
        )
