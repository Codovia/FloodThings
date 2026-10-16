"""Bounded metadata transport shared by the opt-in Home source adapters."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
import httpx
from .weather import retry_after


class PrivateMapTilerLog(logging.Filter):
    def filter(self, record):
        if 'api.maptiler.com' in record.getMessage():
            record.msg, record.args = 'MapTiler HTTP request (location and key omitted)', ()
        elif 'api.open-meteo.com/v1/forecast' in record.getMessage():
            record.msg, record.args = 'Open-Meteo weather HTTP request (point coordinates omitted)', ()
        return True


logging.getLogger('httpx').addFilter(PrivateMapTilerLog())


class CoordinateAccessLog(logging.Filter):
    def filter(self, record):
        # Uvicorn's standard access tuple: client, method, full path, version, status.
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2].split('?', 1)[0]
            if path in {'/api/weather', '/api/ai/rainfall-outlook', '/api/shelters', '/api/risk', '/api/risk/area', '/api/official/warnings'}:
                record.args = (*args[:2], path, *args[3:])
        return True


logging.getLogger('uvicorn.access').addFilter(CoordinateAccessLog())


class SourceFailure(Exception):
    def __init__(self, kind, status=None, retry_seconds=None):
        super().__init__(kind)
        self.kind, self.status, self.retry_seconds = kind, status, retry_seconds


async def read_json(client, url, params=None, limit=65536):
    try:
        async with asyncio.timeout(10):
            async with client.stream('GET', url, params=params) as response:
                if not response.is_success:
                    status = response.status_code
                    raise SourceFailure('rate_limited' if status == 429 else 'provider_unavailable' if status >= 500 else 'provider_http_error', status,
                                        retry_after(response.headers.get('retry-after'), datetime.now(timezone.utc)))
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > limit:
                        raise SourceFailure('response_too_large', response.status_code)
                    raw.extend(chunk)
                return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except SourceFailure:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise SourceFailure('timeout') from None
    except httpx.HTTPError:
        raise SourceFailure('network_failure') from None
    except (ValueError, TypeError):
        raise SourceFailure('invalid_response') from None
