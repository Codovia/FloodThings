#!/usr/bin/env bash
# Loopback demonstration launcher. Configuration is inherited, never sourced.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$ROOT"
case "${1:-}" in
  --help|-h)
    printf 'Usage: ./start.sh [--check|--help]\nStarts the existing local database, FastAPI and Vite. Ctrl+C stops only owned web processes.\nRequires privately exported DATABASE_URL and SHELTER_DATABASE_URL. No installs or migrations.\nDefaults: backend 18050, frontend 14180; override FLOODPULSE_BACKEND_PORT/FLOODPULSE_FRONTEND_PORT.\n--check checks readiness without starting any service.\n'
    exit 0 ;;
  ''|--check) [[ $# -le 1 ]] || { printf 'Unexpected arguments. Use --help.\n' >&2; exit 1; } ;;
  *) printf 'Unknown option. Use --help.\n' >&2; exit 1 ;;
esac
fail() { printf 'FloodPulse: %s\n' "$1" >&2; exit 1; }
printf 'FloodPulse — Starting Application\n'
for command in node npm docker flock setsid timeout curl; do
  command -v "$command" >/dev/null || fail "Missing $command; install project prerequisites separately."
done
VENV="$ROOT/backend/.venv"
[[ -x "$VENV/bin/python" && -r "$VENV/bin/activate" ]] || fail 'Missing backend/.venv; follow README setup before launching.'
# shellcheck source=/dev/null
source "$VENV/bin/activate"
export PYTHONDONTWRITEBYTECODE=1
export FLOODPULSE_BACKEND_PORT=${FLOODPULSE_BACKEND_PORT:-18050}
export FLOODPULSE_FRONTEND_PORT=${FLOODPULSE_FRONTEND_PORT:-14180}
export LOCATION_DIRECTORY_BACKEND=${LOCATION_DIRECTORY_BACKEND:-postgres}
export SHELTER_COOKIE_SECURE=${SHELTER_COOKIE_SECURE:-false}
export SHELTER_DIRECTORY_MODE=${SHELTER_DIRECTORY_MODE:-live}
export SHELTER_PUBLIC_ORIGIN=${SHELTER_PUBLIC_ORIGIN:-http://127.0.0.1:$FLOODPULSE_FRONTEND_PORT}
RUNTIME="$ROOT/data/tmp/launcher"
mkdir -p "$RUNTIME"
exec 9>"$RUNTIME/lock"
flock -n 9 || fail 'A FloodPulse launcher is already running for this checkout.'
PIDS=()
cleanup() {
  trap '' INT TERM
  for pid in "${PIDS[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  for ((n=0; n<30; n++)); do
    alive=false
    for pid in "${PIDS[@]}"; do kill -0 -- "-$pid" 2>/dev/null && alive=true; done
    [[ "$alive" == false ]] && break
    sleep 0.1
  done
  for pid in "${PIDS[@]}"; do
    kill -KILL -- "-$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'printf "\nStopping FloodPulse web services; database left running.\n"; exit 130' INT
trap 'exit 143' TERM
printf '[1/5] Checking Python, Node and private configuration...\n'
"$VENV/bin/python" - preflight <<'PY'
import importlib, os, socket, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
try:
    for name in ['fastapi', 'uvicorn', 'httpx', 'sqlalchemy', 'alembic', 'psycopg', 'geoalchemy2', 'numpy', 'sklearn']:
        importlib.import_module(name)
    from sqlalchemy.engine import make_url
    from app.shelter_security import SecurityConfig
    from app.rainfall_outlook import RainfallModel
    RainfallModel()  # Loads/checks the existing artifact; never trains.
    ports = [int(os.environ[k]) for k in ['FLOODPULSE_BACKEND_PORT', 'FLOODPULSE_FRONTEND_PORT']]
    assert all(1024 <= p <= 65535 for p in ports) and ports[0] != ports[1]
    urls = [make_url(os.environ[k]) for k in ['DATABASE_URL', 'SHELTER_DATABASE_URL']]
    assert all(u.drivername in ['postgresql', 'postgresql+psycopg'] and u.host == '127.0.0.1' and u.port == 55436 and u.database == 'floodpulse_directory' for u in urls)
    assert os.environ['LOCATION_DIRECTORY_BACKEND'] == 'postgres'
    assert os.environ['SHELTER_DIRECTORY_MODE'] in ['live', 'demonstration']
    config = SecurityConfig()
    assert not config.secure and config.origin == f'http://127.0.0.1:{ports[1]}'
    for port in ports:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
except OSError:
    sys.exit('Port unavailable or artifact/environment missing. Check configured ports and README prerequisites; no existing process was stopped.')
except Exception:
    sys.exit('Python dependencies, model, ports or private configuration invalid. Supply DATABASE_URL/SHELTER_DATABASE_URL for the documented database and matching loopback origin; values are never printed.')
PY
node --input-type=module <<'JS'
import fs from 'node:fs'
import path from 'node:path'
try {
  const [major,minor]=process.versions.node.split('.').map(Number)
  if (!(major===20&&minor>=19 || major===22&&minor>=12 || major>22)) throw Error()
  const pkg=JSON.parse(fs.readFileSync('frontend/package.json'))
  for(const name of ['react','react-dom','leaflet','vite']) {
    const installed=JSON.parse(fs.readFileSync(path.join('frontend/node_modules',name,'package.json')))
    if(installed.version!==(pkg.dependencies?.[name]||pkg.devDependencies?.[name]))throw Error()
  }
} catch {
  console.error('Node/Vite dependencies missing or incompatible. Follow README/npm ci setup separately; launcher installs nothing.')
  process.exit(1)
}
JS
DB=floodpulse-sprint6-db
printf '[2/5] Checking PostgreSQL/PostGIS container...\n'
timeout 5 docker info >/dev/null 2>&1 || fail 'Docker unavailable. Start Docker or obtain access to its daemon; no service was recreated.'
state=$(timeout 5 docker inspect --format '{{.State.Status}}' "$DB" 2>/dev/null) || fail 'Existing floodpulse-sprint6-db container missing. Provision the documented database separately; no container or volume was created.'
if [[ "$state" != running ]]; then
  [[ "${1:-}" != --check ]] || fail 'Database is stopped; normal ./start.sh can start the existing container.'
  [[ "$state" == exited || "$state" == created ]] || fail 'Database is paused/restarting or otherwise unavailable; inspect Docker separately.'
  timeout 10 docker start "$DB" >/dev/null 2>&1 || fail 'Could not start the existing database container.'
fi
ready=false
for ((n=0; n<30; n++)); do
  if timeout 4 docker exec "$DB" pg_isready -U postgres -d floodpulse_directory >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]] || fail 'PostgreSQL did not become ready. Inspect database logs separately; data and volumes were not reset.'
printf '[3/5] Checking schema, permissions and active directory (read-only)...\n'
"$VENV/bin/python" - database <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
engines = []
try:
    from sqlalchemy import inspect, text
    from app.location_database import database_engine, DatabaseLocationStore, metadata
    from app.shelter_schema import SHELTER_TABLES
    from app.notification_schema import NOTIFICATION_TABLES
    for key, tables in [('DATABASE_URL', list(metadata.tables.values())), ('SHELTER_DATABASE_URL', [*SHELTER_TABLES, *NOTIFICATION_TABLES])]:
        engine = database_engine(os.environ[key]); engines.append(engine)
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            connection.execute(text('SELECT postgis_lib_version()')).scalar_one()
            inspector = inspect(connection)
            for table in tables:
                assert {c.name for c in table.columns} <= {c['name'] for c in inspector.get_columns(table.name)}
                connection.execute(table.select().limit(0))
            assert inspector.has_table('alembic_version')
            if key == 'SHELTER_DATABASE_URL':
                for table, privileges in [('shelter_sessions', 'INSERT,UPDATE,DELETE'), ('shelter_login_limits', 'INSERT,UPDATE,DELETE'), ('emergency_shelters', 'INSERT,UPDATE'), ('shelter_audit', 'INSERT'), ('admin_notifications', 'INSERT,UPDATE')]:
                    for privilege in privileges.split(','):
                        assert connection.execute(text('SELECT has_table_privilege(current_user, :table, :privilege)'), {'table': table, 'privilege': privilege}).scalar_one()
    DatabaseLocationStore(engines[0]).load()
except Exception:
    sys.exit('Database/schema/directory unavailable. Check private connections, PostGIS, Alembic upgrade head, directory import and documented role grants in a separate maintenance process. No migration/import was run.')
finally:
    for engine in engines:
        engine.dispose()
PY
[[ "${1:-}" != --check ]] || { printf 'Checks passed. No service was started and no data changed.\n'; exit 0; }
# Each child owns a new session/process group; close the inherited launcher lock.
printf '[4/5] Starting FastAPI on loopback...\n'
setsid env -u LOCATION_DIRECTORY_ADMIN_URL "$VENV/bin/python" -B -m uvicorn app.main:app --app-dir "$ROOT/backend" --host 127.0.0.1 --port "$FLOODPULSE_BACKEND_PORT" >"$RUNTIME/backend.log" 2>&1 9>&- &
BACKEND_PID=$!; PIDS+=("$BACKEND_PID")
wait_ready() {
  local pid=$1 url=$2 label=$3
  for ((n=0; n<30; n++)); do
    kill -0 "$pid" 2>/dev/null || fail "$label exited. Inspect its private log in data/tmp/launcher; no log contents are printed automatically."
    if curl --silent --fail --max-time 2 "$url" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  fail "$label readiness timed out. Inspect its private log in data/tmp/launcher."
}
wait_ready "$BACKEND_PID" "http://127.0.0.1:$FLOODPULSE_BACKEND_PORT/api/health" FastAPI
# Validate actual database-backed read routes, not just process liveness.
for path in locations/districts shelters; do
  curl --silent --fail --max-time 10 "http://127.0.0.1:$FLOODPULSE_BACKEND_PORT/api/$path" >/dev/null 2>&1 || fail 'API directory/shelter readiness failed; inspect private configuration and logs.'
done
printf '[5/5] Starting React/Vite on loopback...\n'
export FLOODPULSE_API_TARGET="http://127.0.0.1:$FLOODPULSE_BACKEND_PORT"
(
  cd "$ROOT/frontend"
  exec setsid env -u DATABASE_URL -u SHELTER_DATABASE_URL -u LOCATION_DIRECTORY_ADMIN_URL -u TELEGRAM_BOT_TOKEN -u TELEGRAM_DESTINATIONS npm run dev -- --host 127.0.0.1 --port "$FLOODPULSE_FRONTEND_PORT" --strictPort
) >"$RUNTIME/frontend.log" 2>&1 9>&- &
FRONTEND_PID=$!; PIDS+=("$FRONTEND_PID")
wait_ready "$FRONTEND_PID" "$SHELTER_PUBLIC_ORIGIN" React/Vite
printf '\nApplication: %s\nAdmin:       %s/admin\nBackend:     http://127.0.0.1:%s\n\nPress Ctrl+C to stop FloodPulse. No refresh while the browser is closed.\n' "$SHELTER_PUBLIC_ORIGIN" "$SHELTER_PUBLIC_ORIGIN" "$FLOODPULSE_BACKEND_PORT"
if wait -n "$BACKEND_PID" "$FRONTEND_PID"; then :; fi
fail 'A web service exited unexpectedly. Both owned web services will stop; inspect private launcher logs.'
