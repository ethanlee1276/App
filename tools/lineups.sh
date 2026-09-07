#!/usr/bin/env bash
# Watch for MLB lineup cards from before they post until the slate is set.
#
# WHY IT HAS TO START EARLY, which is the whole point of running it on a
# schedule rather than by hand. `engine/mlb/lineuptimes` records the first
# moment each card is seen up, and the width of the window the real
# release sits in is the gap since the PREVIOUS look at that game. A watch
# that starts at 3pm finds ten cards already up, with no previous look, so
# their windows are unbounded and `is_usable` refuses them.
#
# Ethan's first run measured exactly that: 15 games, 11 caught, 1 usable.
# The one usable boundary had a 909-second window — the polling interval.
# The other ten were recorded and are worthless as boundaries.
#
# MLB cards land roughly 3-4 hours before first pitch, and the earliest
# games start around 1pm ET, so 11:00 local is before the first of them.
#
#   bash tools/install-nightly.sh --lineups            # 11:00 local
#   bash tools/install-nightly.sh --lineups --at 10:30
#   bash tools/install-nightly.sh --lineups --remove
#
# It exits on its own once every card is out (`settled()`), so it costs
# nothing for the rest of the day.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
mkdir -p logs
LOG="$REPO/logs/lineups-$(date +%Y-%m-%d).log"

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

LOCK="$REPO/.lineups.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date -Iseconds)  a lineup watch is already running; skipping" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

echo "$(date -Iseconds)  lineup watch start" >> "$LOG"

# --every 5, not the default 10. Every poll now skips the games whose
# cards are already up, so a tighter interval costs almost nothing once
# the slate starts filling — and the interval IS the precision of every
# boundary recorded, which is the number this whole exercise turns on.
"$PY" lineupwatch.py --watch --every 5 >> "$LOG" 2>&1
RC=$?
echo "$(date -Iseconds)  lineup watch exit $RC" >> "$LOG"

# Report the harvest, so a day that recorded nothing usable is visible in
# the log rather than only in a report nobody runs.
"$PY" -c "
from engine.mlb import lineuptimes
c = lineuptimes.coverage()
print('boundaries: %d game(s), %d caught, %d usable (median window %ss)'
      % (c['games'], c['caught'], c['usable'], c['median_gap_s']))
" >> "$LOG" 2>&1

exit "$RC"
