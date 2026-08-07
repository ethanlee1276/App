#!/bin/bash
# The nightly run, for the machine that actually has the data.
#
# GitHub Actions already runs the test suite and doctor.py --code-only, but
# it cannot see ledger.db, history.db or web/data/ — they are gitignored,
# and statsapi.mlb.com is not reachable from a CI runner. So the checks
# that matter about the MODEL can only run here.
#
# Two steps, and the order is deliberate:
#   1. launch.py   — ingest last night's finals, settle open bets, rebuild
#                    the site, and run doctor.py against real data.
#   2. watch.py    — read the numbers that decide things and stay silent
#                    unless one crossed a bar fixed in advance.
#
# Nothing here changes a model parameter. See watch.py's docstring for why
# that is a design decision and not an omission.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

LOGDIR="$REPO/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/nightly-$(date +%Y-%m-%d).log"

# launchd hands a job a nearly empty PATH, so a Homebrew or pyenv python3
# is invisible unless it is put back. Without this the job dies with
# "command not found" at 6am and the first anyone knows is a week of
# missing ingest.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "$(date -Iseconds)  FATAL: no python3 on PATH" >> "$LOG"
  exit 127
fi

# A slow night must not overlap the next one. flock is not on macOS, so
# this is the portable version: a directory is created atomically or not
# at all.
LOCK="$REPO/.nightly.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date -Iseconds)  another nightly run is still going; skipping" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "================================================================"
  echo "$(date -Iseconds)  nightly start   python: $PY"
  echo "================================================================"
} >> "$LOG"

"$PY" launch.py >> "$LOG" 2>&1
LAUNCH_RC=$?
echo "$(date -Iseconds)  launch.py exit $LAUNCH_RC" >> "$LOG"

# watch.py runs even if launch.py failed. A failed ingest is exactly when
# the readings are most worth having, and a tripwire that only runs on
# healthy nights is not a tripwire.
WATCH_OUT="$("$PY" watch.py 2>&1)"
WATCH_RC=$?
if [ -n "$WATCH_OUT" ]; then
  echo "$WATCH_OUT" >> "$LOG"
fi
echo "$(date -Iseconds)  watch.py exit $WATCH_RC" >> "$LOG"

# Surface it. Silence is the normal outcome and gets no notification —
# a nightly ping that says "all fine" every day trains you to swipe it
# away, and then you swipe away the one that mattered.
notify() {
  osascript -e "display notification \"$1\" with title \"Qellys Book\"" \
    >/dev/null 2>&1 || true
}
if [ "$LAUNCH_RC" -ne 0 ]; then
  notify "launch.py failed — see logs/$(basename "$LOG")"
elif [ -n "$WATCH_OUT" ]; then
  notify "A watch crossed its bar — see logs/$(basename "$LOG")"
fi

# Keep a fortnight. These are plain text and tiny, but unbounded log
# growth in a repo directory is how a disk fills up silently.
find "$LOGDIR" -name 'nightly-*.log' -mtime +14 -delete 2>/dev/null

exit 0
