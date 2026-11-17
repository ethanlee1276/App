"""Hockey is on every league list the app keeps (2026-11-17).

The app's list of leagues with a board (SPORT_CODES) never carried hockey.
Every place that read it skipped the NHL: /nhl opened the site on another
league, a shared hockey player, game or pick (the server hands back
`player/nhl/<slug>`) was read as a player named "nhl", Tonight's
every-league page left hockey's slate out, swiping between leagues passed
over it, and Settings' "Leagues in the nav" could not list it. What these
hold:

  - the list is every board the server keeps (engine/routes.BOARD_FILES),
    in the nav's order;
  - the routers take hockey: /nhl, #nhl and the three-part entity links;
  - a nav list narrowed before hockey was offered keeps hockey in the nav
    (navLeagueOn), and the first tap afterwards writes the leagues that
    were on, hockey included, with the list it was saved against;
  - Ask reads hockey's live scoreboard and hockey's team names, which
    its two lists (LIVE_LEAGUES, NAMED_LEAGUES) had left out.

    python3 tests/test_hockey_is_on_every_league_list.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import routes                                                        # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def _codes():
    at = APP.index("const SPORT_CODES = [")
    return re.findall(r'"([a-z]+)"', APP[at:APP.index("];", at)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const SPORT_CODES = {json.dumps(_codes())};
      const VIEW_ORDER = ["recommended", "record"];
      let _store = {{}};
      const settings = () => _store;
      const state = {{ sport: "nfl" }};
      const seen = [];
      const applySport = () => seen.push(["sport", state.sport]);
      const load = () => seen.push(["load"]);
      const friendRoute = () => true;
      const openPlayerRoute = (slug) => {{ seen.push(["player", slug]); return true; }};
      const openGame = (slug) => seen.push(["game", slug]);
      const openProp = (slug) => seen.push(["pick", slug]);
      {APP[APP.index("const NAV_LEAGUES_BEFORE_HOCKEY"):APP.index("function navLeagueOn(")]}
      {_fn(APP, "navLeagueOn")}
      {_fn(APP, "routeFromPath")}
      {_fn(APP, "entityRoute")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_list_is_every_board_in_the_navs_order():
    codes = _codes()
    assert sorted(codes) == sorted(routes.BOARD_FILES), (codes, sorted(routes.BOARD_FILES))
    nav = [c for c in re.findall(r'class="sport-btn[^"]*" data-sport="([a-z]+)"', INDEX) if c in codes]
    assert nav == codes, ("the nav's league buttons, in order", nav)


def test_the_routers_take_hockey():
    got = _node("""
      const out = { path: routeFromPath("/nhl"), shared: entityRoute("player/nhl/connor-mcdavid"),
                    sport: state.sport, seen: seen.slice() };
      seen.length = 0; state.sport = "nba";
      out.game = entityRoute("game/nhl/edm-cgy-1117");
      out.gameSeen = seen.slice();
      return out;
    """)
    if got is None:
        return
    assert got["path"] == {"hash": "nhl", "sport": "nhl"}
    assert got["shared"] is True and got["sport"] == "nhl"
    assert ["player", "connor-mcdavid"] in got["seen"], "the player, not a player named nhl"
    assert ["game", "edm-cgy-1117"] in got["gameSeen"]
    # The hash change and the boot both route a league by the same list.
    assert "if (SPORT_CODES.includes(h)) {" in APP and "if (hint.sport && SPORT_CODES.includes(hint.sport))" in APP


def test_a_list_narrowed_before_hockey_keeps_hockey():
    got = _node("""
      const on = (s) => SPORT_CODES.filter((c) => navLeagueOn(c, s));
      return {
        every: on({ leagues: [] }),
        before: on({ leagues: ["nfl", "nba"] }),
        chosen: on({ leagues: ["nfl", "nba"], leaguesOffered: SPORT_CODES.slice() }),
        kept: on({ leagues: ["nfl", "nhl"], leaguesOffered: SPORT_CODES.slice() }),
      };
    """)
    if got is None:
        return
    assert got["every"] == _codes()
    assert got["before"] == ["nfl", "nba", "nhl"], "a list saved before hockey was offered says nothing about it"
    assert got["chosen"] == ["nfl", "nba"], "once offered, the list decides"
    assert got["kept"] == ["nfl", "nhl"]


def test_the_settings_page_and_its_taps_read_the_same_rule():
    body = _fn(APP, "applyNavLeagues")
    assert "navLeagueOn(code)" in body and "settings().leagues" not in body
    assert "const on = navLeagueOn(c, s);" in ACCOUNT
    assert "SPORT_CODES.filter((c) => navLeagueOn(c, s)).length" in ACCOUNT
    tap = ACCOUNT[ACCOUNT.index('const league = hit("[data-set-league]");'):]
    tap = tap[:tap.index("return;")]
    assert "const cur = SPORT_CODES.filter((c) => navLeagueOn(c));" in tap
    assert tap.index("settings().leaguesOffered = SPORT_CODES.slice();") < tap.index('setSetting("leagues"'), \
        "stamped before the save writes the settings out"


def test_tonight_reads_hockeys_light_board():
    meta = APP[APP.index("  nhl: { logo:"):]
    meta = meta[:meta.index("},") + 2]
    assert 'fallback: "data/nhl.json"' in meta, "lightNameFor makes nhl_picks.json of it"
    fn = _fn(APP, "tonightBoards") if "function tonightBoards(" in APP else APP[APP.index("async function tonightBoards("):]
    assert "SPORT_CODES.map(async (s) =>" in fn


def test_ask_reads_hockeys_scores_and_team_names():
    from engine import askbot as A
    assert sorted(A.named_teams("who wins rangers vs islanders tonight", "nhl")) == ["NYI", "NYR"]
    assert sorted(A.named_teams("oilers at flames", "nhl")) == ["CGY", "EDM"]
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "live_nhl.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": "2026-11-17T03:00:00Z", "games": [
            {"home": "NYR", "away": "MTL", "home_name": "New York Rangers", "away_name": "Montreal Canadiens",
             "live": {"state": "final", "home_score": 3, "away_score": 1, "period": "Final"}}]}, fh)
    for args in (("nhl", ""), ("", "Canadiens")):
        got = A.live_scores(*args, data_dir=d)
        boards = got.get("scoreboards") or []
        assert boards and boards[0]["sport"] == "nhl", (args, got)
        assert boards[0]["games"][0]["score"] == "MTL 1, NYR 3"
    # Every league Ask names in its tools has its scoreboard and its team words.
    assert set(A.LIVE_LEAGUES) == set(A.LEAGUES) == set(A.NAMED_LEAGUES)


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
