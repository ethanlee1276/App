"""The app icon fills its tile (tools/appiconfit.py; Ethan, 2026-10-28, with
the new artwork attached: "here is the new app icon too use. Make it fit
right.").

His artwork is a picture OF an app icon: a dark rounded tile with a thin
gold rim, floating on a darker backdrop with a margin all round. Scaled
whole, a phone would show that tile inside its own. What these hold:

  * his file is committed as he sent it, and every icon is made from it;
  * the tile fills the square: the gold rim runs just inside every edge,
    with no backdrop margin and no second tile;
  * the rim sits inside the corner iOS cuts every icon to, so the phone
    never cuts it, and is wide enough to read at the iPhone's 180px;
  * Android's maskable icon keeps the crown and the QB inside its 80%
    circle, with no rim for the circle to cut into arcs;
  * no icon has an alpha channel (tests/test_brand.py), and the header logo
    is still cut from the first artwork.

Run directly: `python3 tests/test_the_app_icon_fills_its_tile.py`
"""
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BRAND, WEB = ROOT / "brand", ROOT / "web"
ICONS = {"apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}


def _image():
    """Pillow's Image, or None where it is missing (the box's suite has no
    image libraries), so these skip there rather than fail."""
    try:
        from PIL import Image
    except ImportError:
        print("      (skipped: no Pillow)")
        return None
    return Image


def _tool():
    sys.path.insert(0, str(ROOT / "tools"))
    import appiconfit
    return appiconfit


def _png_size(path: Path) -> tuple:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def test_his_file_is_committed_and_the_icons_are_made_from_it():
    assert _png_size(BRAND / "appicon-2026-10-28.png") == (1254, 1254)
    assert _png_size(BRAND / "appicon-1024.png") == (1024, 1024), "the fitted master: the iOS build's icon"
    for name, n in ICONS.items():
        assert _png_size(WEB / name) == (n, n), name
    sh = (ROOT / "tools" / "appicons.sh").read_text(encoding="utf-8")
    assert "python3 tools/appiconfit.py" in sh, "the build script makes the home-screen icons with the fitter"
    assert "ffmpeg" not in re.sub(r"(?m)^\s*#.*$", "", sh), "the old whole-artwork scale is gone"
    assert 'python3 tools/qbmark.py "$QB_CROP"' in sh, "the header logo is still cut from the first artwork"
    tool = (ROOT / "tools" / "appiconfit.py").read_text(encoding="utf-8")
    assert 'SRC = os.path.join(ROOT, "brand", "appicon-2026-10-28.png")' in tool
    assert tool.count("raise SystemExit") >= 5, "the fitter refuses what it cannot vouch for"
    readme = (ROOT / "deploy" / "ios" / "README.md").read_text(encoding="utf-8")
    assert "App icon: `brand/appicon-1024.png`" in readme


def test_every_size_is_the_fitted_master():
    Image = _image()
    if Image is None:
        return
    master = Image.open(BRAND / "appicon-1024.png").convert("RGB")
    for name, n in ICONS.items():
        got = Image.open(WEB / name)
        assert got.mode == "RGB", f"{name} is {got.mode}: an icon with alpha is composited however the OS likes"
        want = master.resize((n, n), Image.LANCZOS)
        diff = sum(abs(a - b) for pa, pb in zip(got.getdata(), want.getdata()) for a, b in zip(pa, pb)) / (n * n * 3)
        assert diff < 2, f"{name} is not the master at {n}px (mean difference {diff:.1f})"


def test_the_tile_fills_the_square_with_its_rim_just_inside_the_edge():
    Image = _image()
    if Image is None:
        return
    F = _tool()
    m = Image.open(BRAND / "appicon-1024.png").convert("RGB")
    px = m.load()
    mid = 512
    lum = lambda p: sum(p) / 3  # noqa: E731
    gold = lambda p: p[0] > p[1] > p[2] and p[0] > 80  # noqa: E731
    lines = {"top": [(mid, y) for y in range(0, 40)], "bottom": [(mid, 1023 - y) for y in range(0, 40)],
             "left": [(x, mid) for x in range(0, 40)], "right": [(1023 - x, mid) for x in range(0, 40)]}
    for side, line in lines.items():
        rim = [i for i, p in enumerate(line) if gold(px[p])]
        assert rim and F.RIM_INSET - 1 <= rim[0] <= F.RIM_INSET + 1 and rim[-1] <= F.RIM_INSET + F.RIM_WIDTH, \
            f"the {side} rim is not just inside the edge: gold at {rim}"
        assert all(lum(px[p]) < 30 for p in line[:F.RIM_INSET - 1]), f"backdrop outside the {side} rim"
    # No second tile and no backdrop margin: just inside the rim is the
    # field, and the crown and the QB fill the middle the way the artwork's do.
    assert all(lum(px[(mid, y)]) < 40 for y in range(24, 120)), "a second edge inside the rim"
    rows = [y for y in range(40, 984) if any(lum(px[(x, y)]) > 150 for x in range(300, 724, 3))]
    assert 135 < rows[0] < 165 and 805 < rows[-1] < 840, f"the mark spans rows {rows[0]}-{rows[-1]} of 1024"


def test_the_rim_sits_inside_the_corner_ios_cuts_and_reads_at_180px():
    Image = _image()
    if Image is None:
        return
    F = _tool()
    m = Image.open(BRAND / "appicon-1024.png").convert("RGB")
    px = m.load()
    # iOS's mask, pulled in 4px for any difference in its corner: every gold
    # pixel of the outer band lies inside it, so none is ever cut.
    inside = F.shape(1024, 4, F.RADIUS * 1024 - 4).load()
    cut = [(x, y) for y in range(0, 1024, 2) for x in range(0, 1024, 2)
           if min(x, y, 1023 - x, 1023 - y) < 90 and px[x, y][0] > 120 and px[x, y][0] > px[x, y][2] + 60
           and inside[x, y] < 128]
    assert not cut, f"gold the phone's corner would cut: {cut[:6]}"
    small = Image.open(WEB / "apple-touch-icon.png").convert("RGB").load()
    top = [small[90, y] for y in range(0, 6)]
    assert max(p[0] for p in top) > 150, f"the rim is lost at 180px: {top}"


def test_the_maskable_icon_keeps_the_mark_in_androids_circle_and_has_no_rim():
    Image = _image()
    if Image is None:
        return
    mk = Image.open(WEB / "icon-maskable-512.png")
    assert mk.size == (512, 512) and mk.mode == "RGB"
    px = mk.convert("RGB").load()
    far = max(math.hypot(x - 256, y - 256) for y in range(0, 512, 2) for x in range(0, 512, 2)
              if sum(px[x, y]) / 3 > 110)
    assert far <= 0.4 * 512, f"the mark reaches {far:.0f}px out, past the safe circle"
    for y in range(0, 60):                        # top middle: ground and field, never the rim's gold
        r, g, b = px[256, y]
        assert not (r > 120 and r > b + 60), f"a rim at the top of the maskable icon: {(r, g, b)} at {y}"
    corners = [px[x, y] for x, y in ((4, 256), (256, 4), (507, 256), (256, 507))]
    assert all(sum(p) / 3 < 40 for p in corners), corners


def test_the_header_logo_is_untouched():
    head = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<img class="qmark" src="logo-qb.png"' in head
    qb = (ROOT / "tools" / "qbmark.py").read_text(encoding="utf-8")
    assert 'SRC = os.path.join(ROOT, "brand", "appicon-1254.png")' in qb


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
