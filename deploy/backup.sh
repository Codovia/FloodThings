#!/usr/bin/env bash
# Back up the FloodPulse database to deploy/backups/ (private folder), keeping the newest 14.
# Usage:  ./backup.sh          Daily at 02:00 (crontab -e):  0 2 * * * cd ~/floodpulse/deploy && ./backup.sh
# ./auto-update.sh runs ./backup.sh pre-update: those backups are kept separately (newest 14), so frequent
# updates never push out the daily ones.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
kind=${1:-floodpulse}
[[ "$kind" == floodpulse || "$kind" == pre-update ]] || { echo 'Usage: ./backup.sh [pre-update]' >&2; exit 2; }
mkdir -p backups
file="backups/$kind-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U floodpulse_admin -d floodpulse_directory --format=custom > "$file.partial"
[[ -s "$file.partial" ]] || { rm -f "$file.partial"; echo 'Backup failed: empty dump.' >&2; exit 1; }
mv "$file.partial" "$file"
ls -1t backups/"$kind"-*.dump | tail -n +15 | xargs -r rm --
echo "Backup written: deploy/$file ($(du -h "$file" | cut -f1))"
