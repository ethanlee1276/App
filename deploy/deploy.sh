#!/usr/bin/env bash
# Deploy Qellys Book. Run on the server, as the qellys user.
#
#   ./deploy/deploy.sh              # deploy the current branch
#   ./deploy/deploy.sh --no-tests   # only when the suite is already green
#
# THE TEST SUITE IS THE RELEASE GATE, and it does not have to run HERE.
# GitHub Actions runs the whole suite on every push (.github/workflows/
# tests.yml, three Python versions) — so the normal deploy is:
#
#   1. the branch shows a green tick on GitHub (Actions tab), then
#   2. ./deploy/deploy.sh --no-tests          (~a minute)
#
# --no-tests skips ONLY the suite: the database backup, the pull, the
# restart and the prove-it-answers check all still run, and the rollback
# one-liner is printed if anything is off. Running the suite on this box
# takes about an hour (measured 2026-08-18 — 4,600 tests on two vCPUs),
# which made every engine deploy cost Ethan an evening; the tick costs
# nothing. Run the full form only when deploying something that never
# went through GitHub, which should be never.
#
# It refuses the deploy if anything is red. That is the whole point:
# once other people have accounts, "I'm fairly sure that was fine" stops
# being an acceptable standard, and the suite already exists.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SERVICE="${QB_SERVICE:-qellys}"
RUN_TESTS=1
[[ "${1:-}" == "--no-tests" ]] && RUN_TESTS=0

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# Set when this script has already re-executed itself (see step 3). The
# backup and the pull are done by then; repeating them would write a
# second identical backup and pull nothing.
RESUMED="${QB_DEPLOY_RESUMED:-}"

# --- 1. a way back ---------------------------------------------------
# Tagged BEFORE anything changes, so rollback is one command and does not
# depend on remembering what was deployed.
PREV="$(git rev-parse --short HEAD)"
[ -z "$RESUMED" ] && \
  say "current: $PREV  (roll back with: git checkout $PREV && ./deploy/deploy.sh)"

if [ -z "$RESUMED" ]; then
  # --- 2. back up the databases --------------------------------------
  # Before the code changes, not after. A migration that goes wrong is
  # exactly when the pre-migration copy is the only useful thing on the box.
  say "backing up"
  ./deploy/backup.sh

  # --- 3. new code ----------------------------------------------------
  say "pulling"
  BEFORE="$(git rev-parse HEAD)"
  git pull --ff-only
  AFTER="$(git rev-parse HEAD)"

  # THIS SCRIPT JUST OVERWROTE ITSELF, POSSIBLY. Bash does not read a
  # script into memory — it reads lazily, keeping a byte offset into the
  # open file. Rewriting the file underneath it means execution continues
  # at that same offset in the NEW text, which lands wherever the byte
  # count happens to land: usually a different line, sometimes the middle
  # of one.
  #
  # Measured on 2026-08-22. The pull that ADDED the promo-code step
  # inserted 27 lines above the restart; bash resumed past them and went
  # straight to "restarting". The step simply never ran, and nothing said
  # so. A shorter edit could as easily have resumed inside a word and run
  # a fragment as a command.
  #
  # So: if the pull changed this file, start over from the new copy. The
  # env var is how the new process knows the backup and the pull are
  # already done. It also means a step added by a deploy runs on THAT
  # deploy, rather than silently waiting for the next one.
  if [ "$BEFORE" != "$AFTER" ] \
     && ! git diff --quiet "$BEFORE" "$AFTER" -- deploy/deploy.sh; then
    say "deploy.sh changed in that pull — re-running it on the new version"
    export QB_DEPLOY_RESUMED=1
    exec bash "$ROOT/deploy/deploy.sh" "$@"
  fi
fi

# --- 4. the gate ------------------------------------------------------
if [[ "$RUN_TESTS" == "1" ]]; then
  # The runner went parallel on 2026-08-22 and prints a counter while it
  # works — the first cut printed nothing at all until the last file
  # finished, which on this box was eleven silent minutes and read as a
  # hang. No estimate here on purpose: it depends on the box, and a
  # number that is wrong is worse than none. The counter says where it is.
  say "running the suite (this is the gate)"
  if ! python3 run_tests.py; then
    echo
    echo "TESTS FAILED — nothing was restarted, the old code is still serving."
    echo "The pull already happened; to go back:  git checkout $PREV"
    exit 1
  fi
else
  say "SKIPPING TESTS — you asserted they are green elsewhere"
fi

# --- 5. restart -------------------------------------------------------
# THE CADDYFILE IS PART OF THE DEPLOY NOW. It was not, and the manual
# `sudo cp deploy/Caddyfile /etc/caddy/Caddyfile` in its header is the
# kind of step that gets done once and never again — so a routing change
# committed to the repo sat there while the box kept its old copy. That
# is how /sw.js spent every deploy being served off disk instead of
# through the app, which froze the service worker's cache name and let a
# stale bundle outlive every fix that shipped for it.
#
# Only when it differs, and Caddy validates before it reloads: a bad
# Caddyfile that gets installed anyway takes the whole site down, and a
# reload with nothing to reload is noise in the log.
CADDYFILE="/etc/caddy/Caddyfile"
if [ -f deploy/Caddyfile ] && [ -d /etc/caddy ]; then
  if ! sudo cmp -s deploy/Caddyfile "$CADDYFILE"; then
    say "the Caddyfile changed — validating before installing"
    if sudo caddy validate --config deploy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
      sudo cp deploy/Caddyfile "$CADDYFILE"
      sudo systemctl reload caddy && say "caddy reloaded"
    else
      echo
      echo "  THE NEW CADDYFILE DOES NOT VALIDATE. Left the running one in"
      echo "  place — the site keeps working on the old config. See:"
      echo "  caddy validate --config deploy/Caddyfile --adapter caddyfile"
      echo
    fi
  fi
