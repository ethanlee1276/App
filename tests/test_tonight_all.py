"""Tonight, across every sport, on one page.

Ethan, 2026-09-05: "tonight across every sport on one page". The tab
drew one league; an "All sports" chip now draws every league's card on
one page from each league's light board, the current league first, each
in its own colours, with the single-league view a tap away and
unchanged. The pure parts run in node (skipped without it).
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

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const LEAGUE_LABEL = {{ nfl: "NFL", cfb: "College", mlb: "MLB" }};
      const passesFilters = (r) => r.grade !== "Pass";
      const passesGameBet = (b) => b.ok !== false;
      const heldForLongShots = (r) => r.market === "home_runs" && !r.hr_featured;
      const showableLikelyRow = (r) => !r.hidden;
      {_fn("escapeHtml")}
      {_fn("tonightPick")}
      {_fn("tonightLeagueOrder")}
      {_fn("tonightChipsHTML")}
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


def test_one_reader_picks_what_the_tab_draws_from_a_board():
    got = _node("""
      const d = { recommendations: [{player: "A", grade: "A"}, {player: "B", grade: "Pass"}, {player: "C", grade: "A", market: "home_runs"}],
                  game_bets: [{pick: "NYY"}, {pick: "BOS", ok: false}], long_shots: [1, 2, 3, 4],
                  most_likely: Array.from({length: 14}, (_, i) => ({ i, hidden: i === 3 })) };
      const t = tonightPick(d);
      const e = tonightPick(null);
      return { props: t.props.map((r) => r.player), bets: t.bets.length, shots: t.shots.length, ml: t.ml.length, n: t.n, any: t.any,
               empty: [e.n, e.any, e.props.length, e.ml.length] };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["props"] == ["A"], "the Pass and the unfeatured homer are held"
    assert got["bets"] == 1 and got["shots"] == 3 and got["ml"] == 10 and got["n"] == 2 and got["any"] is True
    assert got["empty"] == [0, False, 0, 0]


def test_the_current_league_leads_and_the_chips_name_the_two_views():
    got = _node("""
      return { order: tonightLeagueOrder(["mlb", "nfl", "nba", "wnba", "cfb"], "cfb"),
               unknown: tonightLeagueOrder(["mlb", "nfl"], "ufc"), none: tonightLeagueOrder([], "nfl"),
               sport: tonightChipsHTML("sport", "cfb"), all: tonightChipsHTML("all", "nfl") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["order"] == ["cfb", "mlb", "nfl", "nba", "wnba"] and got["unknown"] == ["mlb", "nfl"] and got["none"] == []
    assert 'class="lb-chip active" data-tn-scope="sport">College' in got["sport"] and 'class="lb-chip " data-tn-scope="all">All sports' in got["sport"]
    assert 'class="lb-chip active" data-tn-scope="all">All sports' in got["all"]


def test_every_league_is_fetched_once_from_its_light_board_with_a_fallback():
    fn = _fn("tonightBoards")
    assert "if (Date.now() - _tonightAll.at < 60000) return _tonightAll.boards;" in fn
    assert "SPORT_CODES.map(async (s) =>" in fn
    assert "let r = await paidFetch(lightNameFor(meta));" in fn
    assert 'if (!r.ok) r = await paidFetch(String(meta.fallback || "").replace(/^data\\//, ""));' in fn, "a league without a light copy yet still draws"
    assert "boards[s] = normalizeSlate(await r.json());" in fn


def test_each_leagues_block_draws_in_its_own_colours_and_puts_them_back():
    fn = _fn("tonightLeagueHTML")
    assert "const was = window.ACTIVE_TEAMS;\n  window.ACTIVE_TEAMS = teamsForSport(s);" in fn
    assert "} finally {\n    window.ACTIVE_TEAMS = was;\n  }" in fn, "put back even if a card throws"
    assert "t.ml.map(likelyRow)" in fn and "t.props.map(cardHTML)" in fn and "t.bets.map(gameBetCard)" in fn and "t.shots.map(longShotCard)" in fn
    assert "nothing clears the bar" in fn and 'data-tonight-league="${s}"' in fn


def test_a_door_in_another_leagues_block_switches_the_league_and_waits_for_its_board():
    fn = _fn("renderTonightAll")
    assert "if (s === state.sport) return;" in fn, "the current league's cards keep their own doors"
    assert 'e.target.closest("[data-prop], [data-open], [data-gid]")' in fn
    assert "chip.click();" in fn and 'afterBoardFor(s, () => { switchView("tonight"); again(); });' in fn
    wait = _fn("afterBoardFor")
    assert "state.sport === s && state.data && _boardFor === meta.api && !state.lightBoard" in wait, "the full board, not the light one, before a detail page opens"
    assert "setTimeout(() => afterBoardFor(s, fn, tries - 1), 200);" in wait and "if (tries <= 0) return;" in wait
    assert 'if (_tonightScope !== "all" || state.view !== "tonight") return;' in fn, "a slow fetch never draws over a page the reader left"


def test_the_single_league_page_is_unchanged_but_for_the_chip_row():
    fn = _fn("renderTonight")
    assert 'if (_tonightScope === "all") { renderTonightAll(host); return; }' in fn
    assert "const { props, bets, shots, ml, n } = tonightPick(d);" in fn
    assert fn.count('tonightChipsHTML("sport", state.sport)') == 2, "the chips on the empty page too"
    assert "Most likely to hit tonight" in fn and "Our edge bets" in fn and "bindTonightChips(host);" in fn
    i = APP.index('try { _tonightScope = localStorage.getItem("qb.tonight.scope")')
    assert "=== \"all\" ? \"all\" : \"sport\"" in APP[i:i + 120], "anything but a remembered All is the single league"
    for sel in (".tn-chips", ".tn-league", ".tn-block .cards"):
        assert sel in CSS, sel


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
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
