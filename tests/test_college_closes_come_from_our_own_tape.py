"""College closes for the season being played come from the lines we record.

Ethan's droplet, 2026-09-23: college closes per season read
[(2022, 951), (2023, 939), (2024, 861), (2025, 860), (2026, 0)]. Every past
season is cfbfastR's cfb_line_odds.csv, whose newest row is 2026-01-20 — it
publishes after a season. The 2026 closes were in `odds_history` all along
(engine/lineledger.record, every build); nothing copied the last pre-kickoff
one to the games table. engine/lineledger.closes_into_games does, from every
college build, for each finished game in its fourteen-day results window.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                                # noqa: E402
from engine import lineledger as L                                   # noqa: E402


def _conn():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [
        {"sport": "cfb", "season": 2026, "period": "2026-09-19", "game_id": "401", "home": "OSU",
         "away": "MICH", "home_score": 31, "away_score": 24, "extra": json.dumps({"week": 4})},
        {"sport": "cfb", "season": 2026, "period": "2026-09-19", "game_id": "402", "home": "UGA",
         "away": "BAMA", "home_score": 20, "away_score": 17, "spread": -3.0, "total": 48.5},
    ])
    ev = "2026-09-19-MICH@OSU"
    rows = []
    for taken, spread, total, hml, aml in (("2026-09-19T15:00:00Z", -6.5, 47.5, -250, 205),
                                           ("2026-09-19T19:25:00Z", -7.0, 48.0, -265, 215),
                                           ("2026-09-19T20:10:00Z", -14.5, 38.5, -900, 600)):   # in play
        base = {"sport": "cfb", "taken_at": taken, "event_id": ev, "home": "OSU", "away": "MICH", "book": "best"}
        rows += [{**base, "player": "OSU", "market": "spread", "line": spread, "over_odds": -110, "under_odds": -110},
                 {**base, "player": "TOTAL", "market": "total", "line": total, "over_odds": -110, "under_odds": -110},
                 {**base, "player": "OSU", "market": "moneyline", "line": 0.0, "over_odds": hml, "under_odds": None},
                 {**base, "player": "MICH", "market": "moneyline", "line": 0.0, "over_odds": aml, "under_odds": None}]
    rows.append({"sport": "cfb", "taken_at": "2026-09-19T15:00:00Z", "event_id": "2026-09-19-BAMA@UGA",
                 "home": "UGA", "away": "BAMA", "book": "best", "player": "UGA", "market": "spread",
                 "line": -1.0, "over_odds": -110, "under_odds": -110})
    db.upsert_odds_history(conn, rows)
    return conn


GAMES = [{"completed": True, "kickoff": "2026-09-19T19:30:00Z", "date": "2026-09-19", "home": "OSU",
          "away": "MICH", "game_id": "401", "season": 2026},
         {"completed": True, "kickoff": "2026-09-19T19:30:00Z", "date": "2026-09-19", "home": "UGA",
          "away": "BAMA", "game_id": "402", "season": 2026},
         {"completed": False, "kickoff": "2026-09-26T19:30:00Z", "date": "2026-09-26", "home": "X",
          "away": "Y", "game_id": "403", "season": 2026}]


def test_the_last_line_before_kickoff_is_the_close():
    conn = _conn()
    got = L.closes_into_games(conn, "cfb", GAMES)
    row = conn.execute("SELECT spread, total, extra FROM games WHERE game_id='401'").fetchone()
    assert (row[0], row[1]) == (-7.0, 48.0), "the 19:25 snapshot, not the in-play one at 20:10"
    extra = json.loads(row[2])
    assert extra["ml"] == [-265, 215] and extra["ml_source"] == "tape" and extra["week"] == 4
    assert got == {"games": 1, "spread": 1, "total": 1, "ml": 1}


def test_a_published_close_is_never_overwritten_and_a_rerun_changes_nothing():
    conn = _conn()
    L.closes_into_games(conn, "cfb", GAMES)
    assert conn.execute("SELECT spread, total FROM games WHERE game_id='402'").fetchone()[:2] == (-3.0, 48.5)
    assert L.closes_into_games(conn, "cfb", GAMES) == {"games": 0, "spread": 0, "total": 0, "ml": 0}


def test_every_college_build_runs_it():
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert '_ll.closes_into_games(conn, "cfb", [g for g in history + games if g["completed"]])' in src


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
