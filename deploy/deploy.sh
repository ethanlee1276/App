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

# --- 1. a way back ---------------------------------------------------
# Tagged BEFORE anything changes, so rollback is one command and does not
# depend on remembering what was deployed.
PREV="$(git rev-parse --short HEAD)"
say "current: $PREV  (roll back with: git checkout $PREV && ./deploy/deploy.sh)"

# --- 2. back up the databases ----------------------------------------
# Before the code changes, not after. A migration that goes wrong is
# exactly when the pre-migration copy is the only useful thing on the box.
say "backing up"
./deploy/backup.sh

# --- 3. new code ------------------------------------------------------
say "pulling"
git pull --ff-only

# --- 4. the gate ------------------------------------------------------
if [[ "$RUN_TESTS" == "1" ]]; then
  say "running the suite (this is the gate, ~12 min)"
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
say "checking (a cold start builds every board first — up to 3 min)"
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
  if [ $((i % 10)) -eq 0 ]; then echo "  still starting… $((i * 3))s"; fi
  sleep 3
done

echo
echo "IT RESTARTED BUT IS NOT ANSWERING."
echo "  journalctl -u $SERVICE -n 50"
echo "  roll back:  git checkout $PREV && ./deploy/deploy.sh --no-tests"
exit 1
