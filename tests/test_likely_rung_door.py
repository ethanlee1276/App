"""A Most Likely prop opened the search page instead of the prop page.

Ethan, 2026-09-10: "When u click on props from the edge board is pulls up
a bunch of stats and sims to run and all this data but when you click on
props from the most likely, it pulls up the search page with the player
on there. We need to fix that where it shows all the data is shows when
you click on the edge bets but also for the most likely bets."

THE CAUSE IS THE LADDER, and it arrived quietly. Both doors resolved a
row with `findProp(propId(r))` — `player|market|side|line` — and fell
back to the player page when that missed. Since the alternate-line
ladders shipped (2026-09-07) a likelihood row's `line` is frequently a
RUNG's line: the same stat at a lower number, bought separately because
that is where "most likely" is actually for sale. No rung is on the props
board, so the exact lookup could never match, and the fallback did
exactly what it was written to do — opened the player page, which is the
search surface Ethan was landing on.

Nothing announced it. The door still worked, it still went somewhere
reasonable, and the better the ladder worked the more of the board went
through the wrong door.

The row already carried the bridge: `likely._row` stamps `rung` as "main"
or "alt" and keeps `main_line`/`main_side` beside the rung's own numbers,
so the card can say what the rung stands next to. `likelyProp` reads it.

WHAT AN ALT RUNG OPENS is the main line's page, and that is the answer
rather than a compromise — the rung's own page does not exist, nothing on
the board carries that line, and the analysis the page draws is per
player and market rather than per line. Bar graph, logs, form, game
script and versus are the same evaluation either way.

Run in node against the real functions, because the failure was
behavioural: every source-level pin this file's neighbour carries still
passed while the board went to the wrong page.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

FNS = ("propId", "propOpenable", "findProp", "likelyProp",
       "likelyOpenableProp", "likelyDoor", "likelyOpen")

#: The prop as the edge board carries it — the main line, with history.
MAIN = {"player": "Jaxon Smith-Njigba", "market": "rec_yds", "side": "OVER",
        "line": 65.5, "recent_values": [70, 55, 80, 62]}

#: The likelihood row cut from it at a RUNG: a lower line, bought
#: separately, with the main line kept beside it.
RUNG = {"kind": "prop", "player": "Jaxon Smith-Njigba", "market": "rec_yds",
        "side": "OVER", "line": 49.5, "rung": "alt",
        "main_line": 65.5, "main_side": "OVER",
        "recent_values": [70, 55, 80, 62]}

#: The same row taken straight off the main line.
ROW = dict(RUNG, line=65.5, rung="main")


def _run(props, row, call="likelyDoor"):
    """Call one door against a board holding exactly `props`."""
    node = shutil.which("node")
    if not node:
        return None
    src = []
    for name in FNS:
        i = APP.index(f"function {name}(")
        src.append(APP[i:APP.index("\n}", i) + 2])
    prog = """
      var escapeAttr = (s) => String(s == null ? "" : s);
      var PROPS = %s;
      var allProps = () => PROPS;
      var pickSlug = () => "";
      var slugify = (s) => String(s).toLowerCase().split(" ").join("-");
      var gameBetAttrs = () => " GAME-DOOR";
      var gameBetOpenable = () => true;
      var gameBetId = () => "gid";
      %s
      console.log(JSON.stringify(%s(%s)));
    """ % (json.dumps(props), "\n".join(src), call, json.dumps(row))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True,
                             timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# --- the bug ----------------------------------------------------------------
def test_a_rung_row_opens_the_prop_it_stands_next_to():
    """The whole report, in one assertion. Before this the rung's own
    line was looked up, missed, and the reader got the player page."""
    got = _run([MAIN], RUNG)
    if got is None:
        return
    assert "data-prop=" in got, f"a rung still opens the player page: {got}"
    assert "Jaxon Smith-Njigba|rec_yds|OVER|65.5" in got, got
    assert "data-player-page" not in got


def test_the_same_is_true_of_the_shelf_row():
    """`likelyOpen` is the list version of the same door and drifted
    with it."""
    got = _run([MAIN], RUNG, call="likelyOpen")
    if got is None:
        return
    assert got.strip() == 'data-open="prop:Jaxon Smith-Njigba|rec_yds|OVER|65.5"', got


def test_a_main_line_row_was_never_broken_and_still_is_not():
    got = _run([MAIN], ROW)
    if got is None:
        return
    assert "data-prop=" in got and "|65.5" in got


# --- what it still refuses --------------------------------------------------
def test_a_rung_whose_main_line_is_not_on_the_board_takes_the_player_page():
    """The fallback is correct here — there is no prop page to open."""
    got = _run([], RUNG)
    if got is None:
        return
    assert "data-player-page=" in got and "data-prop=" not in got


def test_a_row_that_is_not_a_rung_does_not_go_hunting():
    """`rung` is the licence to look at `main_line`. Without it a row
    with a stale line must not quietly open some other number."""
    stray = dict(RUNG, rung="main", line=49.5)
    got = _run([MAIN], stray)
    if got is None:
        return
    assert "data-player-page=" in got, got


def test_a_prop_with_no_history_is_not_a_door_even_when_it_is_found():
    """`propOpenable` is asked of the PROP, because the prop is what the
    page draws. Asked of the likelihood row instead, its own field set
    decided whether a page it does not render was worth opening."""
    thin = dict(MAIN, recent_values=[70])
    got = _run([thin], RUNG)
    if got is None:
        return
    assert "data-player-page=" in got and "data-prop=" not in got


def test_the_openable_test_reads_the_prop_not_the_row():
    """Source-level, because the behavioural case above can only show
    the two disagreeing when their histories differ."""
    i = APP.index("function likelyOpenableProp(")
    body = APP[i:APP.index("\n}", i)]
    assert "propOpenable(t)" in body and "propOpenable(r)" not in body


# --- the neighbours are untouched -------------------------------------------
def test_a_game_row_still_goes_through_the_game_door():
    got = _run([], {"kind": "game", "home": "SEA", "away": "NE"})
    if got is None:
        return
    assert got == " GAME-DOOR"


def test_a_row_with_no_player_is_not_a_door():
    for call in ("likelyDoor", "likelyOpen"):
        got = _run([MAIN], {"kind": "prop", "player": ""}, call=call)
        if got is None:
            return
        assert got == "", f"{call} drew a door onto nothing"


def test_both_doors_resolve_through_the_one_function():
    """They disagreed once already — the card opened a prop the shelf row
    sent to the player page — and this is what stops it happening in the
    other direction."""
    for name in ("likelyDoor", "likelyOpen"):
        i = APP.index(f"function {name}(")
        body = APP[i:APP.index("\n}", i)]
        assert "likelyOpenableProp(r)" in body, f"{name} resolves its own way"
        assert "findProp(" not in body, f"{name} still looks a prop up itself"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
