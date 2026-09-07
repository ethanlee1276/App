"""The football field, and the play drawn on it.

Ethan, 2026-09-07, with three renders: "follow these renders for the nfl
play by play page for live games. The last 2 renders of just the field
and players will the the EXACT renders you will use for the field on the
play by play screens. The black team with represent the away team and
white will represent the home team." Then, mid-build: "this is also for
cfb as well. all this work should be for both nfl and cfb."

Two photographs of one generic stadium wearing our own branding — the
same call as the ballpark, for the same two reasons: we do not hold
thirty-two stadium photographs, and we do not want anybody else's marks
on our card. Which one draws is decided by POSSESSION, because that is
the only difference between them.

WHAT IS DELIBERATELY NOT DRAWN, and why these are tests rather than
comments:

  * His annotated render shows EXIT VELOCITY and LAUNCH ANGLE beside the
    yards. Those are Statcast numbers. Football does not have them —
    ESPN's play carries `event`, `yards`, `down`, `distance` and
    `yard_line` and nothing else. The four-up keeps its shape and is
    filled with four numbers we hold.
  * His render bows the ball out to a receiver. The feed does not say
    where across the field the ball went, so the flight runs straight
    downfield by the distance the play actually gained.
  * A play that lost yards draws no line at all: the camera model is
    fitted downfield from three measured anchors and says nothing about
    the backfield.

The camera model itself is exercised in node against the anchors it was
fitted to, which were read off a 240x150 grid laid over the render.
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
    src = "\n".join([
        "function escapeHtml(s){return String(s);}",
        "function icon(){return '';}",
        _const("pbpOrd"), _const("PBP_FIELD"), _const("PBP_PLAY_HUE"),
        _fn("pbpFieldY"), _fn("pbpFieldHTML"), _fn("pbpCalloutBox"), _fn("pbpPlaySVG"),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src + "\n" + js); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# ------------------------------------------------------------ both codes ---
def test_college_and_pro_are_one_list_not_two_wirings():
    """Every football bug in this file has been 'fixed in one league'."""
    assert 'const PBP_FOOTBALL = new Set(["nfl", "cfb"]);' in APP
    for site in ("const isFootball = PBP_FOOTBALL.has(league);",):
        assert site in APP, site
    # No league-by-name branch may decide the field art or the tiles.
    art = _fn("pbpParkHTML")
    assert '"nfl"' not in art and '"cfb"' not in art, art


# -------------------------------------------------------- which photo ------
def test_the_photo_follows_possession():
    got = _node("""
      const away = pbpFieldHTML({home: "DET", away: "CHI", live: {possession: "CHI"}});
      const home = pbpFieldHTML({home: "DET", away: "CHI", live: {possession: "DET"}});
      const none = pbpFieldHTML({home: "DET", away: "CHI", live: {}});
      const pick = (s) => (s.match(/field-(away|home)-ball/) || [])[1];
      console.log(JSON.stringify({away: pick(away), home: pick(home), none: pick(none)}));""")
    if got is None:
        print("  SKIP node not installed"); return
    # Black jerseys are the away team, and that frame draws when the away
    # team has the ball.
    assert got["away"] == "away", got
    assert got["home"] == "home", got
    # Unknown possession is a real state; it falls back rather than
    # asserting a side.
    assert got["none"] == "home", got


def test_both_frames_ship_in_both_formats_and_both_sizes():
    img = ROOT / "web" / "img" / "field"
    for stem in ("field-away-ball", "field-home-ball"):
        for suf in (".webp", ".jpg", "@640.webp", "@640.jpg"):
            assert (img / f"{stem}{suf}").exists(), stem + suf
        # The one a phone downloads has to be small, same budget as the park.
        assert (img / f"{stem}@640.webp").stat().st_size < 120_000
        assert (img / f"{stem}.webp").stat().st_size < 400_000


# ----------------------------------------------------- the camera model ----
def test_the_field_maps_yards_the_way_the_render_was_measured():
    """The three anchors read off the grid: the line the linemen stand
    on, midfield, and the goal line."""
    got = _node("""
      const at = {};
      for (const d of [0, 5, 10, 20, 40, 70, 100]) at[d] = pbpFieldY(d);
      console.log(JSON.stringify(at));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert abs(got["0"] - 108) < 0.05, got      # line of scrimmage
    assert abs(got["20"] - 84) < 0.05, got      # midfield
    assert abs(got["70"] - 62) < 0.05, got      # the goal line
    # Monotone downfield, and compressing — a lens, not a ruler.
    ys = [got[str(d)] for d in (0, 5, 10, 20, 40, 70, 100)]
    assert all(b < a for a, b in zip(ys, ys[1:])), ys
    # Compression is a PER-YARD claim. The first version compared a
    # five-yard span against a thirty-yard one and called the model
    # broken when it was the test that was.
    near = (got["0"] - got["5"]) / 5
    far = (got["40"] - got["70"]) / 30
    assert near > far * 3, (near, far)
    # Nothing runs off the back of the picture.
    assert got["100"] >= 58 - 0.01, got


