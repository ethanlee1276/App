#!/usr/bin/env bash
# Go live with Stripe, one guided step at a time.
#
#   sudo ./deploy/golive.sh
#
# RUN IT ON THE DROPLET. It writes /etc/qellys/env and restarts the
# service, neither of which means anything on a laptop.
#
# WHY A SCRIPT AND NOT A CHECKLIST. The checklist version of this was
# followed exactly once and produced nothing: the settings were pasted
# into the shell prompt instead of into the file, because a list of
# commands with an editor step in the middle reads as a list of commands.
# Ethan, 2026-08-21: "I'm gonna need it more in depth on how I do it step
# by step. What's in the droplet and what's in the Mac terminal and what
# do I have to plug in where? You should do that for me."
#
# So this does the parts that can be done here, and for the parts that
# cannot — clicking around the Stripe dashboard, typing a card number —
# it stops, says exactly what to do in the browser, and waits.
#
# SAFE TO RE-RUN, AND MEANT TO BE. It checks what is already set and
# skips it. Stop at any point, come back, run it again.
#
# It never prints a secret and never puts one in shell history: values
# are read from a prompt with echo off.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
ENV_FILE="${QB_ENV_FILE:-/etc/qellys/env}"
SETENV="$ROOT/deploy/setenv.sh"
SERVICE="${QB_SERVICE:-qellys}"
SITE="${QB_SITE:-https://qellysbook.com}"

B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'

step()  { printf '\n%s━━━ %s ━━━%s\n' "$B" "$*" "$N"; }
here()  { printf '%s  [on the droplet — that is here]%s\n' "$D" "$N"; }
browser(){ printf '%s  [in your browser, on your Mac]%s\n' "$D" "$N"; }
ok()    { printf '%s  ok%s  %s\n' "$G" "$N" "$*"; }
warn()  { printf '%s  !!%s  %s\n' "$Y" "$N" "$*"; }
bad()   { printf '%s  XX%s  %s\n' "$R" "$N" "$*"; }
pause() { printf '\n%sPress Enter when that is done.%s ' "$B" "$N"; read -r _; }

# Root already, or via sudo — and QB_ENV_FILE passed through EITHER WAY.
# `sudo` strips the environment by default, so `QB_ENV_FILE=x sudo cmd`
# silently writes to /etc/qellys/env instead. That is fine in production
# and wrong everywhere else, including in a test, which is how it was
# found.
as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    env QB_ENV_FILE="$ENV_FILE" "$@"
  else
    sudo env QB_ENV_FILE="$ENV_FILE" "$@"
  fi
}

have() { grep -q "^$1=." "$ENV_FILE" 2>/dev/null; }
val()  { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | head -1; }

ask() {   # ask KEY "what it is" — prompts, validates via setenv.sh
  local key="$1" what="$2" tries=0
  if have "$key"; then
    ok "$key is already set — leaving it alone (--reset $key to change it)"
    return 0
  fi
  printf '\n  %s%s%s — %s\n' "$B" "$key" "$N" "$what"
  # A CAP, because the first version looped for ever. `setenv.sh` fails
  # on a rejected value AND on end-of-input, and those are the same exit
  # code — so a closed stdin (a pipe, a dropped connection, a stray
  # Ctrl-D) spun this at full speed printing "try again" until the
  # terminal filled up. Three is generous for a paste that went wrong.
  while (( tries < 3 )); do
    if as_root "$SETENV" "$key"; then return 0; fi
    (( tries++ ))
    if (( tries < 3 )); then
      printf '\n  Try again, or Ctrl-C to stop and come back later.\n'
    fi
  done
  bad "three attempts at $key did not take. Stopping here — nothing is broken."
  echo "  Run ./deploy/golive.sh again when you have the right value."
  exit 1
}

# ask_or_default KEY "what it is" DEFAULT
#
# Offers a value and takes Enter as yes. For the two settings whose
# correct value is already known — the Discord invite and the owner's own
# address — there is nothing to look up and nothing to get wrong, so
# asking somebody to type them is asking them to make a typo. Still a
# question rather than an assumption: both are his to change.
ask_or_default() {
  local key="$1" what="$2" default="$3" reply=""
  if have "$key"; then
    ok "$key is already set — leaving it alone"
    return 0
  fi
  printf '\n  %s%s%s — %s\n' "$B" "$key" "$N" "$what"
  printf '  Press Enter for %s%s%s, or type a different one: ' "$B" "$default" "$N"
  read -r reply || reply=""
  [[ -z "$reply" ]] && reply="$default"
  if as_root "$SETENV" "$key" "$reply" >/dev/null; then
    ok "$key = $reply"
  else
    bad "$key would not take that value"
    return 1
  fi
}

