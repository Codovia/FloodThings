"""Per-address request limits for public API endpoints, configurable through environment variables.

Two groups: "expensive" endpoints that call paid or quota-limited providers many times per request
(area risk screen, routing, AI rainfall outlook, admin place lookup) and other public reads.
Login and report submission keep their own PostgreSQL-backed limits (shelters.py, reports.py), and
the Telegram webhook and admin routes are excluded. Counts live in this process: the app runs one
worker by design; a multi-instance deployment would need a shared store.

Settings (requests/seconds):
  FLOODPULSE_RATE_EXPENSIVE   default 30/60
  FLOODPULSE_RATE_PUBLIC      default 300/60
"""
import math
import os
import time
from collections import OrderedDict, deque

from fastapi.responses import JSONResponse

EXPENSIVE = ('/api/risk/area', '/api/route', '/api/ai/rainfall-outlook', '/api/admin/place', '/api/location/address')
EXCLUDED_PREFIXES = ('/api/health', '/api/telegram/webhook', '/api/admin/', '/api/reports')
MAX_TRACKED = 20_000


def parse_rule(value, default):
    try:
        count, seconds = (int(part) for part in str(value).split('/'))
        if count > 0 and seconds > 0:
            return count, seconds
    except (TypeError, ValueError):
        pass
    return default


def group(path):
    if not path.startswith('/api/'):
        return None
    if path in EXPENSIVE:
        return 'expensive'
    if path.startswith(EXCLUDED_PREFIXES):
        return None
    return 'public'


class RateLimiter:
    def __init__(self, rules=None, clock=time.monotonic):
        self.rules = rules or {
            'expensive': parse_rule(os.environ.get('FLOODPULSE_RATE_EXPENSIVE'), (30, 60)),
            'public': parse_rule(os.environ.get('FLOODPULSE_RATE_PUBLIC'), (300, 60)),
        }
        self.clock = clock
        self.hits = OrderedDict()

    def check(self, kind, address):
        """Return seconds to wait, or 0 when the request may proceed (and is counted)."""
        limit, window = self.rules[kind]
        now = self.clock()
        key = (kind, address)
        hits = self.hits.get(key)
        if hits is None:
            hits = self.hits[key] = deque()
            if len(self.hits) > MAX_TRACKED:
                self.hits.popitem(last=False)
        else:
            self.hits.move_to_end(key)
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, math.ceil(hits[0] + window - now))
        hits.append(now)
        return 0


def install(app, limiter=None):
    limiter = limiter or RateLimiter()

    @app.middleware('http')
    async def rate_limit(request, call_next):
        kind = group(request.url.path)
        if kind:
            address = request.client.host if request.client else 'unknown'
            wait = limiter.check(kind, address)
            if wait:
                return JSONResponse(status_code=429, headers={'Retry-After': str(wait), 'Cache-Control': 'no-store'},
                                    content={'status': 'rate_limited', 'failure_kind': 'rate_limited', 'retry_after_seconds': wait,
                                             'message': f'Too many requests from your connection. Please wait {wait} seconds and try again.'})
        return await call_next(request)
    return limiter
