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

REMOTE="${1:-}"
if [[ -z "$REMOTE" ]]; then
  echo "usage: ./deploy/seed.sh user@host" >&2
  exit 2
fi
cd "$(dirname "$0")/.."

# ledger.db is FIRST and it is the one that matters most: it is the public
# record, it cannot be rebuilt from anywhere, and the server has already
# started writing its own. Sending it means overwriting that.
echo "==> what will be sent"
for f in data/ledger.db data/history.db data/ufc_dossiers.json; do
  [[ -f "$f" ]] && printf "    %-28s %s\n" "$f" "$(du -h "$f" | cut -f1)"
done
[[ -d data/models ]] && printf "    %-28s %s\n" "data/models/" "$(du -sh data/models | cut -f1)"

cat <<'WARN'

    THE SERVER'S OWN ledger.db WILL BE REPLACED. It has been journaling
    since it came up, so anything it recorded that this machine has not
    also recorded is lost. Settle locally first (python3 launch.py
    --settle all), and take the server's backup before you answer yes —
    deploy/backup.sh runs there nightly and /var/backups/qellys holds it.

WARN
read -r -p "    type SEED to continue: " reply
[[ "$reply" == "SEED" ]] || { echo "aborted"; exit 1; }

echo "==> stopping the app so nothing writes mid-copy"
ssh "$REMOTE" "systemctl stop qellys"

echo "==> sending"
# --partial so a dropped connection on the 65MB history.db resumes rather
# than starting over on a phone tether.
rsync -avz --partial --progress \
  data/ledger.db data/history.db \
  "$REMOTE:/srv/qellys/data/"
[[ -f data/ufc_dossiers.json ]] && rsync -az data/ufc_dossiers.json "$REMOTE:/srv/qellys/data/"
[[ -d data/models ]] && rsync -avz data/models/ "$REMOTE:/srv/qellys/data/models/"

echo "==> ownership: the app user writes these, and root cannot hand over what it does not own"
ssh "$REMOTE" "chown -R qellys:qellys /srv/qellys/data && systemctl start qellys"

echo "==> confirming the box agrees"
ssh "$REMOTE" "cd /srv/qellys && sudo -u qellys python3 launch.py --check 2>/dev/null | sed -n '/The learned model/,/^$/p'"
echo
echo "Done. The Record should now show the real history at https://qellysbook.com/#record"
