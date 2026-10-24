#!/usr/bin/env bash
# Restore the FloodPulse database from a backup made by ./backup.sh. This REPLACES current data.
# Usage:  ./restore.sh backups/floodpulse-YYYYMMDD-HHMMSS.dump   (or backups/pre-update-....dump)
set -euo pipefail
cd "$(dirname "$0")"
[[ $# -eq 1 && -s "$1" ]] || { echo 'Usage: ./restore.sh backups/floodpulse-....dump' >&2; exit 2; }
if [[ "${FLOODPULSE_RESTORE_CONFIRM:-}" != RESTORE ]]; then
  read -r -p 'This replaces all current FloodPulse data with the backup. Type RESTORE to continue: ' answer
  [[ "$answer" == RESTORE ]] || { echo 'Cancelled; nothing changed.'; exit 1; }
fi
echo 'Stopping the app during the restore...'
docker compose stop app caddy
docker compose exec -T db pg_restore -U floodpulse_admin -d floodpulse_directory --clean --if-exists --single-transaction < "$1"
echo 'Starting the app...'
docker compose up -d app caddy
docker compose run --rm --no-deps app python -B -m app.mvp_database
echo 'Restore finished.'
