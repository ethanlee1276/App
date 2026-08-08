"""The live situation, drawn on the art instead of beside it.

Ethan, 2026-08-08, with two screenshots and a circle drawn on the infield:
"when games are live, can we highlight what batters are on base on the
actual stadium where i circled just how we do below it. and it it looks
good maybe we can get rid of the mini bases we have and display only out
and srikes and balls at the bottom ... then we can coninue that idea onto
football by displaying what yard line the players are on along with what
down they are on that the quarter and time left."

Two halves, and they are not symmetrical.

THE BASEBALL HALF NEEDED NO NEW DATA. The park art already drew three
white squares at three fixed coordinates and the live feed already carried
which of them were occupied — `bases` has been on `LiveStatus` since the
mini diamond was written. The two halves had simply never been introduced.
The only genuinely new field is the count, which the MLB linescore has
always carried and nothing read.

THE FOOTBALL HALF NEEDED A NUMBER THAT DID NOT EXIST. `detail` carried
"2nd & 7 at DEN 45" as prose and the card printed it as prose. A drawing
needs a coordinate, and the quarter and clock Ethan asked for were already
in the LIVE badge over the art — so what this actually adds is field
position, parsed out of the spot.

WHAT IS NOT VERIFIED HERE, said plainly: `site.api.espn.com` is blocked
from the container this was written in, so no live NFL payload was ever
read. Every football assertion below runs against a synthetic payload
shaped like the one the parser has always been fed. The parse is written
to fail open for exactly that reason — an unresolvable spot draws the
field as it was drawn before any of this existed — and the first real
Sunday is the thing that confirms it.

Run directly: `python3 tests/test_live_situation.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.models import LiveStatus, live_to_dict
from engine.mlb.sources.live import parse_live
from engine.sources.livescores import parse_espn_scoreboard, spot_to_yard_line


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


VIS = _read("web", "js", "visuals.js")
APP = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")


def _fn(src, name):
    """A whole JS function, brace-matched from its opening line.

    NOT a fixed window. Every string-scanning test in this repo that took
    `src[i:i+1800]` eventually read a slice that stopped in the middle of
    the thing it was asserting about, and passed for the wrong reason.

    The body brace is found by walking PAST the parameter list first.
    `function ballpark(game, opts = {})` has a brace in its signature, and
    the naive "first { after the name" matched that one and returned a
    33-character function — which then made every assertion about the body
    fail for a reason that had nothing to do with the body.
    """
    i = src.index(f"function {name}(")
    p = src.index("(", i)
    depth = 0
    for k in range(p, len(src)):
        if src[k] == "(":
            depth += 1
        elif src[k] == ")":
            depth -= 1
            if depth == 0:
                p = k
                break
    start = src.index("{", p)
    depth = 0
    for k in range(start, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"{name} is not brace-balanced")


# --- the count, which is the only new baseball data -------------------------
SCHED = {"dates": [{"games": [
    {"status": {"abstractGameState": "Live", "detailedState": "In Progress"},
     "teams": {"home": {"team": {"id": 115}, "score": 5},
               "away": {"team": {"id": 147}, "score": 3}},
     "linescore": {"currentInningOrdinal": "6th", "inningState": "Top",
                   "outs": 1, "balls": 3, "strikes": 2,
                   "offense": {"first": {"id": 1}, "third": {"id": 3}}}},
    {"status": {"abstractGameState": "Final"},
     "teams": {"home": {"team": {"id": 112}, "score": 2},
               "away": {"team": {"id": 143}, "score": 4}},
     "linescore": {"balls": 3, "strikes": 2, "outs": 2}},
]}]}


def test_the_count_is_parsed_from_the_linescore():
    board = parse_live(SCHED)
    live = [v for v in board.values() if v.state == "live"][0]
    assert live.balls == 3 and live.strikes == 2


def test_a_finished_game_has_no_count():
    """The linescore keeps its last values after the final out. Rendered,
    that is a card reading "3-2, 2 outs" under the word FINAL — a game
    still in progress, forever."""
    board = parse_live(SCHED)
    fin = [v for v in board.values() if v.state == "final"][0]
    assert fin.balls is None and fin.strikes is None and fin.outs is None


def test_the_count_reaches_the_page():
    """A field parsed and not serialized is a field that does not exist as
    far as the site is concerned."""
    d = live_to_dict(LiveStatus(state="live", balls=1, strikes=2, outs=0))
    assert d["balls"] == 1 and d["strikes"] == 2


# --- the runners, on the art ------------------------------------------------
def test_the_park_art_reads_the_live_bases():
    body = _fn(VIS, "ballpark")
    assert "lv.bases" in body
    assert 'lv.state === "live"' in body, "runners would light on a final"


def test_the_three_bases_are_drawn_at_the_coordinates_the_art_already_used():
    """The bases were three hardcoded rects. Lighting them meant replacing
    them with a loop, and a loop is where a coordinate quietly moves.

    First base is the RIGHT one and third is the LEFT one, on an aerial
    view with home plate at the bottom. Swapping them draws a runner on
    the wrong corner of a diamond that otherwise looks perfectly correct,
    which is the kind of wrong nobody reports and everybody half-notices.
    """
    body = _fn(VIS, "ballpark")
    m = re.search(r"\[\[96, 100, (\d)\], \[120, 76, (\d)\], \[144, 100, (\d)\]\]", body)
    assert m, "the base coordinate table is gone or reshaped"
    assert m.group(1) == "3", "the LEFT base is not third"
    assert m.group(2) == "2", "the TOP base is not second"
    assert m.group(3) == "1", "the RIGHT base is not first"


def test_an_occupied_base_differs_by_more_than_a_fill():
    """Gold on tan dirt at 6px is a colour difference the size of a grain
    of rice. The dark disc behind it is what makes it read."""
    body = _fn(VIS, "ballpark")
    assert "feDropShadow" in body
    assert 'fill="#0c1020" opacity="0.55"' in body, "no disc behind the base"


def _spec(sel):
    """(ids, classes, elements) for a plain selector. Enough for this
    stylesheet, which uses no attribute selectors or :where()."""
    ids = sel.count("#")
    classes = sel.count(".") + sel.count(":")
    elements = len([t for t in re.split(r"[\s>+~]+", sel.strip())
                    if re.match(r"^[a-zA-Z]", t)])
    return (ids, classes, elements)


def test_the_stylesheet_does_not_erase_the_thing_the_markup_draws():
    """THE BUG THIS CAUGHT, in Chromium, after the first version shipped
    green in every test.

    `.stadium g rect { fill: none }` is a deliberate Night Form rule — it
    hollows the plaques on the art. It also matches the bases, and a
    presentation attribute loses to ANY CSS selector, so the occupied base
    rendered with `getComputedStyle(rect).fill === "none"` while
    `fill="#ffd24a"` sat in the markup two feet away.

    The node assertions below all passed while the browser drew nothing,
    because they counted a string I had typed. This one checks the only
    thing that actually decides the pixel: which rule wins.
    """
    hollow = re.search(r"(\.stadium g rect)\s*\{([^}]*)\}", CSS)
    assert hollow and "fill: none" in hollow.group(2), \
        "the hollowing rule changed shape — re-check what it now matches"
    lit = re.search(r"(\.stadium g rect\.on-base)\s*\{([^}]*)\}", CSS)
    assert lit, "nothing restores the fill on an occupied base"
    assert "#ffd24a" in lit.group(2)
    assert _spec(lit.group(1)) > _spec(hollow.group(1)), \
        "the occupied base does not out-specify the rule that blanks it"
    assert CSS.index(lit.group(0)) > CSS.index(hollow.group(0)), \
        "and it must come after, so a specificity tie still resolves right"


def test_the_lit_base_carries_the_class_the_stylesheet_needs():
    """A rule that nothing matches is not a fix."""
    body = _fn(VIS, "ballpark")
    assert 'class="on-base"' in body


def test_the_base_state_is_said_in_words_for_a_screen_reader():
    """The mini diamond carried aria-label="base state" and it is gone.
    Deleting the only text version of a fact while moving the picture is
    the accessible-regression shape."""
    assert 'aria-label="${escapeAttr(runnerLabel(runners))}"' in VIS
    body = _fn(VIS, "runnerLabel")
    assert "bases loaded" in body
    for word in ("first", "second", "third"):
        assert word in VIS


# --- the mini diamond is gone, and gone means gone --------------------------
def test_the_mini_diamond_is_not_left_behind():
    """Ethan asked for it removed once the bases moved onto the art. A
    dead render function that nothing calls is how the next person
    reintroduces the duplicate."""
    for src, name in ((VIS, "visuals.js"), (APP, "app.js")):
        assert "baseDiamond" not in src, f"baseDiamond survives in {name}"
    assert ".basediamond" not in CSS


def test_the_footer_shows_the_count_and_the_outs():
    i = APP.index("if (isLive && mlb) {")
    body = APP[i:APP.index("} else if", i)]
    assert "countStrip(live)" in body
    assert "bases" not in body, "the footer is still repeating the runners"


def test_the_count_strip_fails_open_when_the_feed_is_thin():
    """`balls`/`strikes` are newer than every slate JSON already on disk,
    and newer than any cached payload. Rendering "null-null" on those is
    worse than the line it replaced."""
    body = _fn(VIS, "countStrip")
    assert "b == null || s == null" in body
    # And the outs survive that branch — they are the part that always
    # existed and the part the footer said before any of this.
    assert body.index("b == null || s == null") < body.index("count-label")


# --- football: the spot -----------------------------------------------------
def test_the_home_side_of_the_field_is_the_yard_it_says():
    assert spot_to_yard_line("2nd & 7 at KC 30", "KC", "BUF") == 30.0


def test_the_away_side_is_measured_from_the_other_goal_line():
    """THE ONE THAT IS EASY TO GET BACKWARDS, and the reason the parse
    reads the prose rather than ESPN's numeric yardLine at all. "BUF 38"
    with Buffalo away is 62 yards from the Kansas City goal line, not 38.
    Read the wrong way it draws the ball on the opposite forty — which is
    not a rounding error on a picture, it is the other team driving."""
    assert spot_to_yard_line("2nd & 6 at BUF 38", "KC", "BUF") == 62.0


def test_midfield_resolves_without_belonging_to_anyone():
    """ESPN writes "MID 50" rather than naming a side, and 50 is the one
    yard number that does not need one."""
    assert spot_to_yard_line("1st & 10 at MID 50", "KC", "BUF") == 50.0


def test_a_third_team_is_not_a_spot():
    """College feeds use school codes this module has never mapped, and
    the same parser is pointed at them. An unrecognised side must not be
    silently treated as one of the two teams playing."""
    assert spot_to_yard_line("3rd & 12 at OSU 22", "KC", "BUF") is None


def test_a_yard_number_that_cannot_exist_is_refused():
    """Yards run 1-50 from either side. A 60 is a misparse, and a misparse
    that returns a number is drawn."""
    assert spot_to_yard_line("BUF 60", "KC", "BUF") is None
    assert spot_to_yard_line("", "KC", "BUF") is None


def test_the_abbreviation_map_applies_to_the_spot_too():
    """ESPN says WSH and the rest of this codebase says WAS. The team keys
    are already mapped; a spot that is not would never match its own
    game's home team, and every Washington drive would draw nothing."""
    assert spot_to_yard_line("at WSH 20", "WAS", "DAL") == 20.0


