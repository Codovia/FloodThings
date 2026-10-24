#!/usr/bin/env bash
# Loopback demonstration launcher (run it through ./floodpulse.sh). Private configuration is parsed, never sourced.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)  # this file lives in scripts/
cd "$ROOT"
case "${1:-}" in
  --help|-h)
    printf 'Usage: scripts/app_launcher.sh [--check|--help] (normally run through ./floodpulse.sh)\nStarts the existing local database, FastAPI and Vite. Ctrl+C stops only owned web processes.\nUses private DATABASE_URL/SHELTER_DATABASE_URL environment or data/tmp/launcher/config.json references; optional root .env loads Telegram keys only (0600). Explicit environment takes precedence. No installs or migrations.\nDefaults: backend 18050, frontend 14180; override FLOODPULSE_BACKEND_PORT/FLOODPULSE_FRONTEND_PORT.\n--check checks readiness without starting any service.\n'
    exit 0 ;;
  ''|--check) [[ $# -le 1 ]] || { printf 'Unexpected arguments. Use --help.\n' >&2; exit 1; } ;;
  *) printf 'Unknown option. Use --help.\n' >&2; exit 1 ;;
esac
fail() { printf 'FloodPulse: %s\n' "$1" >&2; exit 1; }
for command in node npm docker flock timeout curl; do
  command -v "$command" >/dev/null || fail "Missing $command; install project prerequisites separately."
done
VENV="$ROOT/backend/.venv"
[[ -x "$VENV/bin/python" && -r "$VENV/bin/activate" ]] || fail 'Missing backend/.venv; follow README setup before launching.'
# shellcheck source=/dev/null
source "$VENV/bin/activate"
if [[ "${FLOODPULSE_CONFIG_LOADED:-}" != 1 ]]; then
  exec "$VENV/bin/python" -B "$ROOT/scripts/launcher_config.py" "$ROOT" "$@"
fi
printf 'FloodPulse — Starting Application\n'
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
# Recovery requires the exclusive checkout lock and a private, matching ownership
# receipt. --check remains read-only and never terminates stale/unrelated services.
if [[ "${1:-}" != --check ]]; then
  "$VENV/bin/python" -B "$ROOT/scripts/launcher_processes.py" recover "$ROOT"
fi
printf '[1/5] Checking Python, Node and private configuration...\n'
"$VENV/bin/python" - preflight <<'PY'
import importlib, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
sys.path.insert(0, str(Path.cwd() / 'scripts'))
for name in ['DATABASE_URL', 'SHELTER_DATABASE_URL']:
    if not os.environ.get(name):
        sys.exit(f'Missing {name}. Configure the private launcher profile data/tmp/launcher/config.json or export this variable; activating a virtual environment does not configure database connections. See README.')
for name in ['fastapi', 'uvicorn', 'httpx', 'sqlalchemy', 'alembic', 'psycopg', 'geoalchemy2', 'numpy', 'sklearn', 'PIL']:
    try:
        importlib.import_module(name)
    except Exception:
        sys.exit(f'Python dependency unavailable/incompatible: {name}. Check backend/.venv; no configuration values are printed.')
try:
    from app.rainfall_outlook import RainfallModel
    RainfallModel()  # Loads/checks the existing artifact; never trains.
except Exception:
    sys.exit('Experimental rainfall model artifact unavailable/invalid. Check the original saved model; no training or replacement was attempted.')
try:
    from sqlalchemy.engine import make_url
    from app.shelter_security import SecurityConfig
    ports = [int(os.environ[k]) for k in ['FLOODPULSE_BACKEND_PORT', 'FLOODPULSE_FRONTEND_PORT']]
    assert all(1024 <= p <= 65535 for p in ports) and ports[0] != ports[1]
    urls = [make_url(os.environ[k]) for k in ['DATABASE_URL', 'SHELTER_DATABASE_URL']]
    assert all(u.drivername in ['postgresql', 'postgresql+psycopg'] and u.host == '127.0.0.1' and u.port == 55436 and u.database == 'floodpulse_directory' for u in urls)
    assert os.environ['LOCATION_DIRECTORY_BACKEND'] == 'postgres'
    assert os.environ['SHELTER_DIRECTORY_MODE'] in ['live', 'demonstration']
    config = SecurityConfig()
    assert not config.secure and config.origin == f'http://127.0.0.1:{ports[1]}'
except Exception:
    sys.exit('Launcher configuration invalid: check distinct numeric ports, private database targets and matching loopback origin. No configuration values are printed.')
from launcher_processes import ensure_ports_available, LaunchError
try:
    ensure_ports_available(dict(zip(('backend', 'frontend'), ports)))
except LaunchError as error:
    sys.exit(str(error))  # Only validated port numbers and allowlisted process diagnostics.
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
  [[ "${1:-}" != --check ]] || fail 'Database is stopped; ./floodpulse.sh can start the existing container.'
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
    from app.report_schema import REPORT_TABLES
    from app.subscription_schema import SUBSCRIPTION_TABLES
    from app.report_position_schema import POSITION_TABLES
    from app.mvp_database import check_app_connection
    for key, tables in [('DATABASE_URL', list(metadata.tables.values())), ('SHELTER_DATABASE_URL', [*SHELTER_TABLES, *NOTIFICATION_TABLES, *REPORT_TABLES, *SUBSCRIPTION_TABLES, *POSITION_TABLES])]:
        engine = database_engine(os.environ[key]); engines.append(engine)
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            connection.execute(text('SELECT postgis_lib_version()')).scalar_one()
            inspector = inspect(connection)
            for table in tables:
                assert {c.name for c in table.columns} <= {c['name'] for c in inspector.get_columns(table.name)}
                connection.execute(table.select().limit(0))
            assert inspector.has_table('alembic_version')
            if key == 'SHELTER_DATABASE_URL':
                check_app_connection(connection)
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
export FLOODPULSE_API_TARGET="http://127.0.0.1:$FLOODPULSE_BACKEND_PORT"
# Replace Bash with the supervisor; keep fd 9's exclusive lock until all owned
# descendants and sockets are gone. Child Popen calls close inherited lock fds.
exec "$VENV/bin/python" -B "$ROOT/scripts/launcher_processes.py" run "$ROOT"
