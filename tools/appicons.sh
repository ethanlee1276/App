#!/usr/bin/env bash
# Rebuild the home-screen icons from Ethan's artwork.
#
#   ./tools/appicons.sh
#
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
echo
echo "The service worker hashes the shell, and icon-192 is in it — so a"
echo "deploy renames the cache by itself and phones pick these up."
