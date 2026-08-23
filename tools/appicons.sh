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
# --- the site logo, which is a CUT rather than a scale -----------------
# The home-screen tile above is the whole artwork. The header logo is not,
# twice over:
#
#   * it sits beside `.brand-words`, which already prints "QELLYS BOOK",
#     so an icon carrying the words prints the name twice at two sizes
#     (Ethan, 2026-08-23: "take away where it says qellys book below it");
#   * and the artwork's background — two stadium floodlights and a field
#     of gold dust on black — is right for a phone tile and wrong in a
#     header, where it reads as a photograph of an app icon pasted into
#     the bar. Ethan, the same day: "remove the shiny lights on the left
#     and right side of the crown so the logo can look more natural
#     sitting there and not like a picture placed there".
#
# tools/qbmark.py does the cut and explains how; it also refuses a bad one
# rather than writing it, which matters because every way this can fail
# still produces a picture. QB_CROP is passed in, so the box stays
# declared once, at the top of this file, where tests/test_brand.py reads
# it back and checks it lands in the artwork's empty band.
python3 tools/qbmark.py "$QB_CROP"

echo
echo "The service worker hashes the shell, and icon-192 is in it — so a"
echo "deploy renames the cache by itself and phones pick these up."
