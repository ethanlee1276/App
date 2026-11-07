"""The unplayed-game finder does the expensive work only where it can matter.

2026-10-01: the box's settle step took 184.7 s a cycle and `launch.py
--todo` stalled. `unplayed_bets` looked every open bet's player up in that
day's whole player log (three days of it, a name normalisation per row)
before asking the one question that can rule a bet out: does the day have
a scoreless game row and a final at all? Since roadmap #44 it runs on every
settle. Now a day is judged once, a day that cannot qualify costs nothing
per bet, only past open bets are read, a day's name map is built once, and
the auto-void asks only for its own sports. The answers are unchanged:
tests/test_unplayed.py and test_a_postponed_mlb_game_voids_itself.py pin
them.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger  # noqa: E402

TODAY = "2026-10-01"


def _world(n_final_days=5, bets_per_day=40):
    hconn = db.connect(":memory:")
    lconn = ledger.connect(":memory:")
    rows = []
    for k in range(n_final_days):
        day = (dt.date(2026, 9, 20) + dt.timedelta(days=k)).isoformat()
        rows.append({"sport": "mlb", "season": 2026, "period": day, "game_id": f"A@B{k}",
                     "home": "B", "away": "A", "home_score": 3, "away_score": 2})
        for i in range(bets_per_day):
            lconn.execute(
                "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
                " stake_units, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (day, "mlb", day, f"Player {i}", "hits", "OVER", 0.5, -150, 1.0, "open", "main"))
    # One day that CAN qualify: a scoreless CLE@CIN beside a final.
    rows += [{"sport": "mlb", "season": 2026, "period": "2026-09-26", "game_id": "CLE@CIN",
              "home": "CIN", "away": "CLE", "home_score": None, "away_score": None},
             {"sport": "mlb", "season": 2026, "period": "2026-09-26", "game_id": "X@Y",
              "home": "Y", "away": "X", "home_score": 1, "away_score": 0}]
    db.upsert_games(hconn, rows)
    db.upsert_player_logs(hconn, [{
        "sport": "mlb", "season": 2026, "period": "2026-09-25", "game_id": "CIN@Z",
        "player": "Elly De La Cruz", "team": "CIN", "opponent": "Z", "position": "SS",
        "home": 1, "market": "hits", "value": 1.0}])
    for side in ("OVER", "UNDER"):
        lconn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
            " stake_units, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-09-26", "mlb", "2026-09-26", "Elly De La Cruz", "hits", side, 0.5,
             -150, 1.0, "open", "main"))
    # A future bet: never read.
    lconn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " stake_units, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (TODAY, "mlb", "2026-10-02", "Elly De La Cruz", "hits", "OVER", 0.5, -150, 1.0,
         "open", "main"))
    lconn.commit()
    return hconn, lconn


def test_a_day_that_cannot_qualify_costs_no_player_lookups():
    hconn, lconn = _world()
    calls = []
    real = ledger._bet_team
    ledger._bet_team = lambda h, b, cache=None: calls.append(b["date"]) or real(h, b, cache)
    try:
        got = ledger.unplayed_bets(lconn, hconn, TODAY)
    finally:
        ledger._bet_team = real
    assert [(r["player"], r["team"]) for r in got] == [("Elly De La Cruz", "CIN")] * 2, got
    assert calls == ["2026-09-26", "2026-09-26"], calls        # 200 final-day bets skipped


def test_the_auto_void_asks_only_for_its_own_sports():
    import inspect
    src = inspect.getsource(ledger.auto_void_unplayed)
    assert "sports=AUTO_VOID_SPORTS" in src


def test_a_sports_filter_narrows_the_read():
    hconn, lconn = _world(n_final_days=1, bets_per_day=1)
    assert ledger.unplayed_bets(lconn, hconn, TODAY, sports=("nba",)) == []
    assert len(ledger.unplayed_bets(lconn, hconn, TODAY, sports=("mlb",))) == 2


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fails += 1; print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
