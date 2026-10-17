#!/bin/bash
# Runs once, when the database volume is first created. Creates the two restricted logins the
# app uses; table permissions are granted after migrations by deploy/setup.sh.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v reader_pw="$READER_PASSWORD" -v app_pw="$APP_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE floodpulse_location_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD :'reader_pw';
CREATE ROLE floodpulse_shelter_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD :'app_pw';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
