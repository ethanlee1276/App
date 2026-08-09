#!/bin/bash
# Install (or remove) the nightly job on this Mac.
#
#   bash tools/install-nightly.sh            # install, runs 06:00 local
#   bash tools/install-nightly.sh --at 04:30 # a different time
#   bash tools/install-nightly.sh --remove
#   bash tools/install-nightly.sh --now      # run it once, right now
#
# Uses launchd rather than cron. On macOS cron still works but is
# deprecated, and — the part that actually matters here — launchd will run
# a StartCalendarInterval job when the machine WAKES if it was asleep at
# the scheduled time. A laptop that is shut at 6am would simply skip a
# cron job, and skipped ingest is the failure this is meant to prevent.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.qellysbook.nightly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR=6
MINUTE=0
# The pre-kickoff pass runs as its OWN agent, with its own label, so the
# two can be installed, moved and removed independently. It refreshes
# odds and rebuilds the boards; it does not settle, because there is
# nothing to settle at 7am that the 6am pass did not already grade.
#
# Ethan, 2026-08-09: "make sure we make the odds pull around 7am est for
# nfl since there will be some games starting at 9am est." A 6am build
# prices a 9:30am London kickoff on lines three and a half hours old.
PRE=""
PRE_HOUR=7
PRE_MINUTE=0
# Which of the three runners this agent drives — nightly, the
# pre-kickoff odds pull, or the lineup watch. Set by the mode flags.
SCRIPT="nightly"
# Echoed back into the printed commands so they act on the agent
# just installed. `--remove` alone removes the NIGHTLY one —
# the label comes from the flags preceding it — so someone who
# followed the printed line would delete the wrong agent and
# leave the one they meant to remove running.
MODE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --remove)
      launchctl unload "$PLIST" 2>/dev/null
      rm -f "$PLIST"
      echo "Removed $LABEL."
      exit 0
      ;;
    --now)
      # $SCRIPT, not nightly.sh. Printed straight after installing an
      # agent, so hardcoding it meant "run it once now" ran the WRONG
      # runner — the nightly, at midday, instead of the lineup watch.
      exec bash "$REPO/tools/${SCRIPT}.sh"
      ;;
    --at)
      HOUR="${2%%:*}"; MINUTE="${2##*:}"
      HOUR=$((10#$HOUR)); MINUTE=$((10#$MINUTE))
      shift 2
      ;;
    --pre-kickoff)
      PRE=1
      SCRIPT="prekick"; MODE="--pre-kickoff "
      LABEL="com.qellysbook.prekick"
      PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
      # An explicit --at after --pre-kickoff still wins; these are the
      # defaults for the pre-kickoff pass only.
      HOUR=$PRE_HOUR; MINUTE=$PRE_MINUTE
      shift
      ;;
    --lineups)
      # Must start BEFORE the cards post. A boundary's width is the gap
      # since the previous look at that game, so a watch that starts late
      # finds them already up with nothing to measure against — the first
      # real run caught 11 and could use 1.
      SCRIPT="lineups"; MODE="--lineups "
      LABEL="com.qellysbook.lineups"
      PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
      HOUR=11; MINUTE=0
      shift
      ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
done

if [ "$(uname)" != "Darwin" ]; then
  echo "This installs a launchd agent and only works on macOS."
  echo "On Linux, run tools/nightly.sh from cron instead."
  exit 1
fi

chmod +x "$REPO/tools/${SCRIPT}.sh"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO/tools/${SCRIPT}.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <!-- false on purpose: installing this should not kick off a full ingest
       and rebuild the moment you run the installer. Use --now for that. -->
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$REPO/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>$REPO/logs/launchd.err</string>
</dict>
</plist>
PLISTEOF

mkdir -p "$REPO/logs"
launchctl unload "$PLIST" 2>/dev/null
launchctl load -w "$PLIST" || { echo "launchctl load failed"; exit 1; }

printf 'Installed %s — runs %02d:%02d local time.\n' "$LABEL" "$HOUR" "$MINUTE"
echo
echo "  check it is registered:  launchctl list | grep qellysbook"
echo "  run it once now:         bash tools/install-nightly.sh $MODE--now"
echo "  read its log:            tail -40 logs/${SCRIPT}-\$(date +%F).log"
echo "  remove it:               bash tools/install-nightly.sh $MODE--remove"
echo
echo "Local time, not UTC — unlike the GitHub workflows, which are UTC."
echo "If the Mac is asleep at that hour, launchd runs the job on wake."