restart() {
  printf '  restarting %s… ' "$SERVICE"
  if as_root systemctl restart "$SERVICE"; then
    sleep 3
    if curl -fsS -m 5 http://127.0.0.1:8000/api/account/me >/dev/null 2>&1; then
      printf '%sup%s\n' "$G" "$N"
    else
      warn "restarted but not answering yet — journalctl -u $SERVICE -n 30"
    fi
  else
    bad "restart failed"
  fi
}

if [[ "${1:-}" == "--reset" ]]; then
  as_root "$SETENV" --unset "${2:?--reset needs a key}"
  echo "cleared. Run ./deploy/golive.sh again to set it."
  exit 0
fi

# --- is anybody there ---------------------------------------------------
# The whole script is a conversation. Run with no terminal — piped, or
# from cron — every prompt returns immediately and it charges through
# eight steps answering nothing.
if [[ ! -t 0 ]]; then
  bad "golive.sh needs a terminal — it asks you questions."
  echo "  Run it directly over ssh, not through a pipe or a script."
  exit 1
fi

# --- where am I ---------------------------------------------------------
if [[ ! -d /etc/qellys && -z "${QB_ENV_FILE:-}" ]]; then
  bad "/etc/qellys does not exist."
  echo
  echo "  This script runs ON THE DROPLET, not on your Mac. From the Mac:"
  echo
  echo "      ssh qellys"
  echo "      cd /srv/qellys && sudo ./deploy/golive.sh"
  echo
  exit 1
fi

clear 2>/dev/null || true
cat <<BANNER
${B}Qellys Books — going live${N}

  This walks the whole thing. It does everything that can be done on this
  box, and stops when you need to do something in a browser.

  Everything you type here is on the DROPLET.
  When it says ${B}[in your browser]${N}, switch to your Mac and come back.

  Stop any time with Ctrl-C. Re-running picks up where you left off.
BANNER
pause

# --- 1. the secret key --------------------------------------------------
step "1 of 8 — the Stripe secret key"
browser
cat <<'TXT'
  Open https://dashboard.stripe.com
  Make sure the TEST MODE toggle (top right) is ON.
  Go to:  Developers -> API keys
  Under "Standard keys", find "Secret key" and click "Reveal".
  Copy it. It starts with  sk_test_
TXT
here
ask STRIPE_SECRET_KEY "the sk_test_... value you just copied"

# CHECKED AGAINST STRIPE THE MOMENT IT IS PASTED. At a silent prompt,
# "nothing appeared because it is not echoed" and "nothing appeared
# because the paste did not take" look identical, and the difference
# does not otherwise surface until two steps later as an error about
# something else. One API call turns that into a yes or a no, here.
printf '  checking the key with Stripe… '
KEYINFO="$(cd "$ROOT" && python3 -c '
from engine import billing as BI, stripeset as SS
BI._env()
import os, sys
try:
    got = SS.verify_key(os.environ["STRIPE_SECRET_KEY"])
except Exception as exc:
    print("BAD", exc); sys.exit(0)
print("OK", "LIVE" if got["live"] else "TEST", got["account"], got["name"] or "-")
' 2>/dev/null)"
case "$KEYINFO" in
  OK*)
    set -- $KEYINFO
    printf '%sworks%s — %s mode, account %s\n' "$G" "$N" "$2" "$3"
    if [[ "$2" == "LIVE" ]]; then
      warn "That is a LIVE key. Real cards will be charged."
    fi ;;
  *)
    bad "Stripe would not accept that key."
    echo "      ${KEYINFO#BAD }"
    echo
    echo "  Clear it and try again:"
    echo "      sudo ./deploy/setenv.sh --unset STRIPE_SECRET_KEY"
    echo "      sudo ./deploy/golive.sh"
    exit 1 ;;
esac
# CHECKED, not assumed. This printed "ok" unconditionally, including
# when setenv had just refused the value — a script that reports success
# it did not have is worse than one that says nothing.
if have QB_SITE_URL; then
  ok "QB_SITE_URL is already set"
elif as_root "$SETENV" QB_SITE_URL "$SITE" >/dev/null; then
  ok "QB_SITE_URL = $SITE"
