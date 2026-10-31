"""The NBA reads this season's minutes once they are measured to read better
(engine/nba/window; Ethan, 2026-10-29: "Ok keep going", after "think like a
pro sports better").

A week into a season a man's last twenty games are mostly last season's
final weeks, a lottery club's April or a contender's playoffs. A pro reads
his role off this season's games once he has a few, and measures first.
What these hold:

  * the build measures it each day (`window_for`, kept a day under
    data/models) and reads this season's games alone only past MIN_GAMES
    scored games and MARGIN minutes closer; otherwise the twenty-game
    window, as the board always read it;
  * when chosen, only the minutes base moves: the per-minute rate keeps all
    his games, and the card says the minutes came from this season;
  * a history the measurement cannot read answers the board's own window.

Run directly: `python3 tests/test_the_nba_reads_this_seasons_minutes_once_measured.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.hoops import NBA                    # noqa: E402
from engine.nba import pipeline as P            # noqa: E402
from engine.nba import window as W              # noqa: E402

BUILD = (ROOT / "nba_build.py").read_text(encoding="utf-8")


def _prop(**kw):
    # Four games this season at 34 minutes, then sixteen of last season's end at 24.
    p = {"player": "A Starter", "market": "pts", "minutes": [34] * 4 + [24] * 16,
         "values": [24] * 4 + [17] * 16, "is_starter": True, "spread": 0.0,
         "is_favorite": False, "rest": "1day", "player_mult": 1.0}
    p.update(kw)
    return p


def test_when_chosen_only_the_minutes_base_reads_this_season():
    old = P.project(_prop(), NBA)
    new = P.project(_prop(base_games=4), NBA)
    assert old["base"] < 30 and new["base"] == 34.0, (old["base"], new["base"])
    # Everything else neutral here, so the projection over its minutes is the rate.
    assert round(old["projection"] / old["proj_min"], 2) == round(new["projection"] / new["proj_min"], 2), \
        "the per-minute rate keeps all twenty games"
    assert any("games this season" in n for n in new["context"]), new["context"]
    assert not any("games this season" in n for n in old["context"])
    same = P.project(_prop(base_games=20), NBA)
    assert same["base"] == old["base"] and not any("games this season" in n for n in same["context"]), \
        "a window of all his games is the board's own window"
    assert P.project(_prop(base_games=2), NBA)["base"] == old["base"], "under three, the base's own floor"


def test_the_rule_needs_enough_games_and_a_clear_margin():
    m = {"n": W.MIN_GAMES, "mae_twenty": 4.0, "mae_season": 4.0 - W.MARGIN}
    assert W.choose(m) == "season"
    assert W.choose(dict(m, mae_season=4.0 - W.MARGIN + 0.01)) == "twenty"
    assert W.choose(dict(m, n=W.MIN_GAMES - 1)) == "twenty"
    assert W.choose({"n": 0}) == "twenty" and W.choose({}) == "twenty"


def test_it_is_measured_once_a_day_and_kept():
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("QB_MODELS_DIR")
        os.environ["QB_MODELS_DIR"] = d
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, "
                         "player TEXT, market TEXT, value REAL)")
            for k in range(60):
                for i in range(15):
                    conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2025, ?, ?, 'min', 24)",
                                 (f"2026-03-{10 + i:02d}", f"P{k}"))
                for i in range(6):
                    conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2026, ?, ?, 'min', 34)",
                                 (f"2026-10-{21 + i:02d}", f"P{k}"))
            got = W.window_for(conn, "nba", "2026-10-29")
            assert got["n"] == 180 and got["window"] == "season" and got["season"] == 2026, got
            stored = json.loads((Path(d) / W.STORE).read_text())
            assert stored["nba:2026-10-29"]["window"] == "season"
            conn.execute("DELETE FROM player_game_logs")
            assert W.window_for(conn, "nba", "2026-10-29")["window"] == "season", "read from the day's store"
            assert W.window_for(conn, "nba", "2026-10-30")["window"] == "twenty", "a new day measures again"
            assert W.window_for(sqlite3.connect(":memory:"), "nba", "2026-10-31")["window"] == "twenty", \
                "no history table: the board's own window"
        finally:
            if old is None:
                os.environ.pop("QB_MODELS_DIR", None)
            else:
                os.environ["QB_MODELS_DIR"] = old


def test_his_games_this_season_are_counted_from_the_newest():
    dates = ["2026-10-27", "2026-10-25", "2026-10-22", "2026-04-12", "2026-04-10"]
    assert W.this_season(dates, "nba", 2026) == 3
    assert W.this_season(dates, "nba", 2025) == 0
    assert W.this_season([], "nba", 2026) == 0


def test_the_build_measures_and_passes_it():
    assert "minutes_window = _window.window_for(conn, args.league, args.date)" in BUILD
    assert 'if minutes_window.get("window") == "season" else 0),' in BUILD


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
