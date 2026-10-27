#!/usr/bin/env bash
# Proves that a FloodPulse backup restores, using the exact pg_dump / pg_restore commands of deploy/backup.sh and
# deploy/restore.sh, on a throwaway copy of the server database (same image, owner, database name and role script).
# Never touches a real database: the container listens on 127.0.0.1 only, gets random passwords and is removed.
#   ./scripts/verify_backup_restore.sh
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
PY="$ROOT/backend/.venv/bin/python"
NAME="floodpulse-restore-check-$$"
PORT=${FLOODPULSE_RESTORE_CHECK_PORT:-55498}
WORK=$(mktemp -d)
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
say() { printf 'restore check: %s\n' "$*"; }
secret() { "$PY" -c 'import secrets;print(secrets.token_hex(16))'; }
ADMIN_PW=$(secret) READER_PW=$(secret) APP_PW=$(secret)

say 'starting a throwaway PostGIS 16 database (as on the server)'
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:5432" \
  -e POSTGRES_DB=floodpulse_directory -e POSTGRES_USER=floodpulse_admin -e POSTGRES_PASSWORD="$ADMIN_PW" \
  -e READER_PASSWORD="$READER_PW" -e APP_PASSWORD="$APP_PW" \
  -v "$ROOT/deploy/db-init:/docker-entrypoint-initdb.d:ro" postgis/postgis:16-3.4 >/dev/null
for _ in $(seq 1 90); do
  # Ready once the init script has created the application role (the server image runs it on first start).
  docker exec "$NAME" psql -U floodpulse_admin -d floodpulse_directory -tAc "SELECT 1 FROM pg_roles WHERE rolname='floodpulse_shelter_app'" 2>/dev/null | grep -q 1 && break
  sleep 1
done
sleep 2
export LOCATION_DIRECTORY_ADMIN_URL="postgresql+psycopg://floodpulse_admin:$ADMIN_PW@127.0.0.1:$PORT/floodpulse_directory"
APP_URL="postgresql+psycopg://floodpulse_shelter_app:$APP_PW@127.0.0.1:$PORT/floodpulse_directory"
cd "$ROOT/backend"
say 'migrating, importing the place directory and granting the application role (as deploy/setup.sh)'
"$PY" -B -m alembic upgrade head >/dev/null 2>&1
"$PY" -B -m app.import_locations >/dev/null
"$PY" -B -m app.mvp_database --grant-to floodpulse_shelter_app >/dev/null

state() {  # row count of every table, the migration version and the marker rows
  "$PY" -B - "$1" <<'PY'
import os, sys
from sqlalchemy import inspect, text
from app.location_database import database_engine
engine = database_engine(os.environ['LOCATION_DIRECTORY_ADMIN_URL'])
with engine.begin() as c:
    if sys.argv[1] == 'seed':
        c.execute(text("INSERT INTO telegram_subscriptions VALUES ('restore-check-marker-before-backup', true, now(), now(), 1, 'RESTORE CHECK')"))
    if sys.argv[1] == 'change':
        c.execute(text("DELETE FROM telegram_subscriptions WHERE subscriber_key='restore-check-marker-before-backup'"))
        c.execute(text("INSERT INTO telegram_subscriptions VALUES ('restore-check-marker-after-backup', true, now(), now(), 2, 'RESTORE CHECK')"))
    tables = sorted(inspect(c).get_table_names())
    counts = {t: c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in tables}
    version = c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    markers = c.execute(text("SELECT subscriber_key FROM telegram_subscriptions WHERE consent_version='RESTORE CHECK' ORDER BY 1")).scalars().all()
engine.dispose()
print(version, len(tables), sum(counts.values()), ','.join(markers), sep='|')
print(';'.join(f'{t}={n}' for t, n in counts.items()), file=sys.stderr)
PY
}
before=$(state seed 2>"$WORK/before.counts")
say "before backup: $(echo "$before" | cut -d'|' -f1) · $(echo "$before" | cut -d'|' -f2) tables · $(echo "$before" | cut -d'|' -f3) rows"

say 'backing up with the deploy/backup.sh command'
docker exec -i "$NAME" pg_dump -U floodpulse_admin -d floodpulse_directory --format=custom > "$WORK/backup.dump"
[[ -s "$WORK/backup.dump" ]] || { say 'FAILED: empty dump'; exit 1; }

state change 2>/dev/null >/dev/null
say 'changed the data after the backup (one row removed, one added)'

say 'restoring with the deploy/restore.sh command'
docker exec -i "$NAME" pg_restore -U floodpulse_admin -d floodpulse_directory --clean --if-exists --single-transaction < "$WORK/backup.dump"

after=$(state check 2>"$WORK/after.counts")
if [[ "$after" == "$before" ]] && cmp -s "$WORK/before.counts" "$WORK/after.counts"; then
  say "restored exactly: same version, same rows in all $(echo "$after" | cut -d'|' -f2) tables; the post-backup change is gone"
else
  say "FAILED: before=$before after=$after"; diff <(tr ';' '\n' <"$WORK/before.counts") <(tr ';' '\n' <"$WORK/after.counts") || true; exit 1
fi
say 'the application role can still use every table after the restore (deploy/restore.sh runs this check too)'
SHELTER_DATABASE_URL="$APP_URL" "$PY" -B -c 'import os;from sqlalchemy import create_engine;from app.mvp_database import check_app_connection;e=create_engine(os.environ["SHELTER_DATABASE_URL"]);c=e.connect();print("restore check:", check_app_connection(c));c.close();e.dispose()'
say 'PASSED (throwaway database removed)'
