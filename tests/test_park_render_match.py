"""The park card to Ethan's two renders.

Ethan, 2026-09-06, with a park card and a play card: "Now that we got the
actual park render done, I want you too match our page more too these
renders."

Four things his renders do that the page did not:

  * the wall numbers carry their position ("336 / LF"), because three
    numbers in a row over a fence mean nothing until you know which is
    the line and which is the alley;
  * the batted-ball caption sits BESIDE THE LANDING MARK, titled by what
    the ball was, with the numbers under it — ours sat at the arc's apex,
    in open sky, as one run-on line;
  * the park factors lead with the number and name the baseline;
  * each batted-ball tile wears a glyph.

Two things his renders show that we do not hold, and therefore do not
draw: the LCF/RCF distances, and the compass sector the wind comes from.
Those refusals are pinned in tests/test_park_shape.py.

The caption's geometry is the only arithmetic here, and it is exercised
for real in node against balls hit to every corner of the park.
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
VIS = (ROOT / "web" / "js" / "visuals.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _const(name):
    """One `const` declaration, whether it closes on its line or not.

    The first version keyed on "is there a `{` nearby" and then hunted
    for "\n};" — which for a ONE-LINE object literal ran past the end of
    the declaration and swallowed everything up to the next multi-line
    one, redeclaring it. Node caught it; nothing else would have."""
    i = APP.index(f"const {name}")
    first = APP[i:APP.index("\n", i)]
    if first.rstrip().endswith(";"):
        return first
    return APP[i:APP.index("\n};", i) + 3]


def _node(js):
    """The arc, with everything it reads, run for real."""
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([
        _const("PBP_PHOTO"), _const("PBP_POLE_DEG"), _const("PBP_TRAJ"),
        "function escapeHtml(s){return String(s).replace(/[&<>\"']/g, (c) => "
        "({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}",
        # `wallShape` is deliberately NOT stubbed. On the photo path — the
        # one every live MLB game takes — `pbpFlight` calls
        # `pbpPhotoWall`, never `pbpWallPoint`, so the visuals.js shape
        # never enters this arithmetic. `typeof` guards the reference.
        _fn("pbpPhotoWall"), _fn("pbpWallPoint"), _fn("pbpFenceFt"),
        _fn("pbpFieldToArt"), _fn("pbpFlight"), _fn("pbpCalloutBox"),
        _fn("pbpArcSVG"),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src + "\n" + js); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# ------------------------------------------------------------ the caption ---
def test_the_caption_is_anchored_to_the_landing_mark_not_the_arcs_apex():
    body = _fn("pbpArcSVG")
    assert "pbpCalloutBox(f.L, cw, ch)" in body, "placed off the landing point"
    assert "f.C[0]" not in body.split("const title")[1], "no longer hung off the apex"
    # Two lines, the way his callout reads: what it was, then how hard
    # and how far.
    assert "escapeHtml(title)" in body and "escapeHtml(detail)" in body
    assert "MPH" in body


def test_the_caption_box_keeps_itself_in_frame_at_every_edge():
    """Driven directly, because no real landing point reaches these — see
    pbpCalloutBox's own note on why the guard exists anyway."""
    got = _node("""
      const W = 104, H = 19, out = [];
      for (const x of [-40, 0, 4, 120, 232, 236, 300]) {
        for (const y of [-30, 0, 4, 20, 75, 146, 149, 200]) {
          const [bx, by] = pbpCalloutBox([x, y], W, H);
          out.push({x, y, bx, by});
        }
      }
      console.log(JSON.stringify(out));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert len(got) == 56
    for b in got:
        assert 4 <= b["bx"] <= 236 - 104, b
        assert b["bx"] + 104 <= 236, b
        assert 4 <= b["by"] <= 146 - 19, b
        assert b["by"] + 19 <= 146, b


def test_the_caption_prefers_up_and_right_of_the_mark():
    """The clamps must not flatten the placement into one corner."""
    got = _node("""
      console.log(JSON.stringify({
        room:  pbpCalloutBox([100, 90], 60, 19),
        right: pbpCalloutBox([220, 90], 60, 19),
        top:   pbpCalloutBox([100, 12], 60, 19),
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["room"] == [107, 65], got["room"]
    # Flipped means the whole box sits clear of the mark, not merely
    # nudged left by the clamp — the clamp alone would leave it lying
    # across the landing point it is supposed to be labelling.
    assert got["right"][0] + 60 <= 220, ("the box clears the mark", got["right"])
    assert got["top"][1] >= 12, ("dropped below the mark", got["top"])


def test_the_caption_never_leaves_the_frame_wherever_the_ball_lands():
    """A ball pulled down either line would push its own caption off the
    picture. The box flips to the other side of the mark instead."""
    got = _node("""
      const park = {lf_ft: 336, cf_ft: 396, rf_ft: 322};
      const out = [];
      for (const x of [40, 80, 125.42, 170, 210]) {
        for (const dist of [15, 200, 340, 440]) {
          const svg = pbpArcSVG({distance: dist, launch_speed: 98.5, launch_angle: -7,
                                 trajectory: "ground_ball", x, y: 100}, park, {photo: true});
          if (!svg) continue;
          const m = svg.match(/<rect x="([-\\d.]+)" y="([-\\d.]+)" width="([\\d.]+)" height="(\\d+)"/);
          if (!m) continue;
          out.push({x: +m[1], y: +m[2], w: +m[3], h: +m[4], at: [x, dist]});
        }
      }
      console.log(JSON.stringify(out));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert len(got) >= 15, f"only {len(got)} arcs drew"
    for b in got:
        assert b["x"] >= 0, b
        assert b["x"] + b["w"] <= 240.5, b
        assert b["y"] >= 0, b
        assert b["y"] + b["h"] <= 150.5, b


def test_a_ball_with_no_trajectory_still_reports_what_is_known():
    got = _node("""
      const park = {lf_ft: 336, cf_ft: 396, rf_ft: 322};
      const svg = pbpArcSVG({distance: 402, x: 125.42, y: 100}, park, {photo: true});
      console.log(JSON.stringify({has: svg.includes("402 FT"),
                                  lines: (svg.match(/<text /g) || []).length}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["has"], "the distance is still captioned"
    assert got["lines"] == 1, "one line, not an empty title above it"


# -------------------------------------------------------------- the chips ---
def test_the_wall_chip_carries_the_position_under_the_number():
    body = _fn("pbpPhotoHTML")
    assert "key.toUpperCase()" in body, "the label comes from the field, not a literal"
    nums = re.findall(r'font-size="([\d.]+)"', body)
    assert len(nums) == 2 and float(nums[0]) > float(nums[1]), (
        "the distance is the headline and the position is the note", nums)


# ------------------------------------------------------------- the header ---
def test_the_header_wears_our_mark_and_boxes_the_venue():
    body = _fn("pbpParkHeadHTML")
    assert "brandMarkHTML(" in body, "the same mark file as the masthead"
    assert "REAL DATA. REAL PLAYS." in body
    rule = re.search(r"(?m)^\.pbp-parkhead-v \{(.*?)\}", CSS, re.S).group(1)
    assert "border:" in rule and "padding:" in rule, rule


def test_the_wind_is_spelled_the_way_a_person_says_it():
    """`wind_dir` ships "out" | "in" | "cross". "12 mph in" is not a
    sentence; his render says "Blowing In"."""
    assert "const PBP_WIND = {out:" in APP
    body = _fn("pbpParkHeadHTML")
    assert "PBP_WIND[w.wind_dir]" in body
    for token in ("blowing out", "blowing in", "crosswind"):
        assert token in APP, token
    # An unknown token prints the speed alone rather than the raw word.
    assert 'rel ? " " + rel : ""' in body


def test_a_closed_roof_is_said_out_loud():
    body = _fn("pbpParkHeadHTML")
    assert "w.dome" in body and "closed roof" in body
    # The other word order is a reason prefix the browser may not carry;
    # tests/test_knowledge.py owns that rule and caught this in the gate.
    assert '"roof closed"' not in body


# -------------------------------------------------------------- the tiles ---
def test_every_batted_ball_tile_wears_a_mark_the_site_already_draws():
    body = _fn("pbpBattedHTML")
    assert "icon(ic, 12)" in body, "the tile actually renders the mark"
    names = re.findall(r'tile\("([a-z]+)"', body)
    assert len(names) == 4, names
    for n in names:
        assert f"\n  {n}:" in APP, f"{n} is not in ICON_PATHS"
    rule = re.search(r"(?m)^\.pbp-bb-tile \.k \{(.*?)\}", CSS, re.S).group(1)
    assert "display: flex" in rule, "the glyph sits on the label's line"


def test_the_new_glyphs_are_drawn_on_the_files_own_grid():
    """An icon library is the exact tell the icon set's own note watches
    for. These are paths in the same 16-unit box as every other one."""
    for name in ("gauge", "angle"):
        i = APP.index(f"\n  {name}:")
        block = APP[i:i + 260]
        assert "<path d=" in block
        for v in re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", block):
            assert 0 <= float(v[0]) <= 16 and 0 <= float(v[1]) <= 16, (name, v)


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
