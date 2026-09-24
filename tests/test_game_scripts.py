"""Which Most Likely picks need the same game, and which need opposite ones.

Ethan, 2026-09-24: "there could be 10 different most likely bets for one
game but I feel like they can all fall into a different game script so I
feel like if you're making a parlay with those picks, there could be one
pick that hurts another … clarify like what falls under what game script
… figure out how we can organize that for the user."

A game goes two ways that move props — who is AHEAD and how many POINTS
get scored — and each lean the site reads is one this repo measured
(engine/corrfit.PRIORS). Picks are sorted into the four scripts they can
win in; two picks that need opposite directions on one axis are a clash,
named on the game page, on the Most Likely page, on the pick page and on
the parlay slip.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _consts():
    out = []
    for name in ("GS_RUSH", "GS_CATCH", "GS_PASS", "GS_TD", "GS_K", "GS_OUTS", "GS_BAT", "GS_HOOP", "GS_HIGH_TOTAL"):
        i = APP.index(f"const {name} = ")
        out.append(APP[i:APP.index(";\n", i) + 1])
    return "\n".join(out)


PRELUDE = "\n".join([
    "const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml;",
    "const MINUS = '\\u2212'; const wholePct = (x) => `${Math.round(x * 100)}%`;",
    "const icon = () => ''; const likelyOpen = () => '';",
    "const teamName = (t) => ({ GB: 'Packers', ATL: 'Falcons' }[t] || t);",
    "const isGameRow = (r) => !!(r && (r.kind === 'game' || !r.player));",
    "const showableLikelyRow = () => true;",
    "var state = { sport: 'nfl', data: { games: [{ home: 'GB', away: 'ATL', favorite: 'GB', spread: -4.5, total: 43.5 }],"
    "  most_likely: [] } };",
])

ML = {"kind": "game", "player": "GB ML", "pick_label": "GB ML", "bet_type": "moneyline", "market": "moneyline",
      "team": "GB", "home": "GB", "away": "ATL", "model_prob": 0.69}
RUSH_U = {"kind": "prop", "player": "Josh Jacobs", "market": "rush_yds", "market_label": "Rushing Yards",
          "side": "UNDER", "line": 55.5, "team": "GB", "opponent": "ATL", "model_prob": 0.62}
REC_U = {"kind": "prop", "player": "Jayden Reed", "market": "rec_yds", "market_label": "Receiving Yards",
         "side": "UNDER", "line": 56.5, "team": "GB", "opponent": "ATL", "model_prob": 0.6}
TD = {"kind": "td", "player": "Josh Jacobs", "market": "anytime_td", "market_label": "Anytime TD",
      "side": "yes", "line": None, "team": "GB", "opponent": "ATL", "model_prob": 0.55}
UNDER = {"kind": "game", "player": "Under 43.5", "pick_label": "Under 43.5", "bet_type": "total", "market": "total",
         "side": "Under", "team": "GB", "home": "GB", "away": "ATL", "model_prob": 0.58}
KICK = {"kind": "prop", "player": "Brandon McManus", "market": "kicking_points", "side": "OVER", "line": 7.5,
        "team": "GB", "opponent": "ATL", "model_prob": 0.6}


def _run(expr):
    node = shutil.which("node")
    if not node:
        return None
    fns = [_fn(n) for n in ("scriptGameOf", "scriptNeed", "scriptPickLabel", "scriptScenarios", "scriptExpected",
                            "scriptClashes", "scriptClashLine", "gameScriptsHTML", "slipScriptNote")]
    prog = PRELUDE + "\n" + _consts() + "\n" + "\n".join(fns) + f"\nprocess.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_each_pick_leans_the_measured_way():
    got = _run("[%s].map((r) => { const n = scriptNeed(r); return [n.margin, n.points]; })"
               % ",".join(json.dumps(x) for x in (ML, RUSH_U, REC_U, TD, UNDER, KICK)))
    if got is None:
        print("  SKIP node not installed")
        return
    assert got == [[1, 0],     # GB ML: the home side ahead
                   [-1, 0],    # a Packers back's under: the Packers not ahead (leading teams run)
                   [1, 0],     # a Packers receiver's under: the Packers ahead (trailing teams throw)
                   [0, 1],     # a touchdown is points
                   [0, -1],    # the under is few points
                   [0, 0]], got  # nothing measured for a kicker: fits any script


def test_opposite_needs_are_a_clash_and_same_needs_are_not():
    got = _run("scriptClashes([%s]).map((c) => [c.a.player, c.b.player])"
               % ",".join(json.dumps(x) for x in (ML, RUSH_U, REC_U, TD, UNDER, KICK)))
    if got is None:
        return
    assert ["GB ML", "Josh Jacobs"] in got, "a win for the Packers is a day their back runs more"
    assert ["Josh Jacobs", "Jayden Reed"] in got, "one needs the Packers behind, one ahead"
    assert ["Josh Jacobs", "Under 43.5"] in got, "a touchdown against a low-scoring game"
    assert ["GB ML", "Jayden Reed"] not in got, "both need the Packers ahead"
    assert not any("Brandon McManus" in pair for pair in got), "no lean, no clash"


def test_the_game_is_sorted_into_its_scripts_expected_first():
    html = _run("gameScriptsHTML(state.data.games[0], [%s])" % ",".join(json.dumps(x) for x in (ML, RUSH_U, REC_U, TD, KICK)))
    if html is None:
        return
    assert "The lines expect <b>Packers ahead (−4.5) · low-scoring (total 43.5)</b>" in html
    first = html.index('class="gs-scn is-expected"')
    assert html.index("Packers ahead · low-scoring") > first and html.index("Packers ahead · low-scoring") < first + 200
    assert "Fits any script" in html and "Brandon McManus" in html
    assert "Pull against each other" in html and "the game that cashes one" in html


def test_a_game_with_no_clash_says_so():
    html = _run("gameScriptsHTML(state.data.games[0], [%s])" % ",".join(json.dumps(x) for x in (ML, REC_U)))
    if html is None:
        return
    assert "None of these need opposite games" in html and "Pull against each other" not in html


def test_the_slip_names_a_clash_on_the_ticket():
    legs = [dict(RUSH_U), dict(REC_U)]
    note = _run("slipScriptNote(%s)" % json.dumps(legs))
    if note is None:
        return
    assert 'class="slip-clash"' in note and "Josh Jacobs" in note and "Jayden Reed" in note
    assert _run("slipScriptNote(%s)" % json.dumps([dict(ML), dict(REC_U)])) == ""


def test_every_surface_carries_it():
    page = _fn("renderGamePage")
    assert "const gpScripts = gameScriptsHTML(g, likelies);" in page
    assert 'gpScripts ? ["gp-sec-scripts", "Game scripts"] : null' in page
    assert '<div id="gp-sec-scripts">' in page
    assert "+ likelyScriptsHTML(rows);" in _fn("renderLikely")
    assert "scriptWhyItem(" in _fn("whyLikelyHTML") and "scriptWhyItem(b)" in _fn("whyGameHTML")
    assert "${slipScriptNote(s.legs)}" in _fn("slipRender")
    for sel in (".gs-card {", ".gs-scn.is-expected {", ".gs-chip {", ".gs-clash {", ".slip-clash {"):
        assert sel in CSS, sel


def test_every_lean_names_its_measurement():
    """A lean with no measurement behind it is a guess wearing the site's
    authority; the block's comment names the corrfit pairing for each."""
    i = APP.index("GAME SCRIPTS — which picks need the game to go the same way")
    note = APP[i:APP.index("const GS_RUSH", i)]
    for key in ("rb_rush_yds__own_margin", "wr_receptions__own_margin", "qb_pass_yds__own_points",
                "sp_strikeouts__opp_runs", "sp_outs__own_margin"):
        assert key in note, key
    from engine import corrfit
    names = {p.key for p in corrfit.PRIORS}
    assert {"rb_rush_yds__own_margin", "wr_receptions__own_margin", "qb_pass_yds__own_points",
            "sp_strikeouts__opp_runs", "sp_outs__own_margin"} <= names


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
