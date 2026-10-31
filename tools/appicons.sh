#!/usr/bin/env bash
# Rebuild the home-screen icons and the site logo from Ethan's artwork.
#
#   ./tools/appicons.sh
#
# TWO SOURCES SINCE 2026-10-28, committed in brand/ so nothing has to come
# back out of a chat log:
#   * brand/appicon-2026-10-28.png, the app icon he sent that day ("here is
#     the new app icon too use. Make it fit right."): tools/appiconfit.py
#     fits its tile to the square, redraws its gold rim inside the shape iOS
#     cuts icons to, and writes the 1024 master (brand/appicon-1024.png, the
#     iOS build's icon), the 180, 192 and 512 icons and the maskable one;
#   * brand/appicon-1254.png, the first artwork (2026-08-22, "Use the actual
#     image, don't make your own"), which the header logo is still cut from
#     (below).
# `make_icon.py`, which DRAWS a flat Q mark, is not what ships and must not
# be run over these.
#
# THE HEADER/TAB CROP, recorded here because this script owns it and a
# test reads it back. The site logo sits beside `.brand-words`, which
# already prints the name, so it is cropped to the mark alone. Ethan,
# 2026-08-23: "take away where it says qellys book below it".
#
# 825 is the middle of the empty band under the QB: rows 804-846 of the
# source carry no ink at all, which is why the cut can be a constant
# rather than a judgement.
QB_CROP="214,0,1039,825"

# Needs Pillow, which is why this is a hand-run tool and not part of the
# test suite: the suite is standard-library only and runs on a box that
# has no image libraries at all. The outputs are committed instead.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in brand/appicon-2026-10-28.png brand/appicon-1254.png; do
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
done

python3 tools/appiconfit.py

# --- the site logo, which is a CUT rather than a scale -----------------
# Cut from the first artwork, the whole of which was the home-screen tile
# until 2026-10-28. The header logo was never that tile, twice over:
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
