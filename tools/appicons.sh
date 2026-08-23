#!/usr/bin/env bash
# Rebuild the home-screen icons from Ethan's artwork.
#
#   ./tools/appicons.sh
#
# THE HEADER/TAB CROP, recorded here because this script owns it and a
# test reads it back. The home-screen icon is the WHOLE artwork — the
# wordmark belongs on a phone tile — but the site logo sits beside
# `.brand-words`, which already prints the name, so it is cropped to the
# mark alone. Ethan, 2026-08-23: "take away where it says qellys book
# below it".
#
# 825 is the middle of the empty band under the QB: rows 804-846 of the
# source carry no ink at all, which is why the cut can be a constant
# rather than a judgement.
QB_CROP="214,0,1039,825"

# THE SOURCE IS `brand/appicon-1254.png`, committed beside these so the
# icons can be rebuilt without going back to a chat log for the file.
# Ethan, 2026-08-22: "Use the actual image, don't make your own" — so
# `make_icon.py`, which DRAWS a flat Q mark, is no longer what ships and
# must not be run over these.
#
# Needs ffmpeg, which is why this is a hand-run tool and not part of the
# test suite: the suite is standard-library only and runs on a box that
# has no image libraries at all. The outputs are committed instead.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="brand/appicon-1254.png"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }
command -v ffmpeg >/dev/null || { echo "needs ffmpeg"; exit 1; }

for spec in "192:web/icon-192.png" "512:web/icon-512.png" \
            "180:web/apple-touch-icon.png"; do
  n=${spec%%:*}; out=${spec##*:}
  ffmpeg -y -hide_banner -loglevel error -i "$SRC" \
    -vf "scale=${n}:${n}:flags=lanczos" -pix_fmt rgb24 "$out"
  echo "  ${n}x${n}  $out"
done

# MASKABLE IS A DIFFERENT PICTURE, not a different size. Android crops it
# to a circle or squircle and keeps only the central 80%, so the
# full-bleed artwork would lose the crown off the top and BOOK off the
# bottom. Inset into the safe zone, on the black the artwork already has.
ffmpeg -y -hide_banner -loglevel error -i "$SRC" \
  -vf "scale=400:400:flags=lanczos,pad=512:512:56:56:black" -pix_fmt rgb24 \
  web/icon-maskable-512.png
echo "  512x512  web/icon-maskable-512.png  (inset for Android's mask)"
# --- the site logo, which is a CROP rather than a scale ----------------
# The home-screen tile is the whole artwork; the header logo is not. It
# sits beside `.brand-words`, which already prints "QELLYS BOOK", so an
# icon carrying the words prints the name twice at two sizes. Ethan,
# 2026-08-23: "take away where it says qellys book below it".
#
# QB_CROP is declared at the top and tests/test_brand.py reads it back
# and checks its bottom edge lands in the artwork's empty band, so this
# number cannot drift away from the picture.
#
# Rounded because it reads as an app-icon tile rather than a photo pasted
# into the bar, and the radius is baked into the alpha here rather than
# left to CSS — the favicon has no stylesheet.
IFS=, read -r cx cy cw ch <<<"$QB_CROP"
ffmpeg -y -hide_banner -loglevel error -i "$SRC" \
  -vf "crop=$((cw-cx)):$((ch-cy)):${cx}:${cy},scale=152:152:flags=lanczos" \
  web/logo-qb.png
echo "  152x152  web/logo-qb.png  (crown + QB, no wordmark)"

# THE TAB ICON IS THE SAME CROP, EMBEDDED IN AN SVG. It has to keep the
# name favicon.svg because sw.js precaches "/favicon.svg" — deleting it
# would fail the service worker install and take the PWA down — and an
# SVG cannot reference an external image in a favicon, so the bytes go
# inside it.
# Through the ENVIRONMENT, not interpolated: the heredoc is quoted so
# the shell expands nothing inside it, which is what keeps the Python
# below readable as Python.
QB_CROP="$QB_CROP" python3 - <<'EOF'
import base64, io, os
from PIL import Image, ImageDraw
box = tuple(int(v) for v in os.environ["QB_CROP"].split(","))
im = Image.open("brand/appicon-1254.png").convert("RGBA").crop(box)
im = im.resize((64, 64), Image.LANCZOS)
m = Image.new("L", (512, 512), 0)
ImageDraw.Draw(m).rounded_rectangle((0, 0, 511, 511), radius=112, fill=255)
im.putalpha(m.resize((64, 64), Image.LANCZOS))
buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
head = open("web/favicon.svg").read().split('"data:image/png;base64,')[0]
open("web/favicon.svg", "w").write(
    head + '"data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    + '"\n         x="0" y="0" width="48" height="48"/>\n</svg>\n')
EOF
EOF_STATUS=$?
[ "$EOF_STATUS" -eq 0 ] || { echo "favicon step failed"; exit 1; }
echo "  48x48    web/favicon.svg  (same crop, embedded)"

echo
echo "The service worker hashes the shell, and icon-192 is in it — so a"
echo "deploy renames the cache by itself and phones pick these up."
