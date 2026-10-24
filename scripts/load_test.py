"""Simultaneous-users test: many simulated visitors open Home at the same moment.

Each visitor loads the page, then the same API calls Home makes for one of a few Karnataka towns.
Reports how many requests succeeded, were rate limited or failed, and response times.
Use against a test or staging server; it calls the live weather and warning providers through the
app, so keep the visitor count modest (the app caches these, so repeated towns are cheap).

    python scripts/load_test.py https://localhost:8443 --users 50 --insecure
"""
import argparse
import asyncio
import statistics
import time

import httpx

TOWNS = [(13.3409, 74.7421), (12.8698, 74.8430), (13.6251, 74.6911), (12.9716, 77.5946), (15.8497, 74.4977)]


def home_requests(index):
    lat, lon = TOWNS[index % len(TOWNS)]
    point = f'latitude={lat}&longitude={lon}'
    return ['/', '/api/health', f'/api/weather?{point}', f'/api/official/warnings?{point}', '/api/official/districts',
            f'/api/risk?{point}', f'/api/shelters?{point}', '/api/locations/districts']


async def visitor(client, index, results):
    for path in home_requests(index):
        started = time.perf_counter()
        try:
            response = await client.get(path)
            results.append((path, response.status_code, time.perf_counter() - started))
        except httpx.HTTPError as error:
            results.append((path, type(error).__name__, time.perf_counter() - started))


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('base_url')
    parser.add_argument('--users', type=int, default=50)
    parser.add_argument('--insecure', action='store_true', help='accept a self-signed certificate (local tests only)')
    args = parser.parse_args()
    results = []
    limits = httpx.Limits(max_connections=args.users)
    async with httpx.AsyncClient(base_url=args.base_url, verify=not args.insecure, timeout=30, limits=limits) as client:
        started = time.perf_counter()
        await asyncio.gather(*(visitor(client, i, results) for i in range(args.users)))
        elapsed = time.perf_counter() - started
    ok = [r for r in results if r[1] == 200]
    limited = [r for r in results if r[1] == 429]
    failed = [r for r in results if r[1] not in (200, 429)]
    times = sorted(r[2] for r in ok)
    print(f'{args.users} simultaneous visitors, {len(results)} requests in {elapsed:.1f} s')
    print(f'  OK: {len(ok)}   rate limited (429): {len(limited)}   failed: {len(failed)}')
    if times:
        p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
        print(f'  response time: median {statistics.median(times):.2f} s, 95th percentile {p95:.2f} s, slowest {times[-1]:.2f} s')
    for path, status, _ in failed[:10]:
        print(f'  failed: {status} {path.split("?")[0]}')


if __name__ == '__main__':
    asyncio.run(main())
