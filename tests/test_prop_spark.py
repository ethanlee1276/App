"""The last ten games, beside the bet — and coloured for the BET.

Ethan, 2026-08-25, with a screenshot of the Edge board: "Our props
displayed in the recommended section should have this same little chart
like this next too the bet. The chart should Correlate to the prop being
displayed obviously."

TWO THINGS, and the second one was hiding in his screenshot.

The placement. A Recommended card already carried the full propAnalysis
chart — axes, per-game values, opponents, a legend — but it sits below
the projection bar, three metrics and the confidence meter, which on a
390px screen is most of a scroll away from the pick it describes. "Has
he been doing this lately" is asked while reading the bet, so it is now
answered there, in the same bars at a fifth the height.

The colours. The row he circled read `Lane Thomas · UNDER 1.5 Hits` with
`1/10 cleared 1.5` and exactly one green bar. `gamelogBars` coloured
`v > line` green with no idea what side the bet was on, so on an UNDER
the single green bar was the one game the bet LOST and the nine red ones
were the nine it won. In the site's own status pair. Reproduced before
changing anything:

    green bars: 1   red bars: 9   caption: "1/10 cleared 1.5"

propAnalysis has always got this right — it computes
`won = over ? v > line : v < line`. The compact version never took the
side at all. It does now, and it names the direction rather than reusing
"cleared", which reads as "went over" whatever the bet was.

THE OLD READING IS KEPT WHEN THERE IS NO SIDE. A form sparkline on a
player page is not a bet and has no side to be on; only callers that
pass one get the bet-relative colouring.

Run directly: `python3 tests/test_prop_spark.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

NODE = shutil.which("node")


def _fn(src, name):
    """The whole function, brace-matched from the BODY brace.

    Counting from the first `{` after the name lands inside `opts = {}`
    in the signature and truncates the function at its own default
    argument — which fails as a syntax error a long way from the cause.
    """
    i = src.index(f"function {name}(")
    j = src.index(") {", i) + 2
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"unbalanced braces reading {name}")


def _bars(values, opts):
    """Render gamelogBars in node and report what it drew."""
    if not NODE:
        return None
    script = _fn(VIS, "gamelogBars") + f"""
const escapeAttr = (s) => String(s);
const svg = gamelogBars({json.dumps(values)}, {json.dumps(opts)});
const txt = (svg.match(/tabular-nums">([^<]*)</) || [])[1] || "";
console.log(JSON.stringify({{
  green: svg.split("var(--good)").length - 1,
  red: svg.split("var(--bad)").length - 1,
  caption: txt,
  aria: (svg.match(/aria-label="([^"]*)"/) || [])[1] || "",
  rules: (svg.match(/stroke-dasharray/g) || []).length,
}}));
"""
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr.strip()
    return json.loads(out.stdout)


# --- the colours ----------------------------------------------------------

def test_an_under_is_green_on_the_games_it_would_have_won():
    """Ethan's row, reproduced. One game over 1.5 in ten: the UNDER won
    nine of them."""
    vals = [0, 1, 1, 0, 1, 0, 2, 1, 0, 1]
    m = _bars(vals, {"line": 1.5, "side": "UNDER", "w": 92, "h": 34})
    if m is None:
        return
    assert m["green"] == 9 and m["red"] == 1, (
        f"an UNDER is still coloured by whether the stat went over: {m}")
    assert m["caption"] == "9/10 under 1.5", m["caption"]


def test_an_over_is_unchanged():
    vals = [0, 1, 1, 0, 1, 0, 2, 1, 0, 1]
    m = _bars(vals, {"line": 1.5, "side": "OVER", "w": 92, "h": 34})
    if m is None:
        return
    assert m["green"] == 1 and m["red"] == 9, m
    assert m["caption"] == "1/10 over 1.5", m["caption"]


def test_no_side_keeps_the_old_reading():
    """A form sparkline on a player page is not a bet. Callers with no
    side still get "cleared", and still get the same colours they did."""
    vals = [0, 1, 1, 0, 1, 0, 2, 1, 0, 1]
    m = _bars(vals, {"line": 1.5, "w": 92, "h": 34})
    if m is None:
        return
    assert m["green"] == 1 and m["red"] == 9, m
    assert m["caption"] == "1/10 cleared 1.5", m["caption"]


def test_the_caption_never_says_cleared_when_it_knows_the_side():
    """"cleared 1.5" reads as "went over 1.5" whichever way the bet
    went, which is the ambiguity that let the bug hide."""
    m = _bars([0, 2, 0, 3], {"line": 1.5, "side": "UNDER", "w": 92, "h": 34})
    if m is None:
        return
    assert "cleared" not in m["caption"], m["caption"]
    assert "under" in m["caption"]


def test_the_spoken_label_says_whose_side_it_is_on():
    """The colours are ΔE 7.5 under deuteranopia and the module header
    is explicit that they can never be the only telling."""
    m = _bars([0, 2, 0, 3], {"line": 1.5, "side": "UNDER", "w": 92, "h": 34})
    if m is None:
        return
    assert "under 1.5" in m["aria"] and "this bet" in m["aria"], m["aria"]


def test_the_threshold_rule_is_still_drawn():
    """Position against a visible line is the reading that needs no
    colour vision at all — it must survive the side change."""
    m = _bars([0, 2, 0, 3], {"line": 1.5, "side": "UNDER", "w": 92, "h": 34})
    if m is None:
        return
    assert m["rules"] >= 1, "the line rule stopped being drawn"


# --- the placement --------------------------------------------------------

def test_the_card_draws_the_form_beside_the_pick():
    fn = _fn(APP, "cardHTML")
    i = fn.index('<div class="pick">')
    seg = fn[i:i + 400]
    assert "propSpark(r)" in seg, \
        "the form chart is no longer next to the bet on a prop card"


def test_the_spark_is_built_from_the_props_own_numbers():
    fn = _fn(APP, "propSpark")
    assert "r.recent_values" in fn and "r.logs" in fn, \
        "the spark stopped reading the prop's own history"
    assert "Number(r.line)" in fn, "the spark is not drawn against this line"
    assert "r.side" in fn, "the spark does not know which way the bet went"
    assert "side" in fn and "gamelogBars(" in fn


def test_a_prop_with_no_history_draws_nothing():
    """Three is the floor propAnalysis uses: below it the chart is an
    anecdote with a rule drawn through it. An empty box beside the pick
    is worse than no box."""
    fn = _fn(APP, "propSpark")
    assert "vals.length < 3" in fn, "the spark lost its history floor"
    assert 'return ""' in fn
    assert "Number.isFinite(line)" in fn, \
        "a prop with no line would draw bars against NaN"


def test_the_spark_has_a_style_and_cannot_overflow_its_card():
    assert ".pick-spark {" in CSS, "the spark has no style"
    i = CSS.index(".pick-spark {")
    seg = CSS[i:i + 260]
    assert "max-width: 100%" in seg, \
        "the spark svg can push a narrow card sideways"


# --- the board Ethan was looking at ---------------------------------------

def test_the_edge_board_row_passes_its_side_too():
    """His screenshot was the Edge board. Fixing Recommended and leaving
    that page telling the reader the opposite would be worse than either
    on its own."""
    i = APP.index("function edgeBoardRows(")
    seg = APP[i:i + 2000]
    assert "side: r.side" in seg, \
        "edge rows no longer carry the side of the bet"
    j = APP.index("function edgeRowHTML(")
    row = APP[j:j + 900]
    assert "side: r.side" in row, \
        "the edge board spark is coloured without knowing the side again"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
