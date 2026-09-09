"""Under pressure on the play-by-play page, read live.

Ethan, 2026-09-08: "I know we added under pressure data for teams, like
clutch win % and reliability % and comeback % and choke % and see if we
can have that as live data as well like when games are going. That's
something we should be showing on the live play by play page yeah? And
use live data for it where we can."

The rates are season counts and do not change during a game; what
changes is the question the scoreboard asks of them. The live card
already reads that in one sentence (`pressureSituation`); the game page
has the two-team table; the play-by-play page — the page a reader is
on WHILE the game is going — had neither. It has a rail card now:

  * `pressureMoment` reads the deep file's live block (score, period,
    clock, possession) against the board's favourite and says which rate
    is being asked of whom — a trailing favourite its reliability and the
    underdog its comeback rate; a one-score game late the favourite's
    choke rate and the underdog's clutch rate; both clutch rates with no
    favourite on file or before the game;
  * the card lights those two cells in the table, chips the moment, and
    beside it prints the one live number this site holds that IS a
    probability — the live market's de-vigged moneyline, when the board
    tracks it;
  * the page warms the league's standings with its own fetch and redraws
    the card on its twelve-second pass while the game is live.

Run directly: `python3 tests/test_pbp_pressure.py`
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
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


# --- the page ----------------------------------------------------------------
def test_the_page_warms_the_leagues_standings_and_draws_the_card_in_the_rail():
    page = APP[APP.index("async function renderPbpPage("):]
    page = page[:page.index("\n}\n")]
    assert "pressureWarm([league])," in page, "the rates are never loaded for the page"
    i = page.index("pressureWarm([league]),")
    assert i < page.index("if (res.ok) d = await res.json();"), "warmed after the render"
    # THE CARD IS IN THE RAIL AND THE MARKET'S NUMBER IS ABOVE IT, which
    # is what this ever meant. Pinning the two lines as ADJACENT broke on
    # 2026-09-09 when our own live win probability landed between them —
    # a third card in the same rail, which is not a regression in either
    # of these. Ordered, not adjacent.
    rail = page[page.index("${winProb}"):page.index("</aside>")]
    assert "${pbpPressureHTML(d, league, boardGame)}" in rail, rail


def test_the_card_reads_the_cache_and_lights_the_cells_being_asked():
    card = _fn("pbpPressureHTML")
    assert "(_standingsCache[league] || {}).pressure" in card
    assert 'if (!pr) return "";' in card
    assert "pressureMoment({ sport: league, d, boardGame, pr })" in card
    assert 'class="pbp-pr-asked"' in card
    assert "the market’s number, not ours" in card
    assert "re-read with every pass of the fast loop" in card
    for sel in (".pbp-pr-chips", ".pbp-pr-line", ".pbp-pr-market", ".pbp-pr-asked"):
        assert sel in CSS, sel


def test_the_header_counts_four_readers():
    assert "Four places read them" in APP


# --- the moment, run ----------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("PRESSURE_ONE_SCORE")}
      {_fn("pressurePct")}
      {_fn("pressureLate")}
      {_fn("pressureFav")}
      {_fn("pressureSituation")}
      {_fn("pressureMoment")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


PR = """{ season: 2026, season_used: 2025, teams: {
      KC: { clutch: 64.3, reliability: 81.0, comeback: 40.0, choke: 12.5, record: "11-6" },
      DEN: { clutch: 84.6, reliability: 70.0, comeback: 80.0, choke: 30.0, record: "10-7" } } }"""


def _asks(m):
    return [[a["team"], a["rate"]] for a in m["asks"]]


def test_the_moment_says_which_rate_the_scoreboard_is_asking_of_whom():
    got = _node(f"""
      const pr = {PR};
      const d = (live) => ({{ home: "KC", away: "DEN", live }});
      const board = {{ home: "KC", away: "DEN", spread: -3.0 }};
      const m = (live, bg) => pressureMoment({{ sport: "nfl", d: d(live), boardGame: bg === undefined ? board : bg, pr }});
      return {{
        pre: m({{ state: "scheduled" }}),
        trailing: m({{ state: "live", home_score: 14, away_score: 24, period: "Q2", clock: "8:12" }}),
        oneLate: m({{ state: "live", home_score: 27, away_score: 24, period: "Q4", clock: "2:01" }}),
        oneLateNoFav: m({{ state: "live", home_score: 27, away_score: 24, period: "Q4" }}, null),
        earlyClose: m({{ state: "live", home_score: 7, away_score: 3, period: "Q1" }}),
        ball: m({{ state: "live", home_score: 14, away_score: 24, period: "Q3", possession: "DEN" }}),
        market: m({{ state: "live", home_score: 14, away_score: 24, period: "Q3" }},
                  {{ ...board, line_track: {{ home: "KC", away: "DEN", now: 31.5, opened: 58.0 }} }}),
        stranger: pressureMoment({{ sport: "nfl", d: d({{ state: "live" }}).home = "NYJ" && {{ home: "NYJ", away: "DEN", live: {{ state: "live" }} }}, boardGame: board, pr }}),
        run: pressureMoment({{ sport: "mlb", d: {{ home: "KC", away: "DEN", live: {{ state: "live", home_score: 3, away_score: 2, period: "Bot 8th" }} }}, boardGame: null, pr }}),
      }};
    """)
    if got is None:
        return
    pre = got["pre"]
    assert not pre["live"] and pre["chips"] == [] and pre["market"] is None
    assert _asks(pre) == [["KC", "clutch"], ["DEN", "clutch"]]
    assert "wins 64% of its one-score games" in pre["line"]
    tr = got["trailing"]
    assert tr["live"] and _asks(tr) == [["KC", "reliability"], ["DEN", "comeback"]], tr
    assert tr["chips"] == ["10-point game", "KC trails as the favourite"], tr["chips"]
    assert "trails as the favourite" in tr["line"] and "81%" in tr["line"] and "80%" in tr["line"]
    ol = got["oneLate"]
    assert _asks(ol) == [["KC", "choke"], ["DEN", "clutch"]], ol
    assert ol["chips"] == ["one-score game", "late"], ol["chips"]
    assert ol["one"] and ol["late"] and ol["margin"] == 3
    nf = got["oneLateNoFav"]
    assert _asks(nf) == [["KC", "clutch"], ["DEN", "clutch"]] and nf["fav"] is None
    ec = got["earlyClose"]
    assert ec["one"] and not ec["late"] and _asks(ec) == [], "an early one-score game asks nothing yet"
    assert ec["chips"] == ["one-score game"]
    assert got["ball"]["chips"][-1] == "DEN has the ball"
    mk = got["market"]["market"]
    assert mk == {"home": "KC", "now": 31.5, "opened": 58.0}, mk
    assert got["stranger"] is None, "a team with no rates draws a card"
    run = got["run"]
    assert run["chips"] == ["one-score game", "late innings"], run["chips"]
    assert _asks(run) == [["KC", "clutch"], ["DEN", "clutch"]]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
