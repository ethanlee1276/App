"""NBA opening night: the game lines, the build's ceiling and the day's pick.

Ethan, 2026-10-20, 7:04 PM, a screenshot of the NBA home page: the 76ers @
Knicks card read "lines post closer to tip-off" four minutes before tip,
Top Picks said the board "needs priced player props", and the Pick of the
Day read "NO BET … decided 04:17 UTC, when 0 of the slate had not started".
"Also nba games are not showing live."

Three causes in the code, three fixes pinned here:

* the NBA board's only paid pull was the props pull (nineteen credits a
  game on a small share of the day), so a night it was declined carried no
  moneyline, spread or total — the NFL's and college's three-credit
  whole-slate tier now runs for the hoops boards too (`--board-odds`);
* the NBA, WNBA and NHL builds ran under the 180-second default ceiling
  the model boards outgrew — a board killed every cycle keeps its file at
  the last build that finished: no lines, no props and a frozen live state;
* a "no bet" decided before the slate had a single row held the day
  (`potd.carry`; its own tests are in
  tests/test_the_days_pick_is_decided_once_not_re_decided_hourly.py).

Run directly: `python3 tests/test_nba_opening_night_lines.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget                                # noqa: E402

LAUNCH = (ROOT / "launch.py").read_text(encoding="utf-8")
NBA = (ROOT / "nba_build.py").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    i = LAUNCH.index(f"def {name}(")
    return LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]


def test_the_hoops_and_hockey_boards_get_the_model_boards_ceiling():
    for name in ("refresh_nba", "refresh_wnba", "refresh_nhl"):
        fn = _fn(name)
        assert "_run_build(args, timeout=600)" in fn, name
        assert "_run_build(args)" not in fn, name


def test_the_pregame_lines_ride_their_own_clock_on_the_leagues_money():
    import launch
    for league, clock in (("nba", launch.NBA_BOARD_CLOCK), ("wnba", launch.WNBA_BOARD_CLOCK)):
        assert oddsbudget.budget_sport(clock) == league
        assert clock not in (launch.NBA_LINES_CLOCK, launch.WNBA_LINES_CLOCK), \
            "the live lane keeps its own clock"


def _board(path: Path, states) -> str:
    path.write_text(json.dumps({"games": [{"home": "NYK", "away": "PHI",
                                           "live": ({"state": s} if s else None)}
                                          for s in states]}))
    return str(path)


def test_the_lines_tier_buys_only_while_a_game_is_still_to_tip():
    import launch
    real = (launch._odds_affordable, launch._paid_pull_baseline, launch._lines_stale)
    asked = []
    try:
        launch._paid_pull_baseline = lambda: "before"
        launch._lines_stale = lambda sport, tag="lines": False
        launch._odds_affordable = lambda out, quiet, **kw: asked.append(kw) or True
        with tempfile.TemporaryDirectory() as d:
            pre = _board(Path(d) / "pre.json", [None, "live"])
            args = ["nba_build.py"]
            assert launch._hoops_lines_tier(args, pre, "nba", launch.NBA_BOARD_CLOCK, True) == (True, "before")
            assert args[-1] == "--board-odds"
            assert asked[-1]["sport"] == launch.NBA_BOARD_CLOCK
            assert asked[-1]["credits"] == launch.BOARD_ODDS_COST
            # Every game under way or over: no pre-game line left to buy, and
            # the pacer is not even asked.
            asked.clear()
            done = _board(Path(d) / "done.json", ["live", "final"])
            args = ["nba_build.py"]
            assert launch._hoops_lines_tier(args, done, "nba", launch.NBA_BOARD_CLOCK, True) == (False, "")
            assert args == ["nba_build.py"] and asked == []
            # The pacer says no: nothing bought.
            launch._odds_affordable = lambda out, quiet, **kw: False
            args = ["nba_build.py"]
            assert launch._hoops_lines_tier(args, pre, "nba", launch.NBA_BOARD_CLOCK, True) == (False, "")
            assert args == ["nba_build.py"]
    finally:
        launch._odds_affordable, launch._paid_pull_baseline, launch._lines_stale = real


def test_refresh_nba_buys_the_lines_when_the_props_pull_is_declined():
    import launch
    names = ("_slate_games", "_odds_affordable", "_with_odds", "_live_lines_due", "_run_build",
             "_finish_paid_pull", "_paid_pull_baseline", "_games_before_tip", "_lines_stale",
             "_board_word")
    real = {n: getattr(launch, n) for n in names}
    ran = []
    try:
        launch._slate_games = lambda path: 2
        launch._with_odds = lambda: True
        launch._live_lines_due = lambda path: False
        launch._paid_pull_baseline = lambda: "before"
        launch._games_before_tip = lambda path: 2
        launch._lines_stale = lambda sport, tag="lines": False
        launch._finish_paid_pull = lambda *a, **k: None
        launch._board_word = lambda path, ok: "ok"
        launch._run_build = lambda args, timeout=180: ran.append((list(args), timeout)) or (True, "")
        # The props pull declined, the three-credit tier allowed.
        launch._odds_affordable = lambda out, quiet, sport=None, **kw: sport == launch.NBA_BOARD_CLOCK
        assert launch.refresh_nba(quiet=True)
        args, timeout = ran[-1]
        assert "--cached-odds" in args and "--board-odds" in args and "--odds" not in args
        assert timeout == 600
        # The props pull authorised: it carries the game lines itself.
        launch._odds_affordable = lambda out, quiet, sport=None, **kw: True
        assert launch.refresh_nba(quiet=True)
        args, _t = ran[-1]
        assert "--odds" in args and "--board-odds" not in args
    finally:
        for n, f in real.items():
            setattr(launch, n, f)


def test_the_build_reads_the_lines_for_games_not_yet_under_way():
    assert 'ap.add_argument("--board-odds", action="store_true",' in NBA
    assert "if args.board_odds or _board_lines_cached(args.league):" in NBA
    # In-play quotes are not a game's pre-game line.
    assert '(g.get("state") or "scheduled") == "scheduled"' in NBA
    # Before the stale-line scan and the spreads the props read.
    assert NBA.index("_board_lines_cached(args.league)") < NBA.index("spread_by_team: dict = {}")


def _event(home="New York Knicks", away="Philadelphia 76ers", when="2026-10-20T23:00:00Z"):
    return {"id": "e1", "commence_time": when, "home_team": home, "away_team": away,
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [
                                {"key": "h2h", "outcomes": [{"name": home, "price": -180},
                                                            {"name": away, "price": 150}]},
                                {"key": "spreads", "outcomes": [{"name": home, "price": -110, "point": -4.5},
                                                                {"name": away, "price": -110, "point": 4.5}]},
                                {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 224.5},
                                                               {"name": "Under", "price": -110, "point": 224.5}]}]}]}


def test_the_board_lines_price_an_nba_slate_game():
    """The shared whole-slate path, on the NBA build's own game objects."""
    import nba_build as B
    from engine.sources import oddsapi as O
    real = (O.fetch_sport_odds, O.sport_cache_age)
    try:
        O.fetch_sport_odds = lambda sport, **kw: ([_event()], O.Quota())
        O.sport_cache_age = lambda sport="nfl", cache_tag="", **kw: 60.0
        game = B._Game("NYK", "PHI", "2026-10-20T23:00:00Z", "New York Knicks", "Philadelphia 76ers")
        res = O.apply_board_lines_to_slate(B._Slate([game], []), sport="nba", cache_only=True)
    finally:
        O.fetch_sport_odds, O.sport_cache_age = real
    assert res.games_priced == 1, res
    assert (game.home_ml, game.away_ml) == (-180, 150)
    assert game.spread == -4.5 and game.total == 224.5


def test_a_cached_lines_file_is_found_only_under_the_tagged_name():
    import nba_build as B
    from engine.sources import fetch as F
    real = F.CACHE_DIR
    try:
        with tempfile.TemporaryDirectory() as d:
            F.CACHE_DIR = Path(d)
            assert not B._board_lines_cached("nba")
            (Path(d) / "odds_board_nba.json").write_text("[]")     # the live lane's file
            assert not B._board_lines_cached("nba")
            (Path(d) / "odds_board_nba_lines.json").write_text("[]")
            assert B._board_lines_cached("nba") and not B._board_lines_cached("wnba")
    finally:
        F.CACHE_DIR = real


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"  ok  {name}")
    print(f"\n{n} tests passed.")