else
  bad "could not set QB_SITE_URL to '$SITE' — set QB_SITE and re-run"
  exit 1
fi
restart

# --- 2. the prices ------------------------------------------------------
step "2 of 8 — create the three prices in Stripe"
here
echo "  Creating the Product and the Monthly / 6-month / Yearly prices."
echo "  Safe if they already exist — it finds them instead of duplicating."
echo
ENVLINES="$(cd "$ROOT" && python3 launch.py --stripe-setup --print-env 2>/tmp/golive-err)"
RC=$?
if [[ $RC -ne 0 ]]; then
  bad "could not create the prices:"
  sed 's/^/      /' /tmp/golive-err
  echo
  echo "  Fix that and run ./deploy/golive.sh again."
  exit 1
fi
# WRITTEN, NOT COPIED. Transcribing three price ids by hand is where a
# swapped pair comes from, and a swapped pair charges the wrong amount to
# somebody who picked the other plan without failing anywhere.
while IFS='=' read -r k v; do
  [[ -z "$k" ]] && continue
  as_root "$SETENV" "$k" "$v" >/dev/null && ok "$k written"
done <<< "$ENVLINES"
restart

# --- 3. the webhook -----------------------------------------------------
step "3 of 8 — the webhook (this is the one that must not be skipped)"
if have STRIPE_WEBHOOK_SECRET; then
  ok "STRIPE_WEBHOOK_SECRET is already set"
else
  here
  echo "  Creating the endpoint in Stripe for you — the URL and all five"
  echo "  events, so none of it is typed."
  echo
  WH="$(cd "$ROOT" && python3 launch.py --stripe-webhook --print-env 2>/tmp/golive-wh)"
  RC=$?
  if [[ $RC -eq 3 ]]; then
    # One exists and Stripe will not reveal an old secret — see
    # ensure_webhook. Replacing it is safe and is the only way forward.
    sed 's/^/      /' /tmp/golive-wh
    printf '\n%sReplace it with a fresh one? Nothing is lost. [y/N]%s ' "$B" "$N"
    read -r yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
      WH="$(cd "$ROOT" && python3 launch.py --stripe-webhook --recreate --print-env 2>/tmp/golive-wh)"
      RC=$?
    else
      bad "cannot continue without the signing secret."
      exit 1
    fi
  fi
  if [[ $RC -ne 0 || -z "$WH" ]]; then
    bad "could not create the webhook:"
    sed 's/^/      /' /tmp/golive-wh
    exit 1
  fi
  sed 's/^/  /' /tmp/golive-wh
  # WRITTEN, NEVER SHOWN. The signing secret goes from Stripe's reply
  # straight into the file. It is the one string nobody should have to
  # handle, and it is the one most often pasted into the wrong slot.
  while IFS='=' read -r k v; do
    [[ -z "$k" ]] && continue
    as_root "$SETENV" "$k" "$v" >/dev/null && ok "$k written"
  done <<< "$WH"
  rm -f /tmp/golive-wh
  restart
fi
echo
warn "Without this, somebody can pay and never get access — the money"
warn "arrives, Stripe shows a failing endpoint, and nothing here reports it."

# --- 4. check -----------------------------------------------------------
step "4 of 8 — check what the server sees"
here
(cd "$ROOT" && python3 launch.py --stripe)
echo
printf '%sEverything above should say "ok". If it does not, stop here.%s\n' "$B" "$N"
pause

# --- 5. buy something ---------------------------------------------------
step "5 of 8 — buy something with a test card"
browser
cat <<TXT
  ${B}This step has no substitute.${N} Everything can be configured
  correctly and still be broken.

  1. Open ${SITE} in a browser.
  2. Sign in (or make an account).
  3. Pick any plan, click Get started, then Continue to secure checkout.
  4. Pay with:
         card    4242 4242 4242 4242
         expiry  any future date, e.g. 12/34
         CVC     any 3 digits
         ZIP     any 5 digits

  Then check all three:
     a) it lets you back into the site within a second or two
     b) Stripe -> Developers -> Webhooks shows the delivery SUCCEEDED
     c) your account page names the plan you bought

  If (a) fails but (b) succeeded, tell me — that is the return-trip poll.
  If (b) failed, Stripe shows you the response body. Tell me what it says.
TXT
pause

# --- 6. discord and the code -------------------------------------------
step "6 of 8 — the Discord invite and your promo code"
here
ask_or_default QB_DISCORD_INVITE \
  "the invite for the members' room" \
  "${QB_DEFAULT_DISCORD:-https://discord.gg/vCAZjntyX}"
