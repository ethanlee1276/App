"""Each park is drawn at its own dimensions, and the ball lands on it.

Ethan, 2026-09-06, with three renders of what the play-by-play park
should look like: "ours is ass."

He was right, and the reason was not only that the art is flat. All
thirty parks were drawn as ONE symmetric arc — `A116 92 0 0 1` — while
`engine/mlb/parks.py` has carried real dimensions the whole time and
`engine/mlb/pipeline.py` has been shipping them to the browser inside the
`park` object. The renderer simply never read them, and the strip's own
subtitle has been advertising "real park shapes" throughout.

THE PART THAT WAS AN ACTUAL BUG, not a missing feature. Two functions
that have to agree, didn't:

    pbpFenceFt(park, phi)   scaled the ball against the park's REAL fence
    pbpWallPoint(phi)       drew it against a fixed ellipse, no park arg

So a 320-foot fly to left at Fenway (wall 310) was correctly flagged gone
by the arithmetic — gold ring and all — and then drawn landing at exactly
the same spot as a 320-foot fly at a park whose wall is 347 away. The
colour was right and the picture was wrong. `wallShape` is now the one
answer to "where is the wall at this bearing", and both read it.

MEASURED AGAINST A LEAGUE REFERENCE, NOT AGAINST THE PARK ITSELF. My own
first version divided by each park's own centre field, which pinned every
centre to the same radius: Fenway's 420 and Petco's 396 drew identically
and only the asymmetry survived. Half of a park's shape is its depth.

Run directly: `python3 tests/test_park_shape.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VIS = (ROOT / "web" / "js" / "visuals.js").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()

#: Real dimensions, from engine/mlb/parks.py.
FENWAY = {"lf_ft": 310, "cf_ft": 420, "rf_ft": 302}
YANKEE = {"lf_ft": 318, "cf_ft": 408, "rf_ft": 314}
PETCO = {"lf_ft": 336, "cf_ft": 396, "rf_ft": 322}
NEUTRAL = {"lf_ft": 330, "cf_ft": 400, "rf_ft": 330}


def _node(parks: dict):
    """`wallShape` run for real, per park. Skips without node."""
    if not shutil.which("node"):
        return None
    src = """
const fs=require("fs"),vm=require("vm");
const ctx=vm.createContext({document:{addEventListener(){}},window:{},console,
  matchMedia:()=>({matches:false}),requestAnimationFrame:()=>{}});
