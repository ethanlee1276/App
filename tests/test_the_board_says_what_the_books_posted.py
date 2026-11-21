"""The board says what the books posted for each game it bought props for
(engine/propmenu, 2026-11-14).

College basketball's board priced no player props for two days, and telling
"we did not buy" from "we bought and the books had posted nothing" took a
command on the box (runbook PL). Ethan's run showed the second: Saturday's
7am pull bought five games and the books had posted player markets on one,
ladders only, where Friday's 6pm pull found them on all five. Each
basketball board now carries `prop_menu`, read off the paid pulls' own
cached payloads: per game, how many books answered, how many standard player
markets and ladders they carried, and when it was pulled. Menus, never a
price.

    python3 tests/test_the_board_says_what_the_books_posted.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import propmenu as PM                    # noqa: E402

NOW = 1794672000.0          # 2026-11-14T16:00Z


def _event(folder, name, away, home, tip, markets, books=8, age_h=3.0):
    path = Path(folder) / name
    path.write_text(json.dumps({
        "away_team": away, "home_team": home, "commence_time": tip,
        "bookmakers": [{"key": f"b{i}", "markets": [{"key": m, "outcomes": []} for m in markets]}
                       for i in range(books)]}))
    os.utime(path, (NOW - age_h * 3600, NOW - age_h * 3600))
    return path


def test_each_bought_game_says_what_its_books_carried():
    d = tempfile.mkdtemp()
    _event(d, "odds_event_cbb_a1_x.json", "LSU Tigers", "Gonzaga Bulldogs", "2026-11-14T20:30:00Z",
           ["h2h", "spreads", "totals", "player_points_alternate", "player_rebounds_alternate"], books=9)
    _event(d, "odds_event_cbb_a2_x.json", "Stonehill Skyhawks", "Texas Tech Red Raiders",
           "2026-11-14T19:00:00Z", ["h2h", "spreads", "totals"])
    _event(d, "odds_event_cbb_a3_x.json", "Ohio State Buckeyes", "UConn Huskies", "2026-11-14T23:30:00Z",
           ["h2h", "player_points", "player_points_alternate", "player_rebounds"], books=10)
    rows = PM.census("cbb", now=NOW, cache_dir=d)
    assert [r["game"] for r in rows] == ["Stonehill Skyhawks @ Texas Tech Red Raiders",
                                         "LSU Tigers @ Gonzaga Bulldogs",
                                         "Ohio State Buckeyes @ UConn Huskies"], "soonest tip first"
    by = {r["game"].split(" @ ")[1]: r for r in rows}
    assert by["Texas Tech Red Raiders"]["posted"] == "no player markets"
    assert by["Gonzaga Bulldogs"]["posted"] == "ladders only" and by["Gonzaga Bulldogs"]["books"] == 9
    assert by["UConn Huskies"]["posted"] == "player props and ladders"
    assert by["UConn Huskies"]["player_markets"] == 2 and by["UConn Huskies"]["ladders"] == 1
    assert by["Gonzaga Bulldogs"]["pulled"] == "2026-11-14T13:00Z"
    assert PM.summary(rows) == "3 game(s) bought: 1 with player props, 1 with ladders only, 1 with none"
    assert "price" not in json.dumps(rows), "menus, never a price"


def test_old_pulls_and_finished_games_and_other_leagues_stay_off():
    d = tempfile.mkdtemp()
    _event(d, "odds_event_cbb_b1_x.json", "A", "B", "2026-11-13T23:00:00Z", ["player_points"], age_h=17)
    _event(d, "odds_event_cbb_b2_x.json", "C", "D", "2026-11-15T00:00:00Z", ["player_points"], age_h=30)
    _event(d, "odds_event_nba_b3_x.json", "E", "F", "2026-11-15T00:00:00Z", ["player_points"])
    assert PM.census("cbb", now=NOW, cache_dir=d) == [], "yesterday's game, a stale pull, another league"
    # The newest pull of a game wins.
    _event(d, "odds_event_cbb_c1_old.json", "G", "H", "2026-11-14T23:00:00Z", [], age_h=9)
    _event(d, "odds_event_cbb_c1_new.json", "G", "H", "2026-11-14T23:00:00Z", ["player_points"], age_h=1)
    rows = PM.census("cbb", now=NOW, cache_dir=d)
    assert len(rows) == 1 and rows[0]["posted"] == "player props"
    assert PM.summary([]) == "no paid prop pull in the last day"


def test_the_basketball_boards_carry_it():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'out["prop_menu"] = _pm.census(args.league)' in src
    assert src.index('out.update(status="slate", **picks_result)') < src.index('out["prop_menu"] = _pm.census(')


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
