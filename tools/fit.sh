#!/usr/bin/env bash
# The four jobs the NFL board is waiting on, as one command you can run
# from a phone.
#
#   ./tools/fit.sh            start them (returns immediately)
#   ./tools/fit.sh --status   how far it has got
#   ./tools/fit.sh --no-restart
#
# WHY THIS EXISTS AS A SCRIPT. Ethan, 2026-08-25: "Am I able to do all of
# that on my phone on the Droplet web console?" Yes — but two things
# about that console make four hand-typed commands the wrong shape:
#
#   * closing the browser tab hangs up the shell, and every process it
#     started dies with it. A calibration pass over 382k rows on one
#     vCPU is minutes, not seconds, so a dropped tab means starting
#     again — and not knowing it stopped;
#   * typing a long command on a phone keyboard, into a console that
#     handles paste badly, is where typos come from.
#
# So this detaches itself with setsid (the shell can hang up; these
# cannot hear it), logs everything with timestamps, and is short to type.
#
# THE RESTART AT THE END IS THE PART THAT IS EASIEST TO FORGET AND MOST
# IMPORTANT. Every fitted store is read ONCE per process and cached for
# its lifetime — engine/calibrate.correction_for holds `_cache` until the
# process ends. So a fit that writes a perfect file changes nothing at
# all on a server that is already running: the boards keep rebuilding
# with the corrections the service loaded at boot. Restarting is what
# makes the work count, and doing it here means it cannot be missed.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
LOG=/var/log/qellys-fit.log
LOCK=/tmp/qellys-fit.pid

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
say()   { printf '\n[%s] ==> %s\n' "$(stamp)" "$*"; }

# --- --status ---------------------------------------------------------
if [[ "${1:-}" == "--status" ]]; then
  if [[ -f "$LOCK" ]] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Still running (pid $(cat "$LOCK")). Last 20 lines:"
  else
    echo "Not running. Last 20 lines:"
  fi
  echo
  tail -n 20 "$LOG" 2>/dev/null || echo "  (no log yet — has it been started?)"
  exit 0
fi

# --- detach -----------------------------------------------------------
# The marker is an argument rather than an environment variable so that
# `ps` shows plainly which copy is the worker.
if [[ "${1:-}" != "--run" ]]; then
  if [[ -f "$LOCK" ]] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Already running (pid $(cat "$LOCK")). Watch it with:"
    echo "  ./tools/fit.sh --status"
    exit 0
  fi
  setsid nohup "$0" --run "$@" >> "$LOG" 2>&1 < /dev/null &
  sleep 1
  echo "Started. It keeps running if you close this console."
  echo
  echo "  ./tools/fit.sh --status      how far it has got"
  echo
  echo "Roughly 10-30 minutes on this box. The site stays up throughout;"
  echo "it restarts once at the end so the new numbers take effect."
  exit 0
fi
shift                                   # drop --run

echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

RESTART=1
[[ "${1:-}" == "--no-restart" ]] && RESTART=0

say "starting — $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
FAILED=()

# `nice`, because this box has ONE vCPU and the site is serving on it.
# A fit that makes every page slow for twenty minutes is a fit that
# should have waited; at nice 10 the server wins every contest for the
# core and the fit uses what is left.
run() {
  local label="$1"; shift
  say "$label"
  if nice -n 10 "$@"; then
    say "$label — done"
  else
    say "$label — FAILED (rc=$?)"
    FAILED+=("$label")
  fi
}

# The CFB ingest first: it is the one that talks to the network, so if
# the key or the API is going to be a problem it is better to find out
# in the first minute than the twentieth. The CFBD key is read from
# /etc/qellys/env automatically (engine/secrets.py) — nothing to export,
# and nothing to type a key into.
run "college football, 2025 season" \
    python3 ingest.py cfb --seasons 2025

# The three NFL fits. Each refuses to apply itself until it has enough
# settled history, so a "not enough data" answer is the system working
# rather than failing — it will say so and move on.
run "NFL probability calibration" \
    python3 calibrate.py --from-db data/history.db --sport nfl
run "NFL player memory" \
    python3 playerfit.py --sport nfl
run "NFL recency dial" \
    python3 formfit.py --sport nfl

if (( RESTART )); then
  # See the header: without this the service keeps the corrections it
  # loaded at boot and every fit above is inert.
  say "restarting the service so the new numbers are loaded"
  if sudo systemctl restart qellys; then
    say "restarted"
  else
    say "RESTART FAILED — the fits are on disk but not in use"
    FAILED+=("restart")
  fi
fi

if (( ${#FAILED[@]} )); then
  say "finished with ${#FAILED[@]} problem(s): ${FAILED[*]}"
else
  say "all done"
fi
