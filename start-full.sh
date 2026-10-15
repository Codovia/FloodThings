#!/usr/bin/env bash
# Separate wrapper; database and web lifecycle remain owned by start.sh.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  printf 'Usage: ./start-full.sh [--telegram] [--check]\nWithout --telegram: start the existing local application.\n--telegram: also start restricted proxy/Quick Tunnel and safely register its webhook.\n--check: read-only readiness; no service start or Telegram request.\nCtrl+C stops owned web/tunnel processes; PostgreSQL and webhook registration remain.\n'
  exit 0
fi
[[ -x "$ROOT/backend/.venv/bin/python" ]] || { printf 'FloodPulse: backend/.venv is missing; follow README setup.\n' >&2; exit 1; }
exec "$ROOT/backend/.venv/bin/python" -B "$ROOT/scripts/full_launcher.py" "$@"
