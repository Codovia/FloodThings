#!/usr/bin/env bash
# Local maintenance only: bring this laptop's database to the current migration (see scripts/upgrade_database.py).
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ -x "$ROOT/backend/.venv/bin/python" ]] || {
  printf 'Missing backend/.venv. Follow README prerequisites first.\n' >&2
  exit 1
}
exec "$ROOT/backend/.venv/bin/python" -B "$ROOT/scripts/upgrade_database.py" "$@"
