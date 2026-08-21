#!/usr/bin/env bash
# Set one value in /etc/qellys/env, without an editor and without
# leaving it in shell history.
#
#   sudo ./deploy/setenv.sh STRIPE_SECRET_KEY
#   sudo ./deploy/setenv.sh QB_PAYWALL 1        # non-secret, inline is fine
#   sudo ./deploy/setenv.sh --show              # what is set (values hidden)
#   sudo ./deploy/setenv.sh --unset QB_PAYWALL
#
# WHY THIS EXISTS. The runbook said "sudo nano /etc/qellys/env" and then
# showed the lines to add. On 2026-08-21 that got read as a list of
# commands: every KEY=VALUE was pasted straight into the bash prompt,
# where it set a shell variable in one SSH session and nothing else. The
# service reads the FILE, so nothing was configured, `--stripe` reported
# five things missing, and one of the pasted lines was the placeholder
# `sk_test_...` rather than a real key. Nothing broke, and nothing worked.
#
# An editor step in the middle of a list of commands is a trap. This
# removes it.
#
# WITH NO VALUE ARGUMENT IT PROMPTS, and reads silently. That is the
# point for secrets: a value typed at a prompt is not in ~/.bash_history,
# is not in `ps`, and is not in /proc/<pid>/cmdline the way an argument
# would be.
#
# Replaces an existing key rather than appending, so running it twice
# does not leave two lines where the LAST one silently wins.
set -euo pipefail

FILE="${QB_ENV_FILE:-/etc/qellys/env}"

die() { echo "error: $*" >&2; exit 1; }

[[ "${1:-}" == "" ]] && die "usage: sudo $0 KEY [VALUE] | --show | --unset KEY"

# --- reading -----------------------------------------------------------
if [[ "$1" == "--show" ]]; then
  [[ -f "$FILE" ]] || { echo "$FILE does not exist yet — nothing is set."; exit 0; }
  echo "$FILE:"
  # VALUES ARE NEVER PRINTED. A key in a terminal is a key in a
  # scrollback buffer, a screenshot and a support thread. The length is
  # enough to tell "set" from "set to the placeholder".
  while IFS='=' read -r k v; do
    [[ -z "$k" || "$k" == \#* ]] && continue
    if [[ -z "$v" ]]; then
      printf '  %-24s (empty)\n' "$k"
    elif [[ "$v" == *"..."* ]]; then
      printf '  %-24s *** LOOKS LIKE A PLACEHOLDER: %s\n' "$k" "$v"
    else
      printf '  %-24s set (%d chars)\n' "$k" "${#v}"
    fi
  done < "$FILE"
  exit 0
fi

# --- writing -----------------------------------------------------------
if [[ "$1" == "--unset" ]]; then
  KEY="${2:-}"; [[ -n "$KEY" ]] || die "--unset needs a key"
  [[ -f "$FILE" ]] || die "$FILE does not exist"
  sed -i "/^${KEY}=/d" "$FILE"
  echo "removed $KEY. Now: sudo systemctl restart qellys"
  exit 0
fi

KEY="$1"
[[ "$KEY" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "'$KEY' is not an environment variable name"

if [[ $# -ge 2 ]]; then
  VALUE="$2"
else
  # -s so it is not echoed; the trailing newline is ours to print.
  read -rsp "Value for $KEY (paste it, then Enter): " VALUE
  echo
fi

[[ -n "$VALUE" ]] || die "no value given — use --unset to clear a key"

# The placeholder check, because that is what actually happened.
case "$VALUE" in
  *"..."*|"<"*|"["*)
    die "'$VALUE' looks like a placeholder from the docs, not a real value" ;;
esac

# Prefix sanity for the ones with a known shape. A test key where a live
# one belongs charges nobody and looks identical in a config file.
case "$KEY" in
  STRIPE_SECRET_KEY)
    [[ "$VALUE" == sk_test_* || "$VALUE" == sk_live_* || "$VALUE" == rk_* ]] \
      || die "a Stripe secret key starts with sk_test_ or sk_live_" ;;
  STRIPE_WEBHOOK_SECRET)
    [[ "$VALUE" == whsec_* ]] \
      || die "a webhook signing secret starts with whsec_ — the API key is a different string" ;;
  STRIPE_PRICE_*)
    [[ "$VALUE" == price_* ]] \
      || die "a price id starts with price_ (prod_... is the PRODUCT, not the price)" ;;
  QB_SITE_URL)
    [[ "$VALUE" == https://* ]] || die "QB_SITE_URL needs the https:// scheme" ;;
  QB_DISCORD_INVITE)
    [[ "$VALUE" == https://discord.gg/* ]] || die "that is not a discord.gg invite" ;;
  QB_INSTAGRAM)
    # Unlike the invite, this one is PUBLIC — the Discord page cites it to
    # people who have not subscribed, which is the point of citing it.
    [[ "$VALUE" == https://www.instagram.com/* || "$VALUE" == https://instagram.com/* ]] \
      || die "give the full profile URL, e.g. https://instagram.com/yourhandle" ;;
esac

mkdir -p "$(dirname "$FILE")"
touch "$FILE"
# 600 and root-owned: the service reads it as root at start, and nothing
# else on the box has any business reading it.
chmod 600 "$FILE"

if grep -q "^${KEY}=" "$FILE" 2>/dev/null; then
  # A literal replacement, not sed's pattern space — a key or a URL
  # contains slashes and ampersands that sed would interpret.
  python3 - "$FILE" "$KEY" "$VALUE" <<'PY'
import sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as fh:
    lines = fh.read().splitlines()
out = [f"{key}={value}" if l.startswith(key + "=") else l for l in lines]
with open(path, "w") as fh:
    fh.write("\n".join(out) + "\n")
PY
  echo "updated $KEY"
else
  printf '%s=%s\n' "$KEY" "$VALUE" >> "$FILE"
  echo "added $KEY"
fi

echo "Now: sudo systemctl restart qellys"
