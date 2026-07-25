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


def test_under_bets_are_graded_side_aware():
    """actual > line is a WIN for an under bettor's opponent, not for them —
    the ledger must grade the side that was actually bet (the same inversion
    once flipped the backtest's P&L)."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    r = _result()
    r["recommendations"][0].update({"side": "UNDER", "odds": -110})
    ledger.log_recommendations(conn, r)
    # Actual 40 is UNDER the 70.5 line -> the UNDER bet WINS.
    ledger.settle(conn, {("A", "rush_yds"): 40.0},
                  closing={("A", "rush_yds"): 65.5})
    p = ledger.performance(conn)
    assert p["wins"] == 1 and p["losses"] == 0
    assert p["net_units"] > 0
    # CLV flips for unders: line dropped 70.5 -> 65.5 = +5 for the under.
    assert abs(p["avg_clv"] - 5.0) < 1e-9
    assert "UNDER" in p["by_side"]


def test_proxy_priced_picks_are_not_journaled():
    conn = _conn()
    r = _result()
    r["recommendations"][0]["has_market"] = False
    assert ledger.log_recommendations(conn, r) == 0


def test_settle_from_history_db():
    """The learning loop's auto-settle: actuals come from ingested game logs,
    closing lines from harvested odds — no hand-built files."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    r = _result(sport="mlb", date="2026-07-24")
    r["recommendations"][0].update(
        {"player": "Aaron Judge", "market": "total_bases", "side": "UNDER",
         "line": 2.5, "odds": -120})
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "g", "player": "Aaron Judge", "team": "NYY",
         "opponent": "BOS", "position": "RF", "home": 1,
         "market": "total_bases", "value": 1.0}])
    hist_db.upsert_odds_history(hist, [
        {"sport": "mlb", "taken_at": "2026-07-24T23:00:00Z", "event_id": "e",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "total_bases", "book": "DK", "line": 2.0,
         "over_odds": -110, "under_odds": -110}])

    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    b = conn.execute("SELECT * FROM bets WHERE player='Aaron Judge'").fetchone()
    # 1 total base is under 2.5 -> the UNDER won; the harvested close joined.
    assert b["status"] == "won" and b["closing_line"] == 2.0
    # Bets with no ingested result stay open (nothing to grade them with).
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 0


def test_moneyline_picks_journal_and_settle_from_scores():
    """Sharp-anchor moneyline picks are validated FORWARD: journaled from
    game_bets, settled by the real final score."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "mlb", "date": "2026-07-24", "recommendations": [],
              "game_bets": [
                  {"bet_type": "moneyline", "recommended": True, "pick": "NYY",
                   "odds": -125, "win_prob": 0.60, "edge": 0.045,
                   "confidence": 6.0, "grade": "Play", "stake_units": 1.0},
                  {"bet_type": "moneyline", "recommended": False, "pick": "COL",
                   "odds": 240, "grade": "Pass", "stake_units": 0.0},
                  {"bet_type": "total", "recommended": True, "pick": "OVER",
                   "odds": -110, "grade": "Play", "stake_units": 1.0},
              ]}
    assert ledger.log_recommendations(conn, result) == 1   # only the ML pick

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
         "home_score": 5, "away_score": 3, "spread": 0.0, "total": None,
         "roof": "open", "surface": "grass", "temp": None, "wind": None,
         "extra": "yankee"}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    b = conn.execute("SELECT * FROM bets WHERE market='moneyline'").fetchone()
    assert b["status"] == "won"
    assert ledger.performance(conn)["net_units"] > 0


def test_total_picks_journal_and_settle_from_scores():
    """Sharp-anchor totals journal by matchup key and settle on the combined
    final score, side-aware."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "mlb", "date": "2026-07-24", "recommendations": [],
              "game_bets": [
                  {"bet_type": "total", "recommended": True, "side": "Under",
                   "line": 8.5, "odds": 100, "matchup": "BOS @ NYY",
                   "win_prob": 0.55, "edge": 0.04, "confidence": 5.5,
                   "grade": "Play", "stake_units": 1.0},
              ]}
    assert ledger.log_recommendations(conn, result) == 1

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
         "home_score": 5, "away_score": 3, "spread": 0.0, "total": None,
         "roof": "open", "surface": "grass", "temp": None, "wind": None,
         "extra": "yankee"}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    b = conn.execute("SELECT * FROM bets WHERE market='total'").fetchone()
    # 5+3 = 8 runs is UNDER 8.5 -> the Under won at +100.
    assert b["status"] == "won" and b["actual"] == 8.0
    assert ledger.performance(conn)["net_units"] == 1.0


def test_export_json_writes_the_site_record():
    import json, tempfile, os
    from pathlib import Path
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, _result())
    ledger.settle(conn, {("A", "rush_yds"): 85.0})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "web" / "data" / "record.json"
        ledger.export_json(conn, p)
        d = json.loads(p.read_text())
        assert d["overall"]["wins"] == 1
        assert d["nfl"]["settled"] == 1 and d["mlb"]["settled"] == 0
        assert d["recent"][0]["player"] == "A"
        assert d["recent"][0]["status"] == "won"
        assert "generated_at" in d


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
