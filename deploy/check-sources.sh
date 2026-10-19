#!/usr/bin/env bash
# Diagnose whether this server can reach the official and weather sources FloodPulse uses.
# Prints only status codes, timings and error types. Usage:  ./check-sources.sh
cd "$(dirname "$0")"
sources=(
  "IMD|https://reactjs.imd.gov.in/geoserver/ows?service=WFS&request=GetCapabilities"
  "SACHET|https://sachet.ndma.gov.in/cap_public_website/rss/rss_karnataka.xml"
  "Open-Meteo|https://api.open-meteo.com/v1/forecast?latitude=13.34&longitude=74.74&current=temperature_2m"
)
echo "== Server public address"; curl -s -4 -m 10 https://ifconfig.me; echo
for proto in 4 6; do
  echo "== From the server itself (IPv$proto)"
  for entry in "${sources[@]}"; do
    name=${entry%%|*}; url=${entry#*|}
    printf '  %-11s ' "$name"
    curl -s -$proto -o /dev/null -m 20 -w '%{http_code} in %{time_total}s\n' "$url" || echo "FAILED (curl exit $?)"
  done
done
echo "== From inside the app container"
docker compose run --rm --no-deps -T app python -B - <<'PY'
import httpx
for name, url in [('IMD', 'https://reactjs.imd.gov.in/geoserver/ows?service=WFS&request=GetCapabilities'),
                  ('SACHET', 'https://sachet.ndma.gov.in/cap_public_website/rss/rss_karnataka.xml'),
                  ('Open-Meteo', 'https://api.open-meteo.com/v1/forecast?latitude=13.34&longitude=74.74&current=temperature_2m')]:
    try:
        r = httpx.get(url, timeout=20)
        print(f'  {name:<11} {r.status_code}')
    except Exception as e:
        print(f'  {name:<11} ERROR {type(e).__name__}: {str(e)[:150]}')
PY
echo "== Recent official-source errors in the app log"
docker compose logs --tail 300 app 2>/dev/null | grep "official source" | tail -5 || true
