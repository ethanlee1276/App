"""Runners, on the bases they are actually on.

Ethan, 2026-09-07: "i guess i have the same question with mlb on if we
are able to display where a batter is on base for the live play by play.
maybe we highlight the bases batters are on and can display a little
circle or something moving along the baseline when the batter is
running."

The first half is real data and is drawn. `live.bases` is documented in
engine/models.py as "MLB: occupied bases, e.g. [2] or [1, 3]" — a list
of base NUMBERS, and the same field the situation row's mini diamond has
always read.

THE SECOND HALF IS NOT DRAWN, and that refusal is a test here rather
than a comment. The feed reports base STATE at the moment a payload was
built, never a runner in motion. A circle sliding along the base path
would be animating something nobody observed, timed to a poll that is
half a minute behind the runner. What IS observed is the state changing,
so a base that has just become occupied pops its marker in.

The bag positions are photo coordinates read off the same 240x150 grid
the wall numbers came from, one base at a time at 6x (scratch:
base1.png, base2.png, base3.png). Reading them from the whole-infield
view first put first and third fourteen units toward the mound — close
enough to look deliberate and wrong enough to sit on the baseline rather
than the bag, which is why the zoom pass exists.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    return APP[i:min([e for e in ends if e != -1])]


def _const(name):
    i = APP.index(f"const {name}")
    first = APP[i:APP.index("\n", i)]
    return first if first.rstrip().endswith(";") else APP[i:APP.index("\n};", i) + 3]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([_const("PBP_PHOTO"), _const("PBP_BASES"), _fn("pbpBasesSVG")])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src + "\n" + js); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_only_the_occupied_bases_are_marked():
    got = _node("""
      const at = (s) => (s.match(/translate\\(([\\d.]+),/g) || []).length;
      console.log(JSON.stringify({
        none: pbpBasesSVG({bases: []}) === "",
        missing: pbpBasesSVG({}) === "",
        one: at(pbpBasesSVG({bases: [1]})),
        corners: at(pbpBasesSVG({bases: [1, 3]})),
        loaded: at(pbpBasesSVG({bases: [1, 2, 3]})),
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    # An empty base needs no marker — the photograph already shows one.
    assert got["none"] and got["missing"], got
    assert got["one"] == 1 and got["corners"] == 2 and got["loaded"] == 3, got


def test_the_field_reads_base_numbers_and_not_a_three_slot_array():
    """engine/models.py: "occupied bases, e.g. [2] or [1, 3]". Read as a
    flag array, [0, 1, 0] would light up first and third."""
    got = _node("""
      const at = (s) => (s.match(/translate\\(([\\d.]+),/g) || []);
      console.log(JSON.stringify({second: at(pbpBasesSVG({bases: [2]}))}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert len(got["second"]) == 1, got
    assert "120" in got["second"][0], got     # second base, not first


def test_the_bags_sit_on_a_diamond_around_the_calibrated_home_plate():
    """The three were measured off one photograph; if they were, they
    agree with the home plate that was measured off it earlier."""
    got = _node("""console.log(JSON.stringify({B: PBP_BASES, H: PBP_PHOTO.home}));""")
    if got is None:
        print("  SKIP node not installed"); return
    b, home = got["B"], got["H"]
    first, second, third = b["1"], b["2"], b["3"]
    # First and third straddle the home-to-second axis, evenly.
    assert abs((first[0] + third[0]) / 2 - home[0]) < 2.5, b
    assert abs(second[0] - home[0]) < 3, b
    # Second is the far bag; first and third are level with each other.
    assert second[1] < first[1] < home[1], b
    assert abs(first[1] - third[1]) < 0.5, b
    # AND THEY ARE NOT INTERCHANGEABLE. Every assertion above survives
    # swapping first and third, which would draw a runner on first at
    # third base. From behind the plate, first is the right-hand bag.
    assert first[0] > home[0] > third[0], b


def test_each_coordinate_actually_lands_on_a_bag():
    """The geometry above is symmetric enough to pass on a sloppy read —
    it did, on one that put first and third fourteen units toward the
    mound. So this asks the PHOTOGRAPH instead.

    A bag in this render is lit warm rather than pure white, but its
    darkest channel is far above the dirt and grass around it, and that
    is the discriminator: the three measured points sample 114-120,
    while the earlier sloppy read sampled 39 (outfield grass) and 58-69
    (infield dirt)."""
    try:
        from PIL import Image
    except ImportError:
        print("  SKIP Pillow not installed"); return
    got = _node("console.log(JSON.stringify(PBP_BASES));")
    if got is None:
        print("  SKIP node not installed"); return
    im = Image.open(ROOT / "web" / "img" / "park" / "park-night.jpg").convert("RGB")
    W, H = im.size
    px = im.load()

    def darkest(gx, gy, r=3):
        x, y = int(gx / 240 * W), int(gy / 150 * H)
        vals = [px[x + dx, y + dy] for dx in range(-r, r + 1) for dy in range(-r, r + 1)]
        return min(min(v) for v in vals[:0] or [tuple(
            round(sum(v[i] for v in vals) / len(vals)) for i in range(3))])

    for base, (gx, gy) in got.items():
        assert darkest(gx, gy) >= 100, (base, gx, gy, darkest(gx, gy))
    # A control: eight units along the baseline from first is not a bag.
    fx, fy = got["1"]
    assert darkest(fx - 8, fy + 4) < 100, "the check would pass anywhere"


def test_no_runner_is_animated_along_a_base_path():
    """The feed gives base state, never a runner in motion. The pop is on
    a base BECOMING occupied, which is the transition we do observe."""
    body = _fn("pbpBasesSVG")
    for motion in ("animateMotion", "mpath", "<path"):
        assert motion not in body, motion
    rule = re.search(r"(?m)^\.pbp-onbase \{([^}]*)\}", CSS)
    assert rule and "animation:" in rule.group(1), "the state change is shown"
    assert "prefers-reduced-motion" in CSS.split(".pbp-onbase")[1][:600]


def test_runners_are_baseball_only_and_ride_the_photograph():
    """The coordinates are the park photograph's. Football has its own
    field and its own overlay; handing it these would put bases on a
    gridiron."""
    art = _fn("pbpParkHTML")
    assert 'const runners = league === "mlb" ? pbpBasesSVG(d.live) : "";' in art
    assert "${art}${runners}${arc}" in art, "under the flight, over the photo"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