ESPN_LIVE = {"events": [
    {"date": "2026-09-13T21:00Z",
     "status": {"type": {"state": "in"}, "period": 3, "displayClock": "8:42"},
     "competitions": [{"competitors": [
         {"homeAway": "home", "team": {"abbreviation": "KC", "id": "12"}, "score": "17"},
         {"homeAway": "away", "team": {"abbreviation": "BUF", "id": "2"}, "score": "14"}],
         "situation": {"downDistanceText": "2nd & 6 at BUF 38",
                       "possessionText": "BUF 38", "possession": "2"}}]},
    {"status": {"type": {"state": "post", "shortDetail": "Final"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "team": {"abbreviation": "WSH", "id": "28"}, "score": "20"},
         {"homeAway": "away", "team": {"abbreviation": "DAL", "id": "6"}, "score": "27"}],
         "situation": {"downDistanceText": "1st & 10 at DAL 25", "possession": "6"}}]},
]}


def test_the_scoreboard_carries_the_spot_and_who_has_the_ball():
    board = parse_espn_scoreboard(ESPN_LIVE)
    live = board[frozenset(("KC", "BUF"))]
    assert live.yard_line == 62.0
    assert live.possession == "BUF"


def test_possession_is_resolved_from_the_team_id_not_assumed():
    """`situation.possession` is a numeric team id, not an abbreviation.
    Used raw it would never equal either team name and the drive arrow
    would never draw."""
    board = parse_espn_scoreboard(ESPN_LIVE)
    assert board[frozenset(("KC", "BUF"))].possession == "BUF"
    src = _read("engine", "sources", "livescores.py")
    assert "by_id.get(str(sit.get(\"possession\", \"\")), \"\")" in src


