#!/usr/bin/env bash
# Seed a new server with the things git does not carry.
#
#   ./deploy/seed.sh root@143.198.169.53        # from the Mac, to the box
#
# WHY THIS EXISTS. `git clone` gives a server the code and nothing else.
# Every database and every fitted model is gitignored — correctly, they are
# large and derived — so a new box starts with:
#
#   * no history.db, so backtests, comps, team ratings and player logs are
#     all empty and nothing can be refitted;
#   * no data/models/*, so player memory, the recency dial, calibration and
#     the blind-spot miner all return their neutral defaults;
#   * a fresh ledger.db, so the public Record shows none of the history the
#     subscription is sold on.
#
# None of that looks broken. The picks still appear — they are simply the
# uncorrected ones, and the Record is simply empty. That is the whole
# reason this script is written down rather than remembered: the failure
# is invisible from the outside.
#
# Found 2026-08-16, after the first live deploy, when the site had been up
# for a day with a blank brain.
set -euo pipefail

# ONE-TIME vs ROUTINE, and the difference matters more than it reads.
#
# The FULL seed sends ledger.db. That is correct exactly once: when a new
# box has never journaled anything and the Mac holds the entire record.
# After that the SERVER owns the journal — it is the thing running
# launch.py against live slates, so it is the only machine whose ledger is
# the truth. Sending the Mac's again would erase every pick the live site
# has recorded since, which is the one loss no backup schedule makes
# painless because it is a deliberate overwrite, not a fault.
#
# So the routine form is --models-only: refits happen on the Mac, because
# they need the 65MB history.db, and only the fitted output travels.
MODE="full"
REMOTE=""
for arg in "$@"; do
  case "$arg" in
    --models-only) MODE="models" ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *)  REMOTE="$arg" ;;
  esac
done
if [[ -z "$REMOTE" ]]; then
  echo "usage: ./deploy/seed.sh [--models-only] user@host" >&2
  echo "  (no flag)      first seed of a new box: ledger, history, models" >&2
  echo "  --models-only  every time after that: fitted models only" >&2
  exit 2
fi
cd "$(dirname "$0")/.."

# RUN THIS FROM THE MACHINE THAT HAS THE DATA, NOT THE ONE RECEIVING IT.
#
# Both prompts scroll past in the same window and the two hosts are easy to
# confuse — it has already sent `ufw`, `journalctl` and `cd ~/App` to the
# wrong box this week. Run here, on the server, it would ssh to itself,
# fail on publickey, and print a permissions error that reads like a
# broken deploy key rather than "wrong machine".
#
# /srv/qellys only exists on the server, so its presence is the tell.
if [[ -d /srv/qellys && "$(pwd -P)" == "/srv/qellys" ]]; then
  echo "This is the SERVER — seed.sh runs from the Mac, which is where the" >&2
  echo "data lives. Type 'exit' to get back, then:" >&2
  echo "    cd ~/App && ./deploy/seed.sh ${MODE:+--models-only }$REMOTE" >&2
  exit 2
fi

# ledger.db is FIRST and it is the one that matters most: it is the public
# record, it cannot be rebuilt from anywhere, and the server has already
# started writing its own. Sending it means overwriting that.
echo "==> what will be sent"
if [[ "$MODE" == "models" ]]; then
  printf "    %-28s %s\n" "data/models/" "$(du -sh data/models | cut -f1)"
  echo "    (models only — the server's ledger.db and history.db are untouched)"
else
  for f in data/ledger.db data/history.db data/ufc_dossiers.json; do
    [[ -f "$f" ]] && printf "    %-28s %s\n" "$f" "$(du -h "$f" | cut -f1)"
  done
  [[ -d data/models ]] && printf "    %-28s %s\n" "data/models/" "$(du -sh data/models | cut -f1)"
fi

if [[ "$MODE" == "models" ]]; then
  echo "==> models only: no confirmation needed, nothing irreplaceable moves"
else
cat <<'WARN'

    THE SERVER'S OWN ledger.db WILL BE REPLACED. It has been journaling
    since it came up, so anything it recorded that this machine has not
    also recorded is lost. Settle locally first (python3 launch.py
    --settle all), and take the server's backup before you answer yes —
    deploy/backup.sh runs there nightly and /var/backups/qellys holds it.

WARN
read -r -p "    type SEED to continue: " reply
[[ "$reply" == "SEED" ]] || { echo "aborted"; exit 1; }
fi

# THE APP MUST COME BACK UP EVEN IF THIS SCRIPT DIES.
#
# `set -euo pipefail` plus a stop/start pair is a trap: anything that fails
# in between — a dropped rsync, a closed laptop lid, a Ctrl-C, a terminal
# window shut while it was still going — exits the script with the service
# STOPPED. And it does not look like an outage from outside, because Caddy
# keeps serving the static files off disk. The site stays up and simply
# stops being true, which is the failure mode this whole deployment has
# been fighting all week.
#
# Happened for real, 2026-08-16: a terminal was closed mid-seed and the
# droplet served a frozen board for twelve minutes before anyone noticed.
_restart_guard() {
  local code=$?
  if [[ "${QB_APP_STOPPED:-0}" == "1" ]]; then
    echo ""
    echo "==> seed did not finish (exit $code) — restarting the app anyway"
    ssh "$REMOTE" "systemctl start qellys" \
      && echo "    app restarted. Nothing was seeded; run this again when ready." \
      || echo "    COULD NOT RESTART. Run: ssh $REMOTE 'systemctl start qellys'"
  fi
  exit "$code"
}
trap _restart_guard EXIT INT TERM HUP

echo "==> stopping the app so nothing writes mid-copy"
ssh "$REMOTE" "systemctl stop qellys"
QB_APP_STOPPED=1

echo "==> sending"
# --partial so a dropped connection on the 65MB history.db resumes rather
# than starting over on a phone tether.
if [[ "$MODE" == "full" ]]; then
  # --partial so a dropped connection on the 65MB history.db resumes
  # rather than starting over on a phone tether.
  rsync -avz --partial --progress \
    data/ledger.db data/history.db \
    "$REMOTE:/srv/qellys/data/"
  [[ -f data/ufc_dossiers.json ]] && rsync -az data/ufc_dossiers.json "$REMOTE:/srv/qellys/data/"
fi
[[ -d data/models ]] && rsync -avz data/models/ "$REMOTE:/srv/qellys/data/models/"

echo "==> ownership: the app user writes these, and root cannot hand over what it does not own"
ssh "$REMOTE" "chown -R qellys:qellys /srv/qellys/data && systemctl start qellys"
QB_APP_STOPPED=0        # started cleanly; the guard has nothing left to do

echo "==> confirming the box agrees"
ssh "$REMOTE" "cd /srv/qellys && sudo -u qellys python3 launch.py --check 2>/dev/null | sed -n '/The learned model/,/^$/p'"
echo
echo "Done. The Record should now show the real history at https://qellysbook.com/#record"