fi

# --- 4b. the discount codes -------------------------------------------
# Ethan, 2026-08-22, on being told to run --stripe-setup by hand: "why
# cant you do it for me since you did the USFARATHANE code for me."
#
# Correct, and the difference was never about permission. A redemption
# code is an environment variable on this box, so golive.sh could just
# set it. A checkout promo is an object inside the Stripe ACCOUNT, and
# the key that creates it lives here in /etc/qellys/env and nowhere
# else. So the fix is not to ask him to run a command — it is to run it
# from the place that already holds the key. This is that place.
#
# --promos-setup, NOT --stripe-setup: this creates coupons only, never a
# Product or a Price. A deploy that silently mints prices is the thing
# the --stripe / --stripe-setup split exists to prevent. A coupon charges
# nobody, cannot be duplicated (Stripe enforces one promotion code per
# name), and one that disagrees with the repo is reported rather than
# rewritten.
#
# Never fatal. A Stripe outage is not a reason to refuse a deploy that
# has nothing to do with billing.
if [ -f /etc/qellys/env ]; then
  say "checking the discount codes at Stripe"
  python3 launch.py --promos-setup || \
    echo "  (could not reach Stripe — the deploy is unaffected; "\
         "run 'python3 launch.py --promos' later to check)"
fi

# --- 5b. the systemd unit, which git tracks and systemd does not read
#
# THE FILE IN THE REPO IS NOT THE FILE THAT RUNS. `deploy/qellys.service`
# is a template; systemd reads /etc/systemd/system/qellys.service, and
# the two only meet when somebody copies one onto the other. Nothing
# checked, so they could drift for as long as nobody looked.
#
# Found 2026-08-31 the way these always are: --auto-update was added to
# the tracked unit, the deploy reported success, the service restarted
# on new code, and the flag was not on — because the running unit had
# never heard of it. A deploy that pulls a change and restarts into
# something else is a deploy that lies.
#
# Announced and diffed rather than done quietly: this writes a system
# file, and a unit that changed under you is worth reading about.
UNIT_SRC="deploy/qellys.service"
UNIT_DST="/etc/systemd/system/${SERVICE}.service"
if [ -f "$UNIT_SRC" ] && ! sudo cmp -s "$UNIT_SRC" "$UNIT_DST"; then
  say "the systemd unit changed — installing it"
  sudo diff "$UNIT_DST" "$UNIT_SRC" | grep -E '^[<>]' | head -20 || true
  sudo cp "$UNIT_SRC" "$UNIT_DST"
  sudo systemctl daemon-reload
  echo "  installed and reloaded — the restart below runs the new unit"
else
  # SAY SO WHEN NOTHING CHANGED, TOO. The first cut printed nothing on a
  # match, and from a phone that is indistinguishable from the step not
  # existing — which is exactly the round trip it caused the day it
  # shipped: the unit had already been installed by hand, this skipped
  # silently, and the deploy output gave no way to tell "already there"
  # from "never ran". One line, with the fact that actually matters on
  # it, read from the file systemd will use rather than asserted.
  echo "  systemd unit matches the repo$(
    grep -q -- '--auto-update' "$UNIT_SRC"       && echo ' (auto-update: ON)' || echo ' (auto-update: off)')"
fi

say "restarting $SERVICE"
sudo systemctl restart "$SERVICE"
sleep 2

# --- 6. prove it is actually up ---------------------------------------
# A restart that returns 0 and a service that serves pages are different
# facts. Ask it a question and require an answer.
#
# THE WINDOW IS WIDE ON PURPOSE. The unit runs launch.py, which does a
# full `refresh_all()` — every sport, every board — BEFORE it binds the
# port. A cold start is therefore tens of seconds, not instant. This
# check used to give up after five tries two seconds apart: about twelve
# seconds, which a healthy deploy loses every single time. It would have
# printed "IT RESTARTED BUT IS NOT ANSWERING" and recommended rolling
# back a deploy that was in the middle of working correctly — the worst
# kind of false alarm, because acting on it undoes a good release.
#
# So: three minutes, and the loop tells the difference between "still
# building" and "dead". A process that has exited is a failure now; one
# that is still running has not finished starting.
# The socket now opens BEFORE the boards are built (see launch.py), so a
# healthy site answers in about a second. A minute of patience here is
# generous rather than hopeful — and if it is still silent after that,
# something is genuinely wrong, which is a different sentence from the
# one this check used to print at people.
say "checking (the site binds first now, so this should answer in seconds)"
for i in $(seq 1 60); do
  if curl -fsS -m 5 http://127.0.0.1:8000/api/account/me >/dev/null 2>&1; then
    echo "up, answering after ~$((i * 3))s, now on $(git rev-parse --short HEAD)"
    exit 0
  fi
  if ! systemctl is-active --quiet "$SERVICE"; then
    echo
    echo "THE SERVICE EXITED — it is not slow, it is down."
    break
  fi
  if [ $((i % 5)) -eq 0 ]; then echo "  still starting… $((i * 3))s"; fi
  sleep 3
  [ "$i" -ge 20 ] && break        # 60s: answering takes ~1s when healthy
done

echo
echo "IT RESTARTED BUT IS NOT ANSWERING."
echo
echo "  The socket opens before the boards are built, so this is NOT the"
echo "  slow-cold-start case any more — a healthy site answers in about a"
echo "  second. Read the journal before rolling anything back:"
echo
echo "  journalctl -u $SERVICE -n 50 --no-pager"
echo "  roll back:  git checkout $PREV && ./deploy/deploy.sh --no-tests"
exit 1