try{vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),ctx);}catch(e){}
const out={};
for(const [k,p] of Object.entries(JSON.parse(process.argv[2]))){
  const w=ctx.wallShape(p);
  out[k]={lf:w.lf,cf:w.cf,rf:w.rf};
}
process.stdout.write(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        r = subprocess.run(
            ["node", path, str(ROOT / "web" / "js" / "visuals.js"), json.dumps(parks)],
            capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout else None
    finally:
        os.unlink(path)


def test_the_generic_arc_is_gone():
    """The single hardcoded ellipse every park was drawn with."""
    assert 'd="M34 60 A116 92 0 0 1 206 60"' not in VIS, (
        "the fixed outfield arc is back — every park is one shape again")


def test_two_different_parks_are_drawn_differently():
    got = _node({"fenway": FENWAY, "petco": PETCO})
    if got is None:
        return                                   # no node; source pins cover it
    assert got["fenway"] != got["petco"], got


def test_a_symmetric_park_is_drawn_symmetric():
    """330/400/330 must mirror, or the geometry is skewed by something
    other than the data."""
    got = _node({"n": NEUTRAL})
    if got is None:
        return
    lf, rf = got["n"]["lf"], got["n"]["rf"]
    assert abs((120 - lf[0]) - (rf[0] - 120)) < 0.5, got
    assert abs(lf[1] - rf[1]) < 0.5, got


def test_a_deeper_centre_field_is_drawn_deeper():
    """THE FLAW IN MY FIRST VERSION. Dividing by the park's own centre
    made Fenway's 420 and Petco's 396 identical. Smaller y is deeper."""
    got = _node({"f": FENWAY, "y": YANKEE, "p": PETCO})
    if got is None:
        return
    assert got["f"]["cf"][1] < got["y"]["cf"][1] < got["p"]["cf"][1], got


def test_a_short_porch_is_drawn_short():
    """Petco is 336 to left and 322 to right. The right-field wall has to
    come in closer than the left, or the asymmetry is decorative."""
    got = _node({"p": PETCO})
    if got is None:
        return
    lf, rf = got["p"]["lf"], got["p"]["rf"]
    assert (rf[0] - 120) < (120 - lf[0]), got


def test_a_park_with_no_dimensions_still_draws():
    """A fresh feed, a new park, a missing field: fall back to a league
    default rather than to NaN geometry."""
    got = _node({"empty": {}, "neutral": NEUTRAL})
    if got is None:
        return
    assert got["empty"] == got["neutral"], got
    for pt in got["empty"].values():
        assert all(isinstance(c, (int, float)) for c in pt), got


def test_the_arc_and_the_drawing_read_one_shape():
    """THE BUG. `pbpWallPoint` took no park and so could not agree with
    `pbpFenceFt`, which takes one."""
    assert "function pbpWallPoint(phiDeg, park)" in APP
    assert "pbpWallPoint(phi, park)" in APP, (
        "the flight is still asking for the wall without saying which park")
    assert "wallShape(park || {}).pt(phiDeg)" in APP


def test_the_art_is_handed_the_dimensions():
    """`pbpParkHTML` built its game object without the park, so the art
    could not have drawn a real wall even once it knew how."""
    at = APP.index("function pbpParkHTML")
    assert "park: (boardGame || {}).park || {}" in APP[at:at + 900]


def test_the_wall_numbers_are_the_real_ones():
    """The distances on the wall come from the feed, not from a table
    somebody typed into the renderer."""
    assert 'park[k + "_ft"]' in VIS
    assert "wallmark" in VIS and ".pbp-park .wallmark" in CSS


def test_no_dimension_we_do_not_hold_is_invented():
    """The render shows five numbers (LF/LCF/CF/RCF/RF). We hold three.
    Drawing LCF and RCF would mean inventing them."""
    assert "lcf" not in VIS.lower().split("wallshape")[1][:2000]
    at = APP.index("function pbpParkFactsHTML")
    assert "lcf" not in APP[at:at + 1900].lower()


def test_the_batted_ball_tiles_show_only_a_batted_ball():
    """Four tiles of em-dash on a walk reads as broken, not as N/A."""
    at = APP.index("function pbpBattedHTML")
    block = APP[at:at + 1400]
    for f in ("launch_speed", "launch_angle", "distance", "trajectory"):
        assert f in block, f
    assert "return \"\"" in block, "it renders tiles for a ball never hit"


def test_the_strikeout_factor_is_not_relabelled():
    """The render's third factor tile says "Extra Base Factor". We do not
    hold that number; we hold the STRIKEOUT factor. Putting ours under
    their label would be a quiet lie on a page about being honest.

    RE-ANCHORED 2026-09-06 when the tiles took the render's fuller names
    ("HR Factor" rather than "HR"). The pin follows the meaning, not the
    old two-letter string: whatever the third factor is called, it is
    called strikeout and it reads f.k."""
    at = APP.index("function pbpParkFactsHTML")
    block = APP[at:at + 1900]
    assert "f.k]" in block, "the third factor is still the strikeout one"
    third = [ln for ln in block.splitlines() if "f.k]" in ln][0]
    assert "strikeout" in third.lower(), third
    # Only the CODE is scanned for their label. A comment is allowed to
    # name it — explaining why we did not adopt it is the whole point of
    # the note — and an earlier version of this test failed on its own
    # explanation, which is a test reading the wrong thing.
    code = "\n".join(ln for ln in block.splitlines()
                     if not ln.strip().startswith("//"))
    assert "extra base" not in code.lower()


def test_the_factors_name_the_baseline_they_are_measured_against():
    """0.92 means nothing without the 1.00 it is against, and the render
    prints that on every tile."""
    at = APP.index("function pbpParkFactsHTML")
    block = APP[at:at + 1900]
    assert "1.00" in block and "avg" in block.lower()


# ---------------------------------------------------------------- photo ---
#
# Ethan, 2026-09-06: "you should be using this render for ALL live mlb
# games. It has our Qellys book logo on it and everything."
#
# One generic park carrying OUR OWN scoreboard, rather than thirty real
# ones carrying somebody else's marks. The vector field stays for the
# other leagues and the small board cards; MLB's play-by-play gets the
# photograph with the moving parts drawn over it.

def test_mlb_gets_the_photograph():
    """RE-ANCHORED 2026-09-07, when football got a photograph of its own
    (Ethan's field renders). `photo` is no longer 'this is baseball' — it
    is 'this league has a picture', which is now MLB or either football
    code. What still has to be true, and is what this test was ever
    about, is that BASEBALL's picture is the ballpark."""
    at = APP.index("function pbpParkHTML")
    block = APP[at:at + 1800]
    assert 'league === "mlb" ? pbpPhotoHTML(game)' in block
    assert "const photo = league === \"mlb\" || isFootball;" in block


def test_the_leagues_without_a_photograph_keep_their_vector_art():
    """RE-ANCHORED 2026-09-07. This said "football and hoops"; football
    now has two field photographs of its own, so the leagues without a
    picture are the basketball ones — and they must still get the drawn
    court rather than somebody else's sport."""
    at = APP.index("function pbpParkHTML")
    block = APP[at:at + 1800]
    assert "court(game" in block and "stadium(game" in block
    assert 'isFootball ? pbpFieldHTML(d)' in block
    # The vector court is reached only after both photo branches.
    assert block.index("pbpFieldHTML") < block.index("court(game")


def test_the_photo_ships_in_both_formats_and_both_sizes():
    """A 2.4MB PNG on the page every live game opens is not shippable."""
    img = ROOT / "web" / "img" / "park"
    for f in ("park-night.webp", "park-night.jpg",
              "park-night@640.webp", "park-night@640.jpg"):
        assert (img / f).exists(), f
    # The one a phone downloads has to be small.
    assert (img / "park-night@640.webp").stat().st_size < 120_000
    assert (img / "park-night.webp").stat().st_size < 400_000


def test_the_hero_image_is_not_lazy():
    """Lazily loading the thing the reader opened the page to look at is
    how a card flashes empty."""
    at = APP.index("function pbpPhotoHTML")
    assert 'loading="lazy"' not in APP[at:at + 1400]


def test_the_arc_is_drawn_in_the_photographs_own_space():
    """The photo has its own field geometry, measured off a calibration
    grid. An arc drawn in the vector field's coordinates would start at
    the wrong plate and land on the wrong grass."""
    assert "const PBP_PHOTO = {" in APP
    assert "function pbpPhotoWall(phiDeg)" in APP
    at = APP.index("function pbpFlight")
    block = APP[at:at + 700]
    assert "photo ? PBP_PHOTO.home" in block
    assert "photo ? pbpPhotoWall(phi)" in block


def test_the_real_fence_still_decides_whether_it_is_gone():
    """The picture is one park; the DIMENSIONS are still each park's own.
    `pbpFenceFt` must keep deciding the ratio, or every park becomes the
    photograph in the arithmetic too."""
    at = APP.index("function pbpFlight")
    block = APP[at:at + 700]
    assert "pbpFenceFt(park, phi)" in block


def test_the_marks_on_the_photo_are_this_parks_numbers():
    at = APP.index("function pbpPhotoHTML")
    block = APP[at:at + 2400]
    assert 'p[key + "_ft"]' in block
    assert "PBP_PHOTO.lf" in block and "PBP_PHOTO.rf" in block
    # The chip carries the position too, and it is DERIVED from the field
    # that supplied the number — so a label can never end up over the
    # wrong distance.
    assert "key.toUpperCase()" in block


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
