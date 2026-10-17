#!/usr/bin/env bash
# One command to install or update FloodPulse on a server with Docker.
# First run: creates deploy/.env passwords, the database, tables, Karnataka place directory and
# restricted permissions, then starts the app with HTTPS. Later runs: rebuild and migrate safely.
# No secret is printed. Usage:  cd deploy && ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"
say() { printf '\n==> %s\n' "$1"; }
fail() { printf 'FloodPulse setup: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null || fail 'Docker is not installed (see docs/AZURE_HOSTING.md step 4).'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose plugin is missing.'
[[ -f .env ]] || fail 'Create deploy/.env first: cp env.example .env, then set FLOODPULSE_DOMAIN.'
chmod 600 .env

value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//"; }
[[ -n "$(value FLOODPULSE_DOMAIN)" ]] || fail 'Set FLOODPULSE_DOMAIN in deploy/.env (for example floodpulse-smvitm.centralindia.cloudapp.azure.com).'
if [[ -z "$(value FLOODPULSE_ORIGIN)" ]]; then
  printf 'FLOODPULSE_ORIGIN=https://%s\n' "$(value FLOODPULSE_DOMAIN)" >> .env
fi
for name in MAINTENANCE_PASSWORD READER_PASSWORD APP_PASSWORD; do
  if [[ -z "$(value "$name")" ]]; then
    printf '%s=%s\n' "$name" "$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')" >> .env
    echo "Generated $name (stored only in deploy/.env)."
  fi
done

say 'Building the FloodPulse image (first time takes a few minutes)'
docker compose build app

say 'Starting the database'
docker compose up -d --wait db

# The owner (maintenance) login is used only by these one-off commands, never by the running app.
export LOCATION_DIRECTORY_ADMIN_URL="postgresql+psycopg://floodpulse_admin:$(value MAINTENANCE_PASSWORD)@db:5432/floodpulse_directory"
maintenance() { docker compose run --rm --no-deps -e LOCATION_DIRECTORY_ADMIN_URL app "$@"; }

say 'Applying database migrations'
maintenance alembic upgrade head

say 'Importing the Karnataka place directory (safe to repeat)'
maintenance python -B -m app.import_locations

say 'Granting least-privilege table permissions'
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U floodpulse_admin -d floodpulse_directory -q <<'SQL'
GRANT CONNECT ON DATABASE floodpulse_directory TO floodpulse_location_reader;
GRANT USAGE ON SCHEMA public TO floodpulse_location_reader;
GRANT SELECT ON location_directory_versions, location_directory_districts, location_directory_localities,
  location_directory_identifiers, location_directory_active TO floodpulse_location_reader;
SQL
maintenance python -B -m app.mvp_database --grant-to floodpulse_shelter_app

say 'Starting FloodPulse and HTTPS'
docker compose up -d app caddy
docker compose run --rm --no-deps app python -B -m app.mvp_database
unset LOCATION_DIRECTORY_ADMIN_URL

printf '\nFloodPulse is starting at %s\n' "$(value FLOODPULSE_ORIGIN)"
printf 'The HTTPS certificate is issued on the first visit; allow up to a minute.\n'
printf 'Next: ./create-admin.sh to create your administrator account.\n'