# Optional, and it is fine to skip: the Discord page just drops the
# sentence that cites it. Not a secret — it is quoted TO people who have
# not paid, which is why it is not gated the way the invite is.
if have QB_INSTAGRAM; then
  ok "QB_INSTAGRAM is already set"
else
  echo "      Your Instagram profile URL (optional — press Enter to skip)."
  read -rp "      QB_INSTAGRAM: " _gram || true
  if [ -n "${_gram:-}" ]; then
    as_root "$SETENV" QB_INSTAGRAM "$_gram" >/dev/null && ok "QB_INSTAGRAM set"
  else
    ok "skipped — the Discord page will simply not mention Instagram"
  fi
fi
if have QB_CODES; then
  ok "QB_CODES is already set"
else
  as_root "$SETENV" QB_CODES "USFARATHANE:12:100" >/dev/null
  ok "QB_CODES = USFARATHANE:12:100  (12 months, up to 100 uses)"
  echo "      The last number is USES, not a percent. A code opens the"
  echo "      whole site — there is no partial discount."
fi
restart

# --- 7. live mode -------------------------------------------------------
step "7 of 8 — switch to LIVE (real cards)"
CURKEY="$(val STRIPE_SECRET_KEY)"
if [[ "$CURKEY" == sk_live_* ]]; then
  ok "already on a live key"
else
  cat <<TXT

  ${B}Only do this once step 5 worked.${N}

  In Stripe: turn the TEST MODE toggle OFF, then Developers -> API keys
  and copy the LIVE secret key. It starts with  sk_live_

  That is the only thing you need. The live side of the account has its
  own prices and its own webhook, both different from the test ones, and
  this script creates both again — you do not go back to the dashboard.

TXT
  printf '%sSwitch to live now? [y/N]%s ' "$B" "$N"; read -r yn
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    as_root "$SETENV" --unset STRIPE_SECRET_KEY >/dev/null
    as_root "$SETENV" --unset STRIPE_WEBHOOK_SECRET >/dev/null
    for k in STRIPE_PRICE_MONTHLY STRIPE_PRICE_SIXMONTH STRIPE_PRICE_YEARLY; do
      as_root "$SETENV" --unset "$k" >/dev/null
    done
    ok "cleared the test values"
    echo
    echo "  Now run this script again and give it the LIVE values."
    exit 0
  else
    ok "staying in test mode — run this again when you are ready"
  fi
fi

# --- 8. the paywall -----------------------------------------------------
step "8 of 8 — turn the paywall on"
here
if have QB_PAYWALL; then
  ok "QB_PAYWALL is already set"
else
  if ! have QB_COMP_EMAILS; then
    echo
    echo "  Your own address goes in FIRST. With an empty comp list the"
    echo "  first thing the paywall does is lock you out of your own board."
    ask_or_default QB_COMP_EMAILS "your own email address" \
      "${QB_DEFAULT_EMAIL:-ethanlee1276@gmail.com}"
  fi
  printf '\n%sTurn the paywall ON now? Everything paid becomes members-only. [y/N]%s ' "$B" "$N"
  read -r yn
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    as_root "$SETENV" QB_PAYWALL 1 >/dev/null
    restart
    ok "paywall on — the restart sealed the boards on disk"
  else
    ok "left off. Run this again when you want it on."
    exit 0
  fi
fi

# --- prove it -----------------------------------------------------------
step "proving it from the outside"
here
echo "  Fetching a paid board with no account, the way a stranger would:"
echo
BODY="$(curl -fsS -m 10 "$SITE/data/recommendations.json" 2>/dev/null || true)"
if [[ -z "$BODY" ]]; then
  warn "could not fetch $SITE/data/recommendations.json — check it by hand"
else
  COUNT="$(printf '%s' "$BODY" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("recommendations") or []))' 2>/dev/null || echo "?")"
  if [[ "$COUNT" == "0" ]]; then
    ok "0 picks visible to a stranger — the wall is real"
  else
    bad "$COUNT picks are readable with no account. Run: python3 launch.py --seal"
  fi
fi

echo
(cd "$ROOT" && python3 launch.py --stripe)
step "done"
echo "  Full reference: docs/GOLIVE.md"
echo "  What is set:    sudo ./deploy/setenv.sh --show"
echo "  Everything:     python3 launch.py --todo"
echo
