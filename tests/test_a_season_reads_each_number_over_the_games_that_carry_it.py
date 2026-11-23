"""A season reads each number over the games that carry it (step ACV, 23 November 2026).

The WNBA's box scores are being read again a night at a time, newest first (step ABO): a game read before the
site kept attempts, steals, blocks and turnovers carries its points and its made threes (the old "3PT" column)
and nothing else until the re-read reaches it. A'ja Wilson's 2026 page, the Monday morning after the first night,
read 3PT "0.9-0.8" and 3P% 113.2 across 48 games: every column divided by every game, made threes from all 48 and
attempts from the few re-read. What these hold:

  * an average is the stat over the games that carry it, not over every game played;
  * a percentage, an average of two markets and a made-tried read only the games carrying both;
  * a column no game of the season carries both halves of says nothing rather than a wrong number;
  * a season every game of which carries every column reads exactly as before.

    python3 tests/test_a_season_reads_each_number_over_the_games_that_carry_it.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamelog as GL, playerpage as PP                 # noqa: E402

OLD = {"min": 34.0, "pts": 24.0, "reb": 9.0, "ast": 3.0, "fg3m": 1.0}           # read before the new columns
NEW = {"min": 38.0, "pts": 28.0, "reb": 10.0, "ast": 2.0, "fg3m": 1.0, "fg3a": 3.0,
       "stl": 2.0, "blk": 1.0, "tov": 2.0, "fgm": 10.0, "fga": 18.0, "ftm": 7.0, "fta": 8.0}
HOW = {c[0]: c[3] for c in GL.HOOPS[0][-1]}


def _season(*games):
    s: dict = {}
    for g in games:
        GL.add_up(s, dict(g))
    return s


def test_an_average_is_over_the_games_that_carry_it():
    s = _season(OLD, OLD, OLD, NEW)
    assert PP.averaged("wnba", HOW["pts"], s, 4) == 25.0, "points are in every game: (3 x 24 + 28) / 4"
    assert PP.averaged("wnba", HOW["stl"], s, 4) == 2.0, "steals over the one game that has them, not 0.5"
    assert PP.averaged("wnba", HOW["blk"], s, 4) == 1.0 and PP.averaged("wnba", HOW["tov"], s, 4) == 2.0


def test_the_headline_reads_the_same_way():
    s = _season(OLD, OLD, OLD, NEW)
    spec = ("stl", "STL", "Steals", ("sum", "stl"), True, False, None, False)
    assert PP.head_value("wnba", spec, s, 4) == 2.0, "a headline per-game number over the games that carry it"


def test_a_percentage_and_a_made_tried_read_the_games_with_both():
    s = _season(OLD, OLD, OLD, NEW)
    assert PP.averaged("wnba", HOW["fg3"], s, 4) == "1.0-3.0", "made and tried over the same game"
    assert GL.value("wnba", HOW["fg3p"], s, 4) == 33.3, "1 of 3, never 4 of 3"
    assert GL.value("wnba", HOW["fg3"], s, 4) == "1-3", "the season's made-tried, the same games"
    assert GL.value("wnba", HOW["fgp"], s, 4) == 55.6 and PP.averaged("wnba", HOW["fg"], s, 4) == "10.0-18.0"


def test_a_column_no_game_carries_whole_says_nothing():
    s = _season(OLD, OLD)
    assert PP.averaged("wnba", HOW["fg3"], s, 2) is None and GL.value("wnba", HOW["fg3p"], s, 2) is None
    assert PP.averaged("wnba", HOW["stl"], s, 2) is None, "no game has steals"


def test_a_whole_season_reads_as_before():
    s = _season(NEW, NEW)
    assert PP.averaged("wnba", HOW["stl"], s, 2) == 2.0 and PP.averaged("wnba", HOW["fg3"], s, 2) == "1.0-3.0"
    assert GL.value("wnba", HOW["fg3p"], s, 2) == 33.3 and GL.value("wnba", HOW["fg3p"], NEW) == 33.3, \
        "one game's own line, as before"
    # Football's averages of two markets too: yards a carry over the games with both.
    f = _season({"rush_yds": 50.0}, {"rush_yds": 40.0, "carries": 10.0})
    how = next(c[3] for g in GL.FOOTBALL for c in g[-1] if c[3][:2] == ("avg", "rush_yds"))
    assert GL.value("nfl", how, f, 2) == 4.0


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
