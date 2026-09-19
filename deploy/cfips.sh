#!/usr/bin/env bash
# Install Cloudflare's published edge ranges, so the app can tell who is
# really calling.
#
#   sudo ./deploy/cfips.sh            fetch and install
#   ./deploy/cfips.sh --check         what is installed, and how old
#
# WHY THIS MATTERS. Behind Cloudflare every visitor reaches the app from
# a Cloudflare edge address. Without this list the rate limiter counts a
# whole city into one bucket and starts refusing real customers the
# moment traffic shows up. engine/cfips.py has the long version.
#
# Cloudflare changes these ranges rarely, but they DO change. The deploy
# refreshes it, and there is a weekly cron line at the bottom of
# docs/DEPLOY.md.
set -euo pipefail

DEST="${QB_CF_IPS:-/etc/qellys/cloudflare-ips.txt}"
V4_URL="https://www.cloudflare.com/ips-v4"
V6_URL="https://www.cloudflare.com/ips-v6"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
die()  { red "error: $*" >&2; exit 1; }

if [ "${1:-}" = "--check" ]; then
  python3 - "$DEST" <<'PY'
import sys, os, time, ipaddress
path = sys.argv[1]
if not os.path.exists(path):
    print("NOT INSTALLED  %s" % path)
    print("  the app falls back to the forwarded hop, which behind")
    print("  Cloudflare is an edge address shared by many visitors.")
    print("  fix: sudo ./deploy/cfips.sh")
    raise SystemExit(1)
good = bad = v4 = v6 = 0
for line in open(path):
    line = line.split("#", 1)[0].strip()
    if not line:
        continue
    try:
        net = ipaddress.ip_network(line, strict=False)
    except ValueError:
        bad += 1
        continue
    good += 1
    v4 += net.version == 4
    v6 += net.version == 6
age = (time.time() - os.path.getmtime(path)) / 86400
print("installed  %s" % path)
print("  %d ranges (%d v4, %d v6), %d unparseable" % (good, v4, v6, bad))
print("  %.1f days old" % age)
if age > 90:
    print("  STALE — Cloudflare's ranges do change. Re-run: sudo ./deploy/cfips.sh")
PY
  exit $?
fi

command -v curl >/dev/null || die "curl is not installed"

TMP="$(mktemp)"
trap 'rm -f "$TMP" "$TMP.v4" "$TMP.v6"' EXIT

echo "fetching Cloudflare's published ranges…"
curl -fsS --max-time 30 "$V4_URL" -o "$TMP.v4" \
  || die "could not fetch $V4_URL — check the box has outbound HTTPS"
curl -fsS --max-time 30 "$V6_URL" -o "$TMP.v6" \
  || die "could not fetch $V6_URL"

# VALIDATED BEFORE IT IS INSTALLED. A truncated download or an error page
# served as 200 would otherwise become a file the app reads as "no ranges"
# — or worse, one bad line widening to something it should not cover.
python3 - "$TMP.v4" "$TMP.v6" "$TMP" <<'PY'
import sys, ipaddress
v4_path, v6_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
nets, bad = [], []
for p in (v4_path, v6_path):
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        try:
            nets.append(ipaddress.ip_network(line, strict=False))
        except ValueError:
            bad.append(line)
v4 = [n for n in nets if n.version == 4]
v6 = [n for n in nets if n.version == 6]
if bad:
    raise SystemExit("refusing to install: %d line(s) are not CIDRs, e.g. %r"
                     % (len(bad), bad[0][:60]))
# Cloudflare has published roughly fifteen v4 and seven v6 ranges for
# years. A handful means something served us a stub.
if len(v4) < 10 or len(v6) < 4:
    raise SystemExit("refusing to install: only %d v4 and %d v6 ranges — "
                     "that is not the real list" % (len(v4), len(v6)))
with open(out_path, "w") as fh:
    fh.write("# Cloudflare edge ranges. Written by deploy/cfips.sh.\n")
    fh.write("# Source: https://www.cloudflare.com/ips-v4 and /ips-v6\n")
    for n in nets:
        fh.write("%s\n" % n)
print("%d ranges (%d v4, %d v6)" % (len(nets), len(v4), len(v6)))
PY

mkdir -p "$(dirname "$DEST")"
# World-readable on purpose: it is a public list, and the app may not be
# running as root.
install -m 644 "$TMP" "$DEST"
grn "installed $DEST"
echo
echo "Restart the app so it picks the list up on the next request:"
echo "  sudo systemctl restart qellys"
