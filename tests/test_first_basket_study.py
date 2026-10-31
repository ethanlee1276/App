"""The NBA first-basket study runs before it is run on the box
(tools/first_basket_study.py; Ethan, 2026-10-31: "first basket score for
NBA ... not just off of book lines").

The study reads the box's stored shots read-only and asks what predicts the
first made basket. These check its rules on shots made up for the purpose:
the first basket is the first MADE shot by action order, the first shot's
team stands in for the tip, the clock reads both feeds' spellings, and the
shares are prior-only.

Run directly: `python3 tests/test_first_basket_study.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import first_basket_study as S                      # noqa: E402
from engine import db                                           # noqa: E402


def _shot(gid, action, player, team, home, made, period=1, clock="PT11M30.00S", season=2025, date="2025-11-01"):
    return (gid, action, season, date, player, team, home, period, clock, made)


def test_the_first_basket_is_the_first_made_shot_by_action_order():
    rows = [_shot("g1", 7, "Jokic", "DEN", 1, 1), _shot("g1", 3, "Gobert", "MIN", 0, 0),
            _shot("g1", 5, "Edwards", "MIN", 0, 1)]
    g = S.games_from(rows)[0]
    assert g["first_shot"] == "MIN" and g["first"] == ("Edwards", "MIN")
    assert g["home"] == "DEN" and g["away"] == "MIN"


def test_the_clock_reads_both_spellings():
    assert S._clock_s("PT11M45.00S") == 705.0 and S._clock_s("9:30") == 570.0 and S._clock_s("") == -1.0


def test_shares_are_prior_only_and_the_tool_runs_on_a_db():
    rows = []
    for i in range(6):
        gid, d = f"g{i}", f"2025-11-{i + 1:02d}"
        season = 2024 if i < 3 else 2025
        rows += [_shot(gid, 1, "Star", "AAA", 1, 1, season=season, date=d),
                 _shot(gid, 4, "Star", "AAA", 1, 0, season=season, date=d),
                 _shot(gid, 2, "Role", "AAA", 1, 0, season=season, date=d),
                 _shot(gid, 3, "Other", "BBB", 0, 0, season=season, date=d)]
    games = S.games_from(rows)
    ev = S.share_events(games, {"shots": 1.0})
    assert ev[0]["p"] == 0.5, "the first game knows nothing yet: an even split"
    assert ev[-1]["p"] > 0.5, "by the last, the man who takes the shots is likelier"
    p = Path(tempfile.mkdtemp()) / "h.db"
    c = sqlite3.connect(p)
    c.executescript(db.SCHEMA)
    c.executemany("INSERT INTO nba_shots (game_id, action, season, date, player, team, home, period, clock, made) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    assert S.main(["--db", str(p)]) == 0


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