def test_a_finished_game_carries_no_drive():
    """ESPN leaves the last situation block on a game that ended an hour
    ago. Drawn, that is a live drive on a final score."""
    board = parse_espn_scoreboard(ESPN_LIVE)
    fin = board[frozenset(("WAS", "DAL"))]
    assert fin.yard_line is None and fin.possession == ""


def test_a_payload_with_no_situation_still_parses():
    """Every scheduled game, and any live game between snaps, has no
    situation block at all."""
    bare = {"events": [{"status": {"type": {"state": "in"}, "period": 1},
                        "competitions": [{"competitors": [
                            {"homeAway": "home", "team": {"abbreviation": "KC"}, "score": "0"},
                            {"homeAway": "away", "team": {"abbreviation": "BUF"}, "score": "0"}]}]}]}
    live = parse_espn_scoreboard(bare)[frozenset(("KC", "BUF"))]
    assert live.yard_line is None and live.possession == ""


def test_the_spot_reaches_the_page():
    d = live_to_dict(LiveStatus(state="live", yard_line=62.0, possession="BUF"))
    assert d["yard_line"] == 62.0 and d["possession"] == "BUF"


def test_a_slate_json_written_before_this_still_loads():
    """`data_loader` builds LiveStatus with **kwargs straight off the JSON.
    Every payload on disk predates these fields; they must be optional."""
    LiveStatus(**{"state": "live", "home_score": 3, "away_score": 0,
                  "period": "Q1", "clock": "9:11", "detail": "",
                  "start_time": "", "outs": None, "bases": None})


