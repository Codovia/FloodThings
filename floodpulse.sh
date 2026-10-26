#!/usr/bin/env bash
# FloodPulse — the one script to run the app on this laptop.
#
#   ./floodpulse.sh              start the app (if it is already running, it is restarted so new code loads)
#   ./floodpulse.sh --telegram   also connect the Telegram bot to this laptop (takes it away from the server)
#   ./floodpulse.sh --lan        also let phones and laptops on the same Wi-Fi open the website (viewing only)
#   ./floodpulse.sh --stop       stop the running app
#   ./floodpulse.sh --check      check that everything is ready; starts nothing
#   ./floodpulse.sh --help
#
# It runs the existing launchers (scripts/full_launcher.py, which supervises scripts/app_launcher.sh),
# keeping all their checks: database, ports, dependencies, private configuration. Ctrl+C stops the app.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$ROOT"

say() { printf 'FloodPulse: %s\n' "$*"; }
fail() { printf 'FloodPulse: %s\n' "$*" >&2; exit 1; }
usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }

mode=start telegram=() yes=
unset FLOODPULSE_LAN  # Only the --lan option opens the website to the network.
for arg in "$@"; do
  case "$arg" in
    --telegram) telegram=(--telegram) ;;
    --lan) export FLOODPULSE_LAN=1 ;;
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
  # The supervisor shuts down after the app launcher; wait until both have released their locks.
  for lock in data/tmp/full_launcher/lock data/tmp/launcher/lock; do
    if [[ -e "$lock" ]]; then
      flock -w 60 "$lock" true || fail 'The previous run is still shutting down after 60 seconds; try again shortly.'
    fi
  done
fi
[[ "$mode" != stop ]] || exit 0

# 4. The Telegram bot can deliver to one place only.
if (( ${#telegram[@]} )) && [[ "$mode" == start && -z "$yes" ]]; then
  say 'The bot can deliver to only one place. --telegram points it at THIS laptop, so the server stops'
  say 'receiving /start and /stop until you point it back (see docs/AZURE_HOSTING.md, step 7).'
  read -r -p 'Continue? [y/N] ' answer
  [[ "$answer" == [yY]* ]] || fail 'Cancelled; nothing was started.'
fi

# 5. Start (or only check): the supervisor runs the app launcher's checks and services, plus the tunnel with --telegram.
args=("${telegram[@]}")
[[ "$mode" != check ]] || args+=(--check)
say "$([[ "$mode" == check ]] && echo 'Checking readiness (nothing will be started)…' || echo "Starting. Open http://127.0.0.1:14180${FLOODPULSE_LAN:+ (or the Same Wi-Fi address it prints)} when it says it is ready; Ctrl+C stops it.")"
exec "$PY" -B "$ROOT/scripts/full_launcher.py" "${args[@]}"
