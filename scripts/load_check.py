"""Simultaneous-visitor check: many people opening FloodPulse at once, on read-only requests only.

Each simulated visitor loads the page and the data a first visit needs that does not call outside providers
(no weather/IMD/Telegram requests, so no quota is spent): health with database, districts, shelters, alert setup,
model results. Reports response times and status codes. All visitors come from one address, so the per-address
public limit (300 requests/minute, rate_limit.py) applies to the whole run; 429 answers show that limit working.

  backend/.venv/bin/python scripts/load_check.py --users 40            # against http://127.0.0.1:14180
  backend/.venv/bin/python scripts/load_check.py --base https://example.org --users 20
"""
import argparse
import asyncio
import collections
import statistics
import time

import httpx

PATHS = ['/', '/api/health/ready', '/api/locations/districts', '/api/shelters', '/api/alerts/subscription', '/api/models/performance']


async def visitor(client, base, results):
    for path in PATHS:
        started = time.perf_counter()
        try:
            status = (await client.get(base + path)).status_code
        except httpx.HTTPError:
            status = 'error'
        results.append((path, status, (time.perf_counter() - started) * 1000))


async def run(base, users):
    results = []
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        started = time.perf_counter()
        await asyncio.gather(*(visitor(client, base, results) for _ in range(users)))
        elapsed = time.perf_counter() - started
    return results, elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:14180')
    parser.add_argument('--users', type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.users <= 200:
        parser.error('--users must be between 1 and 200')
    results, elapsed = asyncio.run(run(args.base.rstrip('/'), args.users))
    times = sorted(ms for _, status, ms in results if status == 200)
    codes = collections.Counter(status for _, status, _ in results)
    print(f'{args.users} simultaneous visitors, {len(results)} requests in {elapsed:.1f} s ({len(results) / elapsed:.0f} requests/s)')
    print('status codes:', dict(sorted(codes.items(), key=str)))
    if times:
        p95 = times[min(len(times) - 1, int(0.95 * len(times)))]
        print(f'successful response time: median {statistics.median(times):.0f} ms, 95th percentile {p95:.0f} ms, slowest {times[-1]:.0f} ms')
    for path in PATHS:
        mine = sorted(ms for p, status, ms in results if p == path and status == 200)
        if mine:
            print(f'  {path:28} median {statistics.median(mine):5.0f} ms   slowest {mine[-1]:5.0f} ms   ({len(mine)} ok)')
    return 0 if codes.get(200, 0) and not codes.get('error') and not any(isinstance(c, int) and c >= 500 for c in codes) else 1


if __name__ == '__main__':
    raise SystemExit(main())
