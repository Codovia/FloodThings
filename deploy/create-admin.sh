#!/usr/bin/env bash
# Create (or, with --reset-password, rotate) an administrator. The password is typed privately
# (16–128 characters), hashed with scrypt and never stored in a file or printed.
# Usage:  ./create-admin.sh USERNAME            ./create-admin.sh USERNAME --reset-password
set -euo pipefail
cd "$(dirname "$0")"
[[ $# -ge 1 ]] || { echo 'Usage: ./create-admin.sh USERNAME [--reset-password]' >&2; exit 2; }
password=$(grep -E '^MAINTENANCE_PASSWORD=' .env | tail -1 | cut -d= -f2-)
[[ -n "$password" ]] || { echo 'Run ./setup.sh first.' >&2; exit 1; }
export LOCATION_DIRECTORY_ADMIN_URL="postgresql+psycopg://floodpulse_admin:${password}@db:5432/floodpulse_directory"
docker compose run --rm --no-deps -e LOCATION_DIRECTORY_ADMIN_URL app python -B -m app.provision_shelter_admin --username "$1" "${@:2}"