# --- football: the drawing --------------------------------------------------
def test_the_ball_marker_is_pinned_to_the_field_the_art_actually_draws():
    """THE ARITHMETIC, asserted against the art rather than restated.

    The field rect starts at x=52 and each end zone is 18 wide, so the
    goal line is at 70 and the field is exactly 100 units between them —
    which is why the spot is `70 + yard` with no scale factor. Move the
    field art and this stops being true silently: the ball would still be
    drawn, just consistently wrong by however far the field moved.
    """
    body = _fn(VIS, "stadium")
    fx = int(re.search(r'<rect x="(\d+)" y="50" width="136" height="60" rx="6" fill="\$\{grass\}"', body).group(1))
    ez = int(re.search(r'<rect x="52" y="50" width="(\d+)" height="60" rx="6" fill="\$\{home\.primary\}"', body).group(1))
    assert fx + ez == 70, f"the goal line moved to {fx + ez}"
    assert re.search(r"const x = 70 \+ Math\.max\(0, Math\.min\(100, yard\)\)", body)


def test_the_home_end_zone_is_the_left_one():
    """The whole convention rests on it: `yard_line` is measured from the
    home goal line because the home end zone is drawn on the left. Flip
    the art and every drive runs backwards."""
    body = _fn(VIS, "stadium")
    home_ez = body.index('fill="${home.primary}"')
    away_ez = body.index('fill="${away.primary}"')
    assert body[:home_ez].rindex('<rect x="52"') < body[:away_ez].rindex('<rect x="170"')


def test_unknown_possession_draws_the_spot_and_no_arrow():
    """Half the fact is better than a guessed direction. ESPN drops
    `possession` between drives and on any turnover it has not resolved."""
    body = _fn(VIS, "stadium")
    assert 'lv.possession === game.away ? -1 : lv.possession === game.home ? 1 : 0' in body
    assert "dir &&" in body


def test_the_drive_is_drawn_after_the_dome():
    """A closed roof lays an 0.8-opacity ellipse over the entire field. A
    ball spot drawn before it is dimmer indoors than out, on the eight
    stadiums where the game is most likely to still be close."""
    body = _fn(VIS, "stadium")
    assert body.index("${roofOverlay}") < body.index("${drive}")


def test_the_football_art_ignores_a_yard_line_on_a_dead_game():
    body = _fn(VIS, "stadium")
    assert 'lv.state === "live" && lv.yard_line != null' in body


