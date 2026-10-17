"""An exchange's chance and a book's price are shown in the same unit.

Audit 2026-09-30, V-9 / O13 (roadmap #37). Kalshi printed "62%" and books
printed "-163", so comparing them meant converting in your head; the crowd
table had no time on it; the gap sentence appeared only at 3 points or
more (so "they agree" and "we did not say" looked the same); and
`exchange_fair`, hung on game rows by engine/exchangefair, was read by
nothing on the page. The fee half of O13 shipped in #22.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def _run(expr):
    js = ("const MINUS = '\\u2212';\n"
          "const american = (o) => (o > 0 ? `+${o}` : `\\u2212${Math.abs(o)}`);\n"
          "const escapeHtml = (s) => String(s);\n"
          "const teamName = (s) => s;\n"
          + "".join(_fn(n) for n in ("probPrice", "pctPrice", "pulledAgo", "crowdLinesHTML",
                                     "crowdStripHTML", "exchangeFairLine"))
          + f"\nconsole.log(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_every_exchange_percentage_carries_its_price():
    got = _run("[probPrice(0.62), probPrice(0.40), probPrice(0.5), probPrice(1), pctPrice(0.62)]")
    assert got[0] == "\u2212163" and got[1] == "+150" and got[2] == "\u2212100"
    assert got[3] == "", "no price for a certainty"
    assert got[4].startswith("62%") and "(\u2212163)" in got[4]


def test_the_crowd_table_has_prices_a_pull_time_and_always_a_gap():
    g = {"away": "NYJ", "home": "BUF"}
    recent = "new Date(Date.now() - 7 * 60000).toISOString()"
    html = _run("crowdStripHTML({away:'NYJ',home:'BUF',crowd:{kalshi:0.62,polymarket:0.6,books:0.6,"
                f"gap_pts:1.0,at:{recent}}}}})")
    assert "(\u2212163)" in html and "(\u2212150)" in html, "each market's % with its price"
    assert "exchange prices pulled 7m ago" in html
    assert "1.0 points higher than the books" in html, "a 1-point gap is said, not hidden"
    agree = _run("crowdStripHTML({away:'NYJ',home:'BUF',crowd:{kalshi:0.6,books:0.6,gap_pts:0.2}})")
    assert "agree on this one" in agree
    lines = _run("crowdLinesHTML({away:'NYJ',home:'BUF'},{kalshi_over:0.55,total_line:44.5})")
    assert "Over 44.5" in lines and "(\u2212122)" in lines


def test_a_game_pick_shows_what_the_exchanges_give_it():
    line = _run("exchangeFairLine({exchange_fair:0.58,win_prob:0.61})")
    assert "Prediction markets: 58%" in line and "(\u2212138)" in line and "our model 61%" in line
    assert _run("exchangeFairLine({win_prob:0.6})") == ""
    assert "${exchangeFairLine(r)}" in _fn("gameBetCard")


def test_the_crowd_build_stamps_when_it_read_the_prices():
    from engine import crowd
    games = [{"away": "NYJ", "home": "BUF"}]
    result = {"games": games}
    crowd.attach(result, "nfl", kalshi_markets=[], poly_rows=[], kalshi_line_markets=[])
    src = (ROOT / "engine" / "crowd.py").read_text()
    assert 'c["at"] = pulled' in src and "pulled = _dt.datetime.now(_dt.timezone.utc)" in src


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
