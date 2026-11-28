#!/usr/bin/env bash
# The pre-kickoff pass: refresh odds and rebuild the boards, nothing else.
#
# Ethan, 2026-08-09: "make sure we make the odds pull around 7am est for
# nfl since there will be some games starting at 9am est."
#
# The 6am nightly settles last night and prices today. For a 1pm kickoff
# that is fine. For a 9:30am London game it prices on lines three and a
# half hours stale, through the window where a Saturday-night number
# becomes a Sunday-morning one.
#
# WHAT IT DELIBERATELY DOES NOT DO. It does not settle. Nothing has
# finished between 6am and 7am that the 6am pass did not already grade,
# and re-running a settle costs API calls and risks grading a game that
# is still being corrected. `--nightly --odds-only` is the whole job.
#
# It is a SECOND launchd agent rather than a change to the first, because
# they answer to different clocks. The nightly wants to be early enough
# that the site is fresh when you wake up; this one wants to be as late
# as possible while still leaving time to act.
#
#   bash tools/install-nightly.sh --pre-kickoff             # 07:00 local
#   bash tools/install-nightly.sh --pre-kickoff --at 07:30
#   bash tools/install-nightly.sh --pre-kickoff --remove
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
mkdir -p logs
LOG="$REPO/logs/prekick-$(date +%Y-%m-%d).log"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -x "$c" ] && PY="$c" && break
  done
fi
if [ -z "$PY" ]; then
  echo "$(date -Iseconds)  FATAL: no python3 on PATH" >> "$LOG"
  exit 1
fi

# Its own lock, separate from the nightly's. Sharing one would mean a
# 6am run that overran blocked the 7am pull, which is the pull that
# actually has a deadline.
LOCK="$REPO/.prekick.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date -Iseconds)  a pre-kickoff run is still going; skipping" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "================================================================"
  echo "$(date -Iseconds)  pre-kickoff start   python: $PY"
} >> "$LOG"

# --sport nfl, not every board. The reason this pass exists is a 9:30am
# kickoff priced on 6am lines; at 7am the MLB board is twelve hours out
# and was refreshed an hour ago. The odds API bills per event per market,
# so pulling all six sports here costs roughly six times what the one
# sport with a game coming is worth.
#
# Add sports as their seasons start: --sport nfl,cfb once college is
# playing Saturday mornings.
"$PY" launch.py --nightly --odds-only --sport nfl >> "$LOG" 2>&1
RC=$?
echo "$(date -Iseconds)  prekick exit $RC" >> "$LOG"

# Notify only on failure. A ping that says "odds refreshed" every morning
# is a ping you learn to swipe away, and then you swipe away the one
# saying the board you are about to bet is running on last night's lines.
if [ "$RC" -ne 0 ] && command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "pre-kickoff odds pull failed — see logs/" with title "Qellys Book"' >/dev/null 2>&1
fi
exit "$RC"