def test_a_play_that_lost_yards_draws_no_flight():
    got = _node("""
      const sack = pbpPlaySVG({kind: "football", event: "Sack", yards: -7, down: 3, distance: 15});
      const gain = pbpPlaySVG({kind: "football", event: "Rush", yards: 7, down: 1, distance: 10});
      const markY = (s) => +(s.match(/<circle cx="[\d.]+" cy="([\d.]+)"/) || [])[1];
      console.log(JSON.stringify({
        sackPath: /<path /.test(sack), gainPath: /<path /.test(gain),
        sackSaysLoss: sack.includes("7 YDS"), sackHasMark: /<circle /.test(sack),
        sackMarkY: markY(sack), gainMarkY: markY(gain), los: PBP_FIELD.los}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["gainPath"] is True
    assert got["sackPath"] is False, "the model does not describe the backfield"
    assert got["sackSaysLoss"] and got["sackHasMark"], "but the play is still reported"
    # AND the mark stays on the line. Taking the absolute value would put
    # a seven-yard LOSS seven yards downfield, which is the same picture
    # as a seven-yard gain — a mutant that survived the first version of
    # this test because it only looked for the line, not for where the
    # ball ended up.
    assert got["sackMarkY"] == got["los"], got
    assert got["gainMarkY"] < got["los"], got


def test_the_flight_runs_straight_downfield():
    """Bowing it to one side would invent the one number the feed does
    not carry — where across the field the ball went."""
    got = _node("""
      const svg = pbpPlaySVG({kind: "football", event: "Pass", yards: 22});
      const m = svg.match(/d="M([\\d.]+) ([\\d.]+) L([\\d.]+) ([\\d.]+)"/);
      console.log(JSON.stringify({x0: +m[1], y0: +m[2], x1: +m[3], y1: +m[4]}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["x0"] == got["x1"], got
    assert got["y1"] < got["y0"], "downfield is up the picture"
    body = _fn("pbpPlaySVG")
    assert " Q" not in body.split("return")[1], "no quadratic — no invented curve"


# ------------------------------------------------------------- the tiles ---
def test_the_tiles_carry_only_numbers_football_actually_has():
    body = _fn("pbpPlayTilesHTML")
    for real in ("p.yards", "p.event", "p.down", "p.distance", "p.yard_line"):
        assert real in body, real
    code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("//"))
    for invented in ("launch_speed", "launch_angle", "EXIT VELOCITY", "LAUNCH ANGLE"):
        assert invented not in code, invented


def test_every_football_tile_wears_a_mark_the_site_draws_itself():
    body = _fn("pbpPlayTilesHTML")
    names = re.findall(r'tile\("([a-z]+)"', body)
    assert len(names) == 4, names
    assert "glove" not in names, "a baseball glove is not a football mark"
    for n in names:
        assert f"\n  {n}:" in APP, f"{n} is not in ICON_PATHS"


def test_the_wind_word_tells_the_two_leagues_fields_apart():
    """Baseball ships the wind's relation to the park; football ships a
    compass bearing. Both are real, neither is the other, and anything
    that is neither prints nothing."""
    body = _fn("pbpWindWord")
    assert "PBP_WIND" in body and "[NSEW]" in body
    head = _fn("pbpParkHeadHTML")
    assert "isFootball ? g.stadium : g.park" in head, "each league's own venue field"
    assert '"THE FIELD" : "THE PARK"' in head


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
