"""The play-by-play page's picks room: our picks on this game, by board.

Ethan, 2026-09-26, the room circled on a Wyoming–Hawai'i page: "instead
of posting live bets, we should just be displaying the most likely bets
and edge bets that were placed on that game in that tab instead." The
room was the tracker's open tickets as one flat list ("Hawai'i Moneyline
· placed −125 · tracking"), which read as a live bet. It is now "Our
picks": the Pick of the Day when it is on this game, then Most Likely,
then Edge — a placed pick carries the tracker's word, a board pick the
journal does not hold says it is on the board, and nothing is drawn twice.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = "\n".join([
        "let state = { sport: 'cfb', data: {} }; let _oneBoard = true;",
        "const LEAGUE_LABEL = { cfb: 'College football', nfl: 'NFL' };",
        "const escapeHtml = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');",
        "const escapeAttr = escapeHtml;",
        "const american = (o) => (o > 0 ? `+${o}` : `−${Math.abs(o)}`);",
        "const teamName = (t) => ({ HAW: \"Hawai'i\", WYO: 'Wyoming' })[t] || t;",
        "const betMark = () => '<i></i>';",
        "const ridingAttrs = (r) => ` data-prop=\"placed:${r.player}\"`;",
        "const likelyOpen = (r) => ` data-open=\"likely:${r.player}\"`;",
        "const propAttrs = (r) => ` data-prop=\"edge:${r.player}\"`;",
        "const liveTrackerRows = (rows) => rows;",
        "const oneBoardOn = () => _oneBoard;",
        "const oneBoardRows = () => (state.data.likely_board || {}).rows || [];",
        "const showableLikelyRow = () => true; const likelyDropped = (r) => !!r.dropped;",
        "const passesFilters = (r) => !!r.recommended; const passesGameBet = (b) => b.grade !== 'Pass';",
        _const("OB_TIERS"),
        _fn("isLikelyBook"), _fn("propInGame"), _fn("trackerBetText"), _fn("pbpPropRows"),
        _const("PBP_GAME_MARKETS"),
        _fn("pbpPickKey"), _fn("pbpMarketOf"), _fn("pbpGameMarket"), _fn("pbpMergePicks"), _fn("pbpOurPicks"),
        _fn("pbpPickRowHTML"), _fn("pbpPropsHTML"),
        f"console.log(JSON.stringify((() => {{ {js} }})()));",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


GAME = """
  const d = { home: "HAW", away: "WYO" };
  const here = { home: "HAW", away: "WYO" };
  state.data = {
    live_picks: [
      { player: "HAW", market: "moneyline", side: "win", odds: -125, category: "main", status: "tracking", game: here },
      { player: "Pofele Ashlock", market: "rec_yds", market_label: "Receiving Yards", side: "over", line: 54.5, odds: -115,
        category: "likely", status: "cleared", current: 61, game: here },
      { player: "Elsewhere", market: "rush_yds", side: "over", line: 40.5, odds: -110, category: "main", status: "tracking",
        game: { home: "BSU", away: "UNLV" } },
    ],
    live_potd: [],
    likely_board: { rows: [
      { player: "Pofele Ashlock", team: "HAW", market: "rec_yds", market_label: "Receiving Yards", side: "over", line: 54.5,
        odds: -115, model_prob: 0.71, tier: "top", game: "WYO@HAW" },
      { player: "Harrison Waylee", team: "WYO", market: "rush_yds", market_label: "Rushing Yards", side: "over", line: 62.5,
        odds: -120, model_prob: 0.66, tier: "strong", game: "WYO@HAW" },
      { player: "Other Game", team: "BSU", market: "rush_yds", side: "over", line: 70.5, odds: -110, model_prob: 0.7,
        tier: "top", game: "UNLV@BSU" },
    ] },
    recommendations: [
      { player: "Micah Alejado", team: "HAW", opponent: "WYO", market: "pass_yds", market_label: "Passing Yards",
        side: "over", line: 240.5, odds: -110, hit_prob: 0.58, recommended: true },
      { player: "Not Recommended", team: "WYO", opponent: "HAW", market: "rec_yds", side: "under", line: 30.5,
        odds: -110, recommended: false },
    ],
    game_bets: [
      { home: "HAW", away: "WYO", bet_type: "moneyline", pick_label: "Hawai'i ML", odds: -125, grade: "B" },
      { home: "HAW", away: "WYO", market: "total", pick_label: "Under 44.5", odds: -108, grade: "B" },
    ],
  };
"""


def test_the_room_splits_the_games_picks_by_board():
    got = _node(GAME + """
      const p = pbpOurPicks(d);
      const view = (xs) => xs.map(({ r, placed }) => [r.pick_label || r.player, r.market, placed]);
      return { likely: view(p.likely), edge: view(p.edge), potd: p.potd.length };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["likely"] == [["Pofele Ashlock", "rec_yds", True], ["Harrison Waylee", "rush_yds", False]], \
        "the placed Most Likely pick once, with the board's other pick on this game after it"
    assert got["edge"] == [["HAW", "moneyline", True], ["Micah Alejado", "pass_yds", False], ["Under 44.5", "total", False]], \
        "the placed moneyline is not drawn a second time from the board; another game's pick is not here"
    assert got["potd"] == 0


def test_the_room_says_which_board_and_whether_it_was_placed():
    got = _node(GAME + "return { html: pbpPropsHTML(d, 'cfb'), other: pbpPropsHTML(d, 'nfl') };")
    if got is None:
        print("  SKIP node not installed"); return
    html = got["html"]
    assert html.index("Most Likely") < html.index("Edge picks"), "Most Likely first, then Edge"
    assert "Hawai'i Moneyline" in html and "placed −125" in html and ">tracking<" in html
    assert "Pofele Ashlock over 54.5 Receiving Yards" in html and ">CLEARED<" in html and "now 61" in html
    assert "Harrison Waylee over 62.5 Rushing Yards" in html and "66% our chance" in html and "Strong" in html
    assert "on the board" in html, "a pick the journal does not hold says so"
    assert 'data-open="likely:Harrison Waylee"' in html and 'data-prop="edge:Micah Alejado"' in html, "every pick opens its page"
    assert "Elsewhere" not in html and "Other Game" not in html and "Not Recommended" not in html
    assert "open the College football tab" not in html and "Our picks are kept on each league" in got["other"]


def test_an_empty_game_and_the_older_likely_board():
    got = _node("""
      const d = { home: "HAW", away: "WYO" };
      state.data = {};
      const empty = pbpPropsHTML(d, "cfb");
      _oneBoard = false;
      state.data = { most_likely: [
        { player: "Kept", team: "HAW", opponent: "WYO", market: "rec_yds", side: "over", line: 40.5, odds: -130, hit_prob: 0.7 },
        { player: "Dropped", team: "HAW", opponent: "WYO", market: "rec_yds", side: "over", line: 40.5, dropped: true } ] };
      return { empty, likely: pbpOurPicks(d).likely.map(({ r }) => r.player) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert "No Most Likely or edge picks on this game." in got["empty"]
    assert got["likely"] == ["Kept"]


def test_the_tab_is_named_for_what_it_holds():
    assert '["props", "Our picks"]' in APP and '"Live props"]' not in APP


if __name__ == "__main__":
    import sys
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
