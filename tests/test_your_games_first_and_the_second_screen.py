"""Your games first, the Sweat Board and the second screen (js/app.js
myBetTeams and the strip and Live board's order, js/detail.js PBP_BIG).

Ethan's second research paper (2026-10-29): "Rank every card on the home
screen and live page with one simple score: a user's tracked bet counts
most, then followed players and teams ... then how close the game is to
starting", "All-games Sweat Board: every game a user has action on, on one
screen" (ESPN's Multiview) and "Second-screen mode: big-text live view built
for a phone next to the TV, with alerts" (StreamCenter). What these hold:

  * an open bet's legs name its games' teams, in their own league; a
    settled bet names none;
  * the home strip puts a game a bet of yours rides on ahead of your teams,
    live games still first and the picks' own order untouched;
  * the Live tab, every league showing, gives your games their own shelf
    over the full slate (a scoreboard's favourites over its list); one
    league, your games first in it;
  * the second screen opens from a live game's TV row, shows the score, the
    clock, the last play, who the plays favour and the reader's legs, is
    the page's held copy (the TV delay holds it too), never a veiled game's,
    lights the score and taps once when it changes, and is counted.

Run directly: `python3 tests/test_your_games_first_and_the_second_screen.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
APP, DET = READ("web", "js", "app.js"), READ("web", "js", "detail.js")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return None
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_an_open_bet_names_its_games_teams_in_their_league():
    bets = [
        {"result": "pending", "legs": [{"sport": "nba", "team": "LAL", "game": "BOS @ LAL"},
                                       {"sport": "nfl", "team": "BUF", "game": "BUF @ LA"}]},
        {"result": "pending", "legs": [{"sport": "NBA", "player": "Jokic", "game": "DEN vs. PHX"}]},
        {"result": "win", "legs": [{"sport": "nba", "team": "NYK", "game": "NYK @ MIA"}]},
        {"result": "pending", "desc": "a bet logged by hand"},
    ]
    got = _node(f"const mbLoad = () => {json.dumps(bets)};\n" + _fn(APP, "myBetTeams") + _fn(APP, "myBetOn") + """
      const nba = myBetTeams("nba"), nfl = myBetTeams("nfl");
      console.log(JSON.stringify({ nba: [...nba].sort(), nfl: [...nfl].sort(),
        on: myBetOn({ home: "lal", away: "GSW" }, nba), off: myBetOn({ home: "NYK", away: "MIA" }, nba),
        none: myBetOn(null, nba) }));""")
    if got is None:
        return
    assert got["nba"] == ["BOS", "DEN", "LAL", "PHX"], got
    assert got["nfl"] == ["BUF", "LA"], "the Bills game's teams, in the NFL alone"
    assert got["on"] is True and got["off"] is False and got["none"] is False, "a settled bet names none"


def test_the_strip_and_the_live_board_put_your_games_first():
    strip = APP[APP.index("const fav = (g) => (isFavTeam(g.home) || isFavTeam(g.away)) ? 0 : 1;"):]
    strip = strip[:strip.index("|| startKey(a).localeCompare(startKey(b)));")]
    assert "const mine = myBetTeams(state.sport), bet = (g) => myBetOn(g, mine) ? 0 : 1;" in strip
    assert strip.index("rank(a) - rank(b)") < strip.index("bet(a) - bet(b)") < strip.index("fav(a) - fav(b)"), \
        "live first, then your bets, then your teams"
    board = APP[APP.index("async function renderLiveBoard()"):]
    board = board[:board.index("\n}\n")]
    assert "const yours = _liveChip === \"all\" ? games.filter(isYours) : [];" in board
    shelf = board.index("Your games <span class=\"mini\">— ${yours.length} with your bets on</span>")
    assert shelf < board.index("Object.keys(LIVE_FEEDS).filter((s) => bySport[s])"), \
        "your games over the full slate, the way a scoreboard's favourites sit over its list"
    assert "shown.sort((a, b) => isYours(b) - isYours(a));" in board, "one league: yours lead its grid"
    # The picks' order is the product (Ethan, 2026-08-20): nothing of this touches a board of picks.
    assert "myBetTeams(" not in APP[APP.index("function renderLivePicks()"):APP.index("function renderLivePicks()") + 6000]


def test_the_second_screen_is_the_held_copy_and_never_a_veiled_game():
    tv = _fn(DET, "pbpTvHTML")
    assert 'if (!d || (d.live || {}).state !== "live") return "";' in tv and 'data-big="on">Second screen</button>' in tv
    page = DET[DET.index("async function renderPbpPage("):]
    held, veil = page.index("d = tvHeld.d;\n  PBP_BIG.d = null;"), page.index("if (d && spoiledG(league,")
    shown = page.index("PBP_BIG.d = d;")
    assert held < veil < shown < page.index("chatMount(league, event, d);"), "set only after the veil's check"
    wire = page[page.index("  const wire = () => {"):page.index("  const wire = () => {") + 900]
    assert "pbpBigPaint();" in wire
    paint = _fn(DET, "pbpBigPaint")
    assert 'if (!PBP_BIG.on || state.view !== "pbp" || !PBP_BIG.d) {' in paint, "leaving the game closes it"
    assert "pbpBigLock(true);" in paint and 'buzz("tap");' in paint and "prefers-reduced-motion" in paint
    assert 'track("second_screen", ' in DET and 'e.key === "Escape"' in DET
    from engine import analytics as AN
    assert "second_screen" in AN.CLIENT_EVENTS


def test_the_second_screen_says_the_game_big_and_your_legs():
    d = {"home": "LAL", "away": "BOS", "live": {"state": "live", "period": "Q3", "clock": "6:00",
                                                 "home_score": 70, "away_score": 66},
         "plays": [{"event": "Tatum makes a three", "wp": 41}]}
    got = _node("""
      const escapeHtml = (s) => String(s);
      const icon = () => "x";
      let tvDelay = () => 30;
      const PBP_ACT = { list: [{ legs: [{ player: "LeBron James" }] }] };
      const pbpLegLine = (l) => `<li>${l.player}</li>`;
      """ + DET[DET.index("const PBP_BIG = {"):DET.index("async function pbpBigLock(")] + f"""
      PBP_BIG.d = {json.dumps(d)};
      const a = pbpBigHTML();
      tvDelay = () => 0; PBP_BIG.d = {{ home: "LAL", away: "BOS", live: {{ state: "final" }}, plays: [] }};
      PBP_ACT.list = [];
      console.log(JSON.stringify({{ a, b: pbpBigHTML() }}));""")
    if got is None:
        return
    a = got["a"]
    for want in ("<span>BOS</span><b>66</b>", "<span>LAL</span><b>70</b>", "Q3 · 6:00", "Tatum makes a three",
                 "BOS 59% to win", "<li>LeBron James</li>", "30s behind, with your TV"):
        assert want in a, (want, a)
    assert "Final" in got["b"] and "<ul" not in got["b"] and "behind" not in got["b"], got["b"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
