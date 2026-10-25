#!/usr/bin/env bash
# Keep the server on the latest code pushed to GitHub, for the branch this copy follows.
#
#   ./auto-update.sh --on       check every 5 minutes (adds one line to this user's crontab)
#   ./auto-update.sh --off      stop the automatic checks
#   ./auto-update.sh --status   show whether it is on and the latest log lines
#   ./auto-update.sh            check once now (what the 5-minute job runs)
#
# On a new commit: back up the database (backups/pre-update-*.dump), update the code (fast-forward
# only), run ./setup.sh and wait until the app reports ready. Every step goes to deploy/auto-update.log.
# It never rolls back by itself: a failed update is logged and not retried until a newer commit arrives.
set -euo pipefail
cd "$(dirname "$0")"
# Git writes the code with this umask and Docker copies the modes into the image, where the app runs as another
# user: the code must stay readable (umask 077 here once made main.py unreadable and took the site down).
umask 022
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin" GIT_TERMINAL_PROMPT=0
HERE=$(pwd -P)
LOG=auto-update.log
FAILED=.auto-update.failed
READY_WAIT=${FLOODPULSE_READY_WAIT:-120}

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" >> "$LOG"; }
other_jobs() { crontab -l 2>/dev/null | grep -vF "$HERE/auto-update.sh" || true; }
is_on() { crontab -l 2>/dev/null | grep -qF "$HERE/auto-update.sh"; }

update() {
  # One run at a time; a run that finds another still working leaves it alone.
  exec 9>> .auto-update.lock
  flock -n 9 || return 0
  if [[ -f "$LOG" ]] && (( $(wc -l < "$LOG") > 5000 )); then
    tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  touch "$LOG" && chmod 600 "$LOG" .auto-update.lock   # the script's own files stay private

  local branch old new
  branch=$(git symbolic-ref --quiet --short HEAD) || { log 'FAILED: the server copy is not on a branch; nothing changed.'; exit 1; }
  if ! git fetch --quiet origin "$branch" 2>> "$LOG"; then
    log "FAILED: could not reach GitHub for $branch; trying again in 5 minutes."
    exit 1
  fi
  old=$(git rev-parse HEAD)
  new=$(git rev-parse FETCH_HEAD)
  [[ "$old" != "$new" ]] || return 0
  [[ "$(cat "$FAILED" 2>/dev/null)" != "$new" ]] || return 0   # already failed; wait for a newer commit

  fail() { log "FAILED: $1"; printf '%s\n' "$new" > "$FAILED"; exit 1; }
  git merge-base --is-ancestor "$old" "$new" ||
    fail "$branch on GitHub does not contain the server's commit ${old:0:7} (history rewritten, or a commit made on the server); update by hand."
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] ||
    fail 'files tracked by Git were changed on the server; nothing updated. See: git status'

  log "Updating $branch ${old:0:7} -> ${new:0:7}: $(git log -1 --format=%s "$new")"
  ./backup.sh pre-update >> "$LOG" 2>&1 9>&- || fail 'database backup failed; code not updated.'
  git merge --ff-only --quiet "$new" >> "$LOG" 2>&1 || fail 'code update failed; see the lines above.'
  ./setup.sh >> "$LOG" 2>&1 9>&- ||
    fail "setup.sh failed at ${new:0:7}; the code is updated but the app may still run ${old:0:7}. See the lines above."

  local waited
  for (( waited = 0; waited < READY_WAIT; waited += 5 )); do
    if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=5)" >/dev/null 2>&1; then
      rm -f "$FAILED"
      log "OK: now running ${new:0:7}."
      return 0
    fi
    sleep 5
  done
  fail "the app did not report ready within ${READY_WAIT}s after updating to ${new:0:7}. Check: docker compose ps; docker compose logs app"
}

case "${1:-}" in
  --on)
    jobs=$(other_jobs)   # read the whole crontab before replacing it
    printf '%s\n' ${jobs:+"$jobs"} "*/5 * * * * $HERE/auto-update.sh" | crontab -
    echo "Automatic updates on: GitHub is checked every 5 minutes for branch $(git symbolic-ref --quiet --short HEAD || echo '?')."
    echo 'Log: deploy/auto-update.log' ;;
  --off)
    jobs=$(other_jobs)
    printf '%s' "${jobs:+$jobs$'\n'}" | crontab -
    echo 'Automatic updates off.' ;;
  --status)
    if is_on; then echo 'Automatic updates: on'; else echo 'Automatic updates: off'; fi
    echo "Branch: $(git symbolic-ref --quiet --short HEAD || echo 'none') at $(git rev-parse --short HEAD)"
    if [[ -f "$LOG" ]]; then grep -E '^[0-9]{4}-.* (Updating|OK|FAILED)' "$LOG" | tail -n 10; fi ;;
  '') update ;;
  *) sed -n '4,7p' "$HERE/auto-update.sh" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
