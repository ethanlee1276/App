"""Every league's spread says who gives the points (24 November).

The NBA's, hockey's and college's boards carry no ``favorite``; their ``spread``, like the NFL's, is written from the
home side (-5.5: the home side gives the points; +5.5: the away side does). The Live card's lines grid, the side
rail's live cards and the game page's lines table took the home side as the favourite when the slate named none, so
an away favourite read backwards: Memphis at Charlotte showed "MEM +2.5" beside "MEM -145" on the Live tab. And the
game page's and the team page's line chip showed nothing outside the NFL. One rule now,
app.js spreadFav: the slate's favourite, else the spread's own sign.

Run directly: `python3 tests/test_every_leagues_spread_says_who_gives_the_points.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def test_the_rule_reads_the_spreads_own_sign():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    fn = APP[APP.index("function spreadFav(g)"):]
    fn = fn[:fn.index("\n}") + 2]
    cases = [{"away": "MEM", "home": "CHA", "spread": 5.5},                    # tonight's NBA board: MEM -185
             {"away": "POR", "home": "PHI", "spread": -2.5},
             {"away": "CIN", "home": "WAS", "favorite": "CIN", "spread": 6.5},  # the NFL names it
             {"away": "A", "home": "B", "spread": 0}, {"away": "A", "home": "B"}]
    out = subprocess.run([node, "-e", fn + f"process.stdout.write(JSON.stringify({json.dumps(cases)}.map(spreadFav)))"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    assert json.loads(out.stdout) == ["MEM", "PHI", "CIN", "", ""]


def test_every_place_that_draws_a_spread_uses_it():
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    assert APP.count("const fav = spreadFav(g);") == 2, "the live card and the rail's live cards"
    assert 'const fav = g.favorite || (Number.isFinite(sp) && sp !== 0 ? (sp < 0 ? g.home : g.away) : "");' in APP, \
        "the game script's read, the same rule written out (its tests run it on its own)"
    assert "const gpFav = spreadFav(g);" in det, "the game page's lines table"
    assert "`<span class=\"chip\">${escapeHtml(teamName(spreadFav(g)))} −${Math.abs(g.spread).toFixed(1)}</span>`" in det
    assert "spreadFav(g) && g.spread != null ? `${teamNameIn(d.sport, spreadFav(g))}" in more, "the team page"
    for js in (APP, det, more):
        assert "g.favorite || g.home" not in js, "never the home side by default"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
