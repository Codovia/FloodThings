#!/usr/bin/env bash
# FloodPulse — the one script to run the app on this laptop.
#
#   ./floodpulse.sh              start the app (if it is already running, it is restarted so new code loads)
#   ./floodpulse.sh --telegram   also connect the Telegram bot to this laptop (takes it away from the server)
#   ./floodpulse.sh --stop       stop the running app
#   ./floodpulse.sh --check      check that everything is ready; starts nothing
#   ./floodpulse.sh --help
#
# It wraps the existing launchers (start.sh, start-full.sh), which keep all their checks: database,
# ports, dependencies, private configuration. Press Ctrl+C in this terminal to stop the app.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$ROOT"

say() { printf 'FloodPulse: %s\n' "$*"; }
fail() { printf 'FloodPulse: %s\n' "$*" >&2; exit 1; }
usage() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; }

mode=start telegram=() yes=
for arg in "$@"; do
  case "$arg" in
    --telegram) telegram=(--telegram) ;;
    --stop) mode=stop ;;
    --check) mode=check ;;
    --yes) yes=1 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown option '$arg'. Use --help." ;;
  esac
done

PY="$ROOT/backend/.venv/bin/python"
[[ -x "$PY" ]] || fail 'backend/.venv is missing; follow the README setup first.'

# 1. Telegram settings always come from the private .env file. VS Code can copy an outdated version of
#    them into every new terminal, and terminal values would otherwise take precedence.
unset TELEGRAM_BOT_USERNAME TELEGRAM_BOT_TOKEN TELEGRAM_DESTINATIONS TELEGRAM_WEBHOOK_SECRET

# 2. The launchers keep private files under data/ and refuse folders that others can write to.
for dir in data data/tmp; do
  if [[ -d "$dir" && -O "$dir" ]]; then chmod go-w "$dir"; fi
done

# 3. Stop a running copy first, so the latest code is loaded. Only this folder's verified FloodPulse
#    launcher is signalled (as Ctrl+C would); it then stops its own backend and web server.
if [[ "$mode" != check ]]; then
  "$PY" -B scripts/launcher_processes.py stop "$ROOT" || fail 'Could not stop the running app safely; stop it with Ctrl+C in its terminal.'
fi
[[ "$mode" != stop ]] || exit 0

# 4. The Telegram bot can deliver to one place only.
if (( ${#telegram[@]} )) && [[ "$mode" == start && -z "$yes" ]]; then
  say 'The bot can deliver to only one place. --telegram points it at THIS laptop, so the server stops'
  say 'receiving /start and /stop until you point it back (see docs/AZURE_HOSTING.md, step 7).'
  read -r -p 'Continue? [y/N] ' answer
  [[ "$answer" == [yY]* ]] || fail 'Cancelled; nothing was started.'
fi

# 5. Start (or only check). start-full.sh runs start.sh's checks and services, plus the tunnel with --telegram.
args=("${telegram[@]}")
[[ "$mode" != check ]] || args+=(--check)
say "$([[ "$mode" == check ]] && echo 'Checking readiness (nothing will be started)…' || echo 'Starting. Open http://127.0.0.1:14180 when it says it is ready; Ctrl+C stops it.')"
exec "$ROOT/start-full.sh" "${args[@]}"
