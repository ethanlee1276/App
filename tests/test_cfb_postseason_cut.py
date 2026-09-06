"""College football's postseason starts in the season's OWN December.

Found 2026-09-05 while counting one-score games for the under-pressure
table: a college champion read 15-0 in the regular-season standings,
which is two games more than a regular season plus a conference title
game can hold. `engine.playoffs.POSTSEASON` dated the college cut at
December 15 of the FOLLOWING year, so no bowl or playoff game was ever
postseason — every one counted in the standings table, and the bracket
page, which draws only postseason rows, never had a college row to draw.

Run directly: `python3 tests/test_cfb_postseason_cut.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, playoffs, standings


def test_bowls_and_the_playoff_are_postseason_and_the_title_game_is_not():
    assert playoffs.is_postseason("cfb", 2025, "2025-12-06") is False, "conference title games"
    assert playoffs.is_postseason("cfb", 2025, "2025-12-13") is False, "Army–Navy"
    assert playoffs.is_postseason("cfb", 2025, "2025-12-20") is True, "playoff first round"
    assert playoffs.is_postseason("cfb", 2025, "2026-01-10") is True, "semifinals"
    assert playoffs.is_postseason("cfb", 2025, "2026-01-20") is True, "the final"
    # The NBA's cut really is in the next calendar year, and stays so.
    assert playoffs.is_postseason("nba", 2025, "2026-04-20") is True
    assert playoffs.is_postseason("nba", 2025, "2025-12-20") is False


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    rows = [
        ("2025-08-30", "IND", "OSU", 31, 10), ("2025-09-06", "MICH", "IND", 3, 20),
        ("2025-09-13", "IND", "PSU", 27, 24), ("2025-09-20", "ORE", "IND", 14, 21),
        ("2025-12-06", "IND", "OSU", 13, 10),           # conference title game
        ("2025-12-20", "IND", "ALA", 38, 3),            # playoff first round
        ("2026-01-20", "IND", "TEX", 27, 21),           # the final
    ]
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score) VALUES ('cfb', 2025, ?, ?, ?, ?, ?, ?)",
        [(p, f"g{i}", h, a, hs, as_) for i, (p, h, a, hs, as_) in enumerate(rows)])
    return conn


def test_the_standings_table_counts_the_title_game_and_not_the_playoff():
    conn = _conn()
    table = standings.compute(conn, "cfb", season=2025, today="2026-02-01")
    ind = [t for g in table["groups"] for t in g["teams"] if t["team"] == "IND"][0]
    assert ind["record"] == "5-0", ind
    assert table["games_counted"] == 5
    b = playoffs.bracket(conn, "cfb", season=2025, today="2026-02-01")
    assert b["started"] is True
    assert b["games_counted"] == 2 and len(b["rounds"]) >= 1, b


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
