#!/usr/bin/env bash
# Back up the FloodPulse database to deploy/backups/ (private folder), keeping the newest 14.
# Usage:  ./backup.sh          Daily at 02:00 (crontab -e):  0 2 * * * cd ~/floodpulse/deploy && ./backup.sh
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p backups
file="backups/floodpulse-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U floodpulse_admin -d floodpulse_directory --format=custom > "$file.partial"
[[ -s "$file.partial" ]] || { rm -f "$file.partial"; echo 'Backup failed: empty dump.' >&2; exit 1; }
mv "$file.partial" "$file"
ls -1t backups/floodpulse-*.dump | tail -n +15 | xargs -r rm --
echo "Backup written: deploy/$file ($(du -h "$file" | cut -f1))"
