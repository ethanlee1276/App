"""Tests for the bet-tracking ledger + bankroll (in-memory SQLite)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger


def _conn():
    return ledger.connect(":memory:")


def _result(**over):
    base = {
        "sport": "nfl", "date": "2024-W05",
        "recommendations": [
            {"player": "A", "market": "rush_yds", "side": "OVER", "line": 70.5,
             "book": "FanDuel", "odds": 100, "projection": 80, "hit_prob": 0.6,
             "edge": 0.08, "confidence": 7.5, "grade": "Play", "stake_units": 1.0,
             "recommended": True},
            {"player": "B", "market": "rec_yds", "side": "OVER", "line": 50.5,
             "odds": -110, "grade": "Pass", "stake_units": 0.0, "recommended": False},
        ],
    }
    base.update(over)
    return base


def test_bankroll_config_and_sizing():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=2000, unit_pct=2.0)
    assert ledger.bankroll(conn) == 2000
    ledger.log_recommendations(conn, _result())
    row = conn.execute("SELECT stake_dollars FROM bets WHERE player='A'").fetchone()
    # 1.0 unit × 2% × $2000 = $40
    assert row["stake_dollars"] == 40.0


def test_only_recommended_logged_and_idempotent():
    conn = _conn()
    assert ledger.log_recommendations(conn, _result()) == 1     # B is a Pass
    assert ledger.log_recommendations(conn, _result()) == 0     # idempotent
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1


def test_settle_win_updates_bankroll():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)  # $10/unit
    ledger.log_recommendations(conn, _result())
    # actual 85 clears the 70.5 line at +100 -> win, +1u = +$10
    n = ledger.settle(conn, {("A", "rush_yds"): 85.0})
    assert n == 1
    assert ledger.bankroll(conn) == 1010.0
    p = ledger.performance(conn)
    assert p["wins"] == 1 and p["win_rate"] == 1.0 and p["net_units"] == 1.0


def test_settle_loss_and_push():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    r = _result()
    r["recommendations"][0]["odds"] = -110
    ledger.log_recommendations(conn, r)
    ledger.settle(conn, {("A", "rush_yds"): 40.0})   # miss -> loss -1u = -$10
    assert ledger.bankroll(conn) == 990.0
    p = ledger.performance(conn)
    assert p["losses"] == 1 and p["net_units"] == -1.0

    # a push returns the stake
    conn2 = _conn()
    ledger.log_recommendations(conn2, _result())
    ledger.settle(conn2, {("A", "rush_yds"): 70.5})
    p2 = ledger.performance(conn2)
    assert p2["pushes"] == 1 and p2["net_units"] == 0.0 and ledger.bankroll(conn2) == 1000.0


def test_performance_breakdowns_and_clv():
    conn = _conn()
    ledger.log_recommendations(conn, _result())
    ledger.settle(conn, {("A", "rush_yds"): 90.0}, closing={("A", "rush_yds"): 72.5})
    p = ledger.performance(conn)
    assert "Play" in p["by_grade"] and p["by_grade"]["Play"]["w"] == 1
    assert "rush_yds" in p["by_market"]
    assert abs(p["avg_clv"] - 2.0) < 1e-9        # 72.5 - 70.5


def test_summary_renders():
    conn = _conn()
    ledger.log_recommendations(conn, _result())
    ledger.settle(conn, {("A", "rush_yds"): 90.0})
    s = ledger.summary(conn)
    assert "Bankroll" in s and "Win rate" in s and "ROI" in s


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