# --- behaviour, actually executed -------------------------------------------
_HARNESS = r"""
const fs = require("fs");
global.window = {};
global.document = { addEventListener(){}, querySelectorAll: () => [],
  createElement: () => ({ style:{}, classList:{add(){},remove(){}} }),
  body: { appendChild(){} } };
eval(fs.readFileSync(process.argv[2], "utf8"));
const out = [];
const park = (live) => ballpark({ home: "NYY", away: "BOS", live });
const litBases = (svg) => (svg.match(/fill="#ffd24a"/g) || []).length;
const drawn = (svg) => (svg.match(/transform="rotate\(45 \d+ \d+\)"/g) || []).length;
out.push(["empty",      litBases(park({ state: "live", bases: [] })),      drawn(park({ state: "live", bases: [] }))]);
out.push(["corners",    litBases(park({ state: "live", bases: [1, 3] })),  drawn(park({ state: "live", bases: [1, 3] }))]);
out.push(["loaded",     litBases(park({ state: "live", bases: [1, 2, 3] })), drawn(park({ state: "live", bases: [1,2,3] }))]);
out.push(["final",      litBases(park({ state: "final", bases: [1, 2] })), drawn(park({ state: "final", bases: [1,2] }))]);
out.push(["none",       litBases(park(undefined)),                          drawn(park(undefined))]);

const field = (live) => stadium({ home: "KC", away: "BUF", live });
const spotX = (svg) => {
  const m = svg.match(/<line x1="([\d.]+)" y1="50" x2="[\d.]+" y2="110" stroke="#ffd24a"/);
  return m ? Number(m[1]) : null;
};
const arrows = (svg) => (svg.match(/<path d="M[\d.]+ 55/g) || []).length;
out.push(["kc-own-30", spotX(field({ state: "live", yard_line: 30, possession: "KC" })),
                        arrows(field({ state: "live", yard_line: 30, possession: "KC" }))]);
out.push(["buf-45",    spotX(field({ state: "live", yard_line: 55, possession: "BUF" })),
                        arrows(field({ state: "live", yard_line: 55, possession: "BUF" }))]);
out.push(["midfield",  spotX(field({ state: "live", yard_line: 50, possession: "" })),
                        arrows(field({ state: "live", yard_line: 50, possession: "" }))]);
out.push(["goal",      spotX(field({ state: "live", yard_line: 99, possession: "KC" })),
                        arrows(field({ state: "live", yard_line: 99, possession: "KC" }))]);
out.push(["dead",      spotX(field({ state: "final", yard_line: 40, possession: "KC" })), 0]);

out.push(["count", countStrip({ state: "live", outs: 1, balls: 3, strikes: 2 }).includes("3<i>–</i>2") ? 1 : 0,
                    countStrip({ state: "live", outs: 1 }).includes("<i>–</i>") ? 1 : 0]);
out.push(["outs",  countStrip({ state: "live", outs: 1 }).includes("1 out<") ? 1 : 0,
                    countStrip({ state: "live", outs: 2 }).includes("2 outs") ? 1 : 0]);
out.push(["label", runnerLabel(new Set([1, 3])) === "Ballpark — runners on first and third" ? 1 : 0,
                    runnerLabel(new Set()) === "Ballpark" ? 1 : 0]);
console.log(JSON.stringify(out));
"""


def _run_js():
    node = shutil.which("node")
    assert node, ("node is not on PATH — these are the only assertions here "
                  "that RUN the renderer rather than read it, so a silent "
                  "skip would leave the behaviour untested")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_HARNESS)
        path = fh.name
    try:
        res = subprocess.run([node, path, os.path.join(ROOT, "web", "js", "visuals.js")],
                             capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return {r[0]: r[1:] for r in json.loads(res.stdout)}


def test_the_renderer_lights_exactly_the_occupied_bases():
    r = _run_js()
    assert r["empty"] == [0, 3]
    assert r["corners"] == [2, 3]
    assert r["loaded"] == [3, 3]


def test_the_renderer_never_lights_a_base_on_a_dead_game():
    """The bases stay drawn — an unlit diamond is part of the art. What
    must not survive is the gold."""
    r = _run_js()
    assert r["final"] == [0, 3]
    assert r["none"] == [0, 3]


def test_the_renderer_puts_the_ball_where_the_arithmetic_says():
    r = _run_js()
    assert r["kc-own-30"] == [100, 1]       # 70 + 30
    assert r["buf-45"] == [125, 1]          # 70 + (100 - 45)
    assert r["midfield"] == [120, 0]        # no possession, no arrow
    assert r["dead"][0] is None


def test_the_arrow_is_dropped_at_the_goal_line_rather_than_pinned():
    """Seven pixels downfield of the 1 is past the back of the end zone.
    Clamped, the arrowhead would sit on the goal line and read as a second
    spot."""
    r = _run_js()
    assert r["goal"] == [169, 0]


def test_the_strip_renders_a_count_and_survives_without_one():
    r = _run_js()
    assert r["count"] == [1, 0], "count missing, or a dash drawn with no count"
    assert r["outs"] == [1, 1], "outs is not pluralised"


def test_the_spoken_base_state_is_english():
    r = _run_js()
    assert r["label"] == [1, 1]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
