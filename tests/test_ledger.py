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


def test_pnl_curve_runs_cumulative_by_date():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    # Day 1: a +100 winner. Day 2: a loser.
    ledger.log_recommendations(conn, _result(date="2026-07-24"))
    ledger.settle(conn, {("A", "rush_yds"): 85.0})
    r2 = _result(date="2026-07-25")
    r2["recommendations"][0]["player"] = "C"
    ledger.log_recommendations(conn, r2)
    ledger.settle(conn, {("C", "rush_yds"): 40.0})

    curve = ledger.pnl_curve(conn)
    assert [p["date"] for p in curve] == ["2026-07-24", "2026-07-25"]
    assert curve[0] == {"date": "2026-07-24", "day_u": 1.0, "cum_u": 1.0, "n": 1}
    # Running total nets the loss against day 1's win.
    assert curve[1]["day_u"] == -1.0 and curve[1]["cum_u"] == 0.0

    # The curve rides along in the site export.
    import json, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "record.json"
        ledger.export_json(conn, p)
        assert json.loads(p.read_text())["curve"][-1]["cum_u"] == 0.0


def test_settle_falls_back_to_snapshot_closes_for_clv():
    """No harvested odds_history close for a live date — the journal must
    fall back to our own recorded line snapshots so CLV still accrues."""
    import datetime as dt
    import tempfile
    from pathlib import Path
    import engine.linemoves as lm
    from engine import db as hist_db
    from engine.models import Prop, GameLog, SportsbookLine, RUSH_YDS

    old_path = lm.HISTORY_PATH
    lm.HISTORY_PATH = Path(tempfile.mkdtemp()) / "hist.jsonl"
    try:
        conn = _conn()
        ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
        ledger.log_recommendations(conn, _result(sport="nfl", date="2026-07-25"))

        # Snapshot the board twice ON the bet date: open 70.5, close 73.5.
        def prop_at(line):
            return Prop("A", "GB", "CHI", "RB", RUSH_YDS, [GameLog(1, "X", 80)],
                        80, None, [SportsbookLine("DraftKings", line, -110, -110)])
        day = dt.datetime(2026, 7, 25, 12, 0).timestamp()
        lm.record_snapshots([prop_at(70.5)], ts=day)
        lm.record_snapshots([prop_at(73.5)], ts=day + 8 * 3600)

        hist = hist_db.connect(":memory:")
        hist_db.upsert_player_logs(hist, [
            {"sport": "nfl", "season": 2026, "period": "2026-07-25",
             "game_id": "A-2026-07-25", "player": "A", "team": "GB",
             "opponent": "CHI", "position": "RB", "home": 1,
             "market": "rush_yds", "value": 85.0}])
        assert ledger.settle_from_history(conn, hist, sport="nfl") == 1
        b = conn.execute("SELECT * FROM bets WHERE player='A'").fetchone()
        # Closing line came from the snapshots; the Over beat the close by 3.
        assert b["closing_line"] == 73.5
        assert abs(ledger.performance(conn)["avg_clv"] - 3.0) < 1e-9
    finally:
        lm.HISTORY_PATH = old_path


def _ls_result(**over):
    base = {
        "sport": "mlb", "date": "2026-07-26",
        "recommendations": [],
        "long_shots": [
            {"player": "Slugger", "market": "home_runs", "book": "FanDuel",
             "odds": 320, "model_prob": 0.24, "ev_per_unit": 0.05,
             "confidence": 5.0, "grade": "Lean"},
        ],
        "longshot_watch": [
            {"player": "Watch Guy", "book": "DraftKings", "odds": 450,
             "model_prob": 0.15, "ev_per_unit": -0.02},
            {"player": "Slugger", "book": "FanDuel", "odds": 320,     # dupe of the pick
             "model_prob": 0.24, "ev_per_unit": 0.05},
            {"player": "Proxy Guy", "book": "proxy", "odds": 400,
             "model_prob": 0.2},                                      # never journaled
        ],
    }
    base.update(over)
    return base


def test_longshots_journal_separately_with_no_bankroll_impact():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    # Picks + watchlist, deduped; proxy prices refused.
    assert ledger.log_longshots(conn, _ls_result()) == 2
    assert ledger.log_longshots(conn, _ls_result()) == 0    # idempotent
    # The main record does not see them at all.
    assert ledger.performance(conn)["open"] == 0
    assert ledger.performance(conn, category="longshot")["open"] == 2

    # Slugger homers (+320 at 0.1u = +0.32u); Watch Guy doesn't (-0.1u).
    ledger.settle(conn, {("Slugger", "home_runs"): 1.0,
                         ("Watch Guy", "home_runs"): 0.0})
    assert ledger.bankroll(conn) == 1000.0                  # zero dollar exposure
    ls = ledger.longshot_report(conn)
    assert ls["wins"] == 1 and ls["losses"] == 1
    assert abs(ls["net_units"] - 0.22) < 1e-9
    # Calibration readout: model avg vs implied vs actual.
    assert abs(ls["avg_model_prob"] - 0.195) < 1e-9
    assert ls["actual_hit_rate"] == 0.5
    assert ls["recent"][0]["player"] in ("Slugger", "Watch Guy")
    # Main performance and curve stay untouched.
    assert ledger.performance(conn)["settled"] == 0
    assert ledger.pnl_curve(conn) == []


def test_home_run_pick_lands_only_in_the_longshot_bucket():
    """Previously a recommended HR prop was journaled twice — once in the
    headline record and once as a long shot. The record is meant to
    describe the picks the model stands behind, so the main copy is gone
    and only the long-shot row remains."""
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-26")
    r["recommendations"][0].update(player="Slugger", market="home_runs",
                                   line=0.5, odds=320)
    assert ledger.log_recommendations(conn, r) == 0
    assert ledger.log_longshots(conn, _ls_result()) == 2
    rows = conn.execute("SELECT category FROM bets WHERE player='Slugger'").fetchall()
    assert [r["category"] for r in rows] == ["longshot"]


def test_category_key_still_admits_both_buckets_for_other_markets():
    """The (…, category) unique key must keep working — a non-long-shot
    market can legitimately appear in both buckets."""
    conn = _conn()
    for cat in ("main", "longshot"):
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,"
            "stake_units,stake_dollars,status,category) VALUES "
            "('mlb','2026-07-26','Dual','total_bases','OVER',1.5,-110,"
            "1.0,10,'open',?)", (cat,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM bets WHERE player='Dual'").fetchone()[0] == 2


def test_migration_adds_category_and_keeps_rows():
    """A pre-category ledger.db upgrades in place: old rows become 'main',
    and the new (…, category) unique key admits longshot rows."""
    import sqlite3, tempfile
    from pathlib import Path
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT,
            side TEXT, line REAL, book TEXT, odds INTEGER,
            projection REAL, hit_prob REAL, edge REAL, confidence REAL, grade TEXT,
            stake_units REAL, stake_dollars REAL,
            status TEXT DEFAULT 'open', actual REAL,
            pnl_units REAL, pnl_dollars REAL, closing_line REAL,
            UNIQUE (sport, date, player, market)
        );""")
    old.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, "
        "odds, stake_units, stake_dollars, status, pnl_units) "
        "VALUES ('t', 'mlb', '2026-07-25', 'Slugger', 'home_runs', 'OVER', 0.5, "
        "'FanDuel', -110, 1.0, 10.0, 'won', 0.909)")
    old.commit(); old.close()

    conn = ledger.connect(path)
    row = conn.execute("SELECT category, status FROM bets").fetchone()
    assert row["category"] == "main" and row["status"] == "won"
    assert ledger.performance(conn)["wins"] == 1
    # Same player/market/date now journals in the longshot bucket too.
    assert ledger.log_longshots(conn, _ls_result(date="2026-07-25")) == 2


def test_summary_renders():
    conn = _conn()
    ledger.log_recommendations(conn, _result())
    ledger.settle(conn, {("A", "rush_yds"): 90.0})
    s = ledger.summary(conn)
    assert "Bankroll" in s and "Win rate" in s and "ROI" in s


def _insert_settled(conn, player, *, status, line=50.5, side="OVER", odds=-110,
                    hit_prob=None, edge=None, closing=None, book="FanDuel",
                    market="rush_yds", stake_dollars=10.0, date="2026-07-20"):
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, "
        "odds, hit_prob, edge, stake_units, stake_dollars, status, "
        "pnl_units, closing_line, category) "
        "VALUES ('t','mlb',?,?,?,?,?,?,?,?,?,1.0,?,?,0,?, 'main')",
        (date, player, market, side, line, book, odds, hit_prob, edge,
         stake_dollars, status, closing))
    conn.commit()


def test_process_grading_judges_the_decision_not_the_result():
    conn = _conn()
    # Won, but the line closed BELOW our over — got lucky.
    _insert_settled(conn, "Lucky", status="won", line=50.5, closing=49.5)
    # Lost, but the close moved our way — good bet, bad night.
    _insert_settled(conn, "Unlucky", status="lost", line=50.5, closing=52.0)
    # An UNDER whose line fell: side-aware, that's a good process bet.
    _insert_settled(conn, "UnderGood", status="won", side="UNDER",
                    line=50.5, closing=49.0)
    # No close known -> ungraded process.
    _insert_settled(conn, "NoClose", status="won", closing=None)

    p = ledger.performance(conn)
    assert p["process"]["good"] == 2 and p["process"]["bad"] == 1
    assert p["process"]["lucky_wins"] == 1
    assert p["process"]["unlucky_losses"] == 1

    recent = {r["player"]: r for r in ledger.recent_settled(conn)}
    assert recent["Lucky"]["process"] == "bad" and recent["Lucky"]["clv"] == -1.0
    assert recent["Unlucky"]["process"] == "good" and recent["Unlucky"]["clv"] == 1.5
    assert recent["UnderGood"]["clv"] == 1.5
    assert recent["NoClose"]["process"] is None and recent["NoClose"]["clv"] is None


def test_calibration_buckets_and_brier_vs_market():
    conn = _conn()
    # Four bets the model called 60%, market fair was 55% (edge stored 0.05).
    # Three hit: realized 75% in the 60–65 bucket.
    for i, st in enumerate(["won", "won", "won", "lost"]):
        _insert_settled(conn, f"P{i}", status=st, hit_prob=0.60, edge=0.05)
    c = ledger.calibration(conn)
    assert c["n"] == 4
    b = next(x for x in c["buckets"] if x["lo"] == 60)
    assert b["n"] == 4 and b["predicted"] == 0.6 and b["actual"] == 0.75
    assert b["ci"] > 0
    # Brier by hand: model mean((0.6-w)^2) = (3*0.16 + 0.36)/4 = 0.21;
    # market fair 0.55 -> (3*0.2025 + 0.3025)/4 = 0.2275. Model wins.
    assert abs(c["brier_model"] - 0.21) < 1e-6
    assert abs(c["brier_market"] - 0.2275) < 1e-6
    assert c["brier_edge"] > 0

    # Pushes and prob-less rows never contaminate the curve.
    _insert_settled(conn, "Pushy", status="push", hit_prob=0.6, edge=0.05)
    _insert_settled(conn, "NoProb", status="won")
    assert ledger.calibration(conn)["n"] == 4


def test_account_health_scores_books_from_own_patterns():
    conn = _conn()
    # SharpBook: 6 bets, always beat the close, all one market, odd stakes.
    for i in range(6):
        _insert_settled(conn, f"S{i}", status="won", book="SharpBook",
                        closing=52.0, stake_dollars=13.37)
    # SoftBook: 6 bets, never beat the close, two markets, round stakes.
    for i in range(6):
        _insert_settled(conn, f"R{i}", status="lost", book="SoftBook",
                        closing=49.0, stake_dollars=25.0,
                        market="rush_yds" if i % 2 else "rec_yds")
    # TinyBook: below the minimum sample — must not be scored at all.
    _insert_settled(conn, "T0", status="won", book="TinyBook")

    h = ledger.account_health(conn)
    assert "disclaimer" in h and "not" in h["disclaimer"]
    books = {b["book"]: b for b in h["books"]}
    assert "TinyBook" not in books
    sharp, soft = books["SharpBook"], books["SoftBook"]
    assert sharp["beat_close_rate"] == 1.0 and soft["beat_close_rate"] == 0.0
    assert sharp["score"] > soft["score"]
    assert sharp["band"] in ("moderate", "elevated") and soft["band"] == "low"
    assert sharp["actions"]          # something concrete to do about it
    # Riskiest book leads the list.
    assert h["books"][0]["book"] == "SharpBook"


def test_longshot_home_runs_settle_from_ingested_logs():
    """The HR board's whole point is measurement, which needs it to grade.
    A journaled home_runs longshot must settle off the same player_game_logs
    the nightly MLB ingest writes — win when he went deep, loss when he
    didn't — without touching the main record's bankroll."""
    from engine import db
    conn = ledger.connect(":memory:")
    hist = db.connect(":memory:")
    result = {
        "sport": "mlb", "date": "2026-07-26",
        "long_shots": [{"player": "Aaron Judge", "market": "home_runs",
                        "odds": 320, "book": "FanDuel", "model_prob": 0.28}],
        "longshot_watch": [{"player": "Mike Trout", "market": "home_runs",
                            "odds": 450, "book": "DraftKings",
                            "model_prob": 0.19}],
    }
    assert ledger.log_longshots(conn, result) == 2
    start_roll = ledger.bankroll(conn)

    # What the nightly ingest writes after the games finish.
    db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-26",
         "player": "Aaron Judge", "team": "NYY", "opponent": "BOS",
         "market": "home_runs", "value": 1.0},
        {"sport": "mlb", "season": 2026, "period": "2026-07-26",
         "player": "Mike Trout", "team": "LAA", "opponent": "SEA",
         "market": "home_runs", "value": 0.0},
    ])
    assert ledger.settle_from_history(conn, hist) == 2

    rows = {r["player"]: r for r in ledger.recent_settled(conn, category="longshot")}
    assert rows["Aaron Judge"]["status"] == "won"
    assert rows["Mike Trout"]["status"] == "lost"
    # Flat 0.1u at +320 → +0.32u; measurement only, zero dollars at risk.
    assert abs(rows["Aaron Judge"]["pnl_units"] - 0.32) < 1e-6
    assert ledger.bankroll(conn) == start_roll
    lr = ledger.longshot_report(conn)
    assert lr["settled"] == 2 and lr["open"] == 0 and lr["wins"] == 1
    assert lr["actual_hit_rate"] == 0.5
    # And none of it leaks into the headline record.
    assert ledger.performance(conn)["settled"] == 0


def test_resize_unstaked_gives_zero_stake_picks_real_pnl():
    """The old grading bug left settled picks staked at 0.00u — wins that
    earned nothing on the record. Resizing them at a flat stake makes the
    profit they produced visible, without pretending dollars were risked."""
    conn = _conn()
    _insert_settled(conn, "ZeroWin", status="won", odds=150, stake_dollars=0)
    _insert_settled(conn, "ZeroLoss", status="lost", odds=-110, stake_dollars=0)
    conn.execute("UPDATE bets SET stake_units=0, pnl_units=0")
    conn.commit()
    # Unstaked rows stay out of the headline record until they're sized.
    p0 = ledger.performance(conn)
    assert p0["settled"] == 0 and p0["unstaked"] == 2

    assert ledger.resize_unstaked(conn, stake_units=0.1) == 2
    p = ledger.performance(conn)
    assert p["settled"] == 2 and p["wins"] == 1 and p["losses"] == 1
    assert p["unstaked"] == 0
    # +150 winner at 0.1u = +0.15u; −110 loser = −0.10u.
    assert abs(p["net_units"] - 0.05) < 1e-6
    assert abs(p["units_staked"] - 0.2) < 1e-6
    # Units only — no dollars were ever at risk, so the bankroll is untouched.
    assert ledger.bankroll(conn) == float(ledger.get_cfg(conn, "starting_bankroll"))


def test_zero_stake_picks_are_never_journaled():
    conn = _conn()
    r = _result()
    r["recommendations"][0]["stake_units"] = 0.0     # Kelly says don't bet
    assert ledger.log_recommendations(conn, r) == 0
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0


def test_longshot_markets_never_enter_the_main_record():
    """A home-run prop that clears the main board's bar still belongs in
    the long-shot bucket — otherwise a night of +650 darts rewrites the
    headline W-L and ROI."""
    conn = _conn()
    res = _result(sport="mlb", date="2026-07-26", recommendations=[
        {"player": "Slugger", "market": "home_runs", "side": "OVER", "line": 0.5,
         "book": "FanDuel", "odds": 650, "hit_prob": 0.16, "edge": 0.034,
         "confidence": 6.9, "grade": "Lean", "stake_units": 0.2,
         "recommended": True},
        {"player": "Contact", "market": "hits", "side": "OVER", "line": 0.5,
         "book": "FanDuel", "odds": -110, "hit_prob": 0.54, "edge": 0.035,
         "confidence": 6.4, "grade": "Play", "stake_units": 0.2,
         "recommended": True},
    ])
    assert ledger.log_recommendations(conn, res) == 1        # only the hits prop
    row = conn.execute("SELECT player, category FROM bets").fetchone()
    assert row["player"] == "Contact" and row["category"] == "main"


def test_repair_moves_legacy_longshots_and_restates_bankroll():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    # Legacy state: an HR prop journaled into main, plus a real main pick.
    _insert_settled(conn, "HRGuy", status="won", market="home_runs", odds=650,
                    stake_dollars=10.0)
    _insert_settled(conn, "RealPick", status="lost", market="hits", odds=-110,
                    stake_dollars=10.0)
    conn.execute("UPDATE bets SET pnl_units=6.5, pnl_dollars=65 WHERE player='HRGuy'")
    conn.execute("UPDATE bets SET pnl_units=-1.0, pnl_dollars=-10 WHERE player='RealPick'")
    conn.commit()
    assert ledger.performance(conn)["settled"] == 2

    assert ledger.move_longshots_out_of_main(conn) == 1
    main, ls = ledger.performance(conn), ledger.longshot_report(conn)
    assert main["settled"] == 1 and main["wins"] == 0     # the HR win is gone
    assert ls["settled"] == 1 and ls["wins"] == 1
    # Re-graded at the flat 0.1u stake: +650 → +0.65u, no dollars.
    assert abs(ls["net_units"] - 0.65) < 1e-6
    # Bankroll restated from the main journal only: 1000 − 10.
    assert ledger.bankroll(conn) == 990.0
    assert ls["avg_odds"] == 650 and ls["by_sport"]["mlb"]["n"] == 1


def test_repair_drops_duplicates_already_in_the_longshot_bucket():
    conn = _conn()
    _insert_settled(conn, "Dup", status="won", market="home_runs", odds=400)
    conn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,"
                 "stake_units,stake_dollars,status,pnl_units,category) VALUES "
                 "('mlb','2026-07-20','Dup','home_runs','OVER',0.5,400,"
                 "0.1,0,'won',0.4,'longshot')")
    conn.commit()
    assert ledger.move_longshots_out_of_main(conn) == 1
    # One row survives, in the long-shot bucket — no double count.
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
    assert ledger.longshot_report(conn)["settled"] == 1
    assert ledger.performance(conn)["settled"] == 0


def test_export_json_carries_calibration_and_health():
    import json, tempfile
    from pathlib import Path
    conn = _conn()
    _insert_settled(conn, "A", status="won", hit_prob=0.6, edge=0.05,
                    closing=52.0)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "record.json"
        ledger.export_json(conn, p)
        d = json.loads(p.read_text())
        assert d["calibration"]["n"] == 1
        assert "books" in d["account_health"]
        assert d["overall"]["process"]["good"] == 1


def test_open_by_day_separates_tonight_from_a_backlog():
    """A single "70 open" hides the only distinction that matters: picks
    from tonight are supposed to be open, picks from a finished day are a
    symptom."""
    conn = _conn()
    for date, cat, n in (("2026-07-27", "main", 12), ("2026-07-27", "longshot", 58),
                         ("2026-07-26", "main", 2), ("2026-07-20", "longshot", 3)):
        for i in range(n):
            conn.execute(
                "INSERT INTO bets (sport, date, player, market, status, category) "
                "VALUES ('mlb', ?, ?, 'total_bases', 'open', ?)",
                (date, f"{date}-{cat}-{i}", cat))
    conn.commit()

    days = ledger.open_by_day(conn, "2026-07-27")
    assert [d["date"] for d in days] == ["2026-07-27", "2026-07-26", "2026-07-20"]
    tonight = days[0]
    assert tonight["stale"] is False
    assert tonight["total"] == 70
    assert tonight["counts"] == {"main": 12, "longshot": 58}
    assert all(d["stale"] for d in days[1:])
    assert sum(d["total"] for d in days if d["stale"]) == 5


def test_open_by_day_is_empty_when_nothing_is_open():
    assert ledger.open_by_day(_conn(), "2026-07-27") == []


def _hist_day(hconn, date, n_games=2, n_final=2, players=()):
    """Seed a slate day: games (some final) plus stat rows for players."""
    for i in range(n_games):
        hconn.execute(
            "INSERT OR REPLACE INTO games (sport, season, period, game_id, home, away, "
            "home_score, away_score) VALUES ('mlb', 2026, ?, ?, 'H', 'A', ?, ?)",
            (date, f"g{i}", 5 if i < n_final else None, 3 if i < n_final else None))
    for p in players:
        hconn.execute(
            "INSERT OR REPLACE INTO player_game_logs (sport, season, period, game_id, "
            "player, market, value) VALUES ('mlb', 2026, ?, ?, ?, 'total_bases', 2)",
            (date, f"{p}-{date}", p))
    hconn.commit()


def test_no_show_on_a_fully_final_day_is_voided():
    """A projected-lineup hitter who never played can never settle. Once
    the day's slate is fully final, the journal mirrors the book: void,
    zero P&L, excluded from every aggregate."""
    from engine import db as hist_db
    conn, hconn = _conn(), hist_db.connect(":memory:")
    _hist_day(hconn, "2026-07-26", n_games=2, n_final=2, players=["Played Guy"])
    for player, cat in (("Sat Out", "longshot"), ("Played Guy", "main")):
        conn.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, odds, "
            "stake_units, stake_dollars, status, category) VALUES ('mlb', "
            "'2026-07-26', ?, 'total_bases', 'OVER', 1.5, -110, 0.1, 1.0, "
            "'open', ?)", (player, cat))
    conn.commit()

    n = ledger.settle_from_history(conn, hconn)
    rows = {r["player"]: r["status"] for r in conn.execute("SELECT player, status FROM bets")}
    assert rows["Sat Out"] == "void"
    assert rows["Played Guy"] == "won"        # 2 > 1.5, settled normally
    assert n == 2                             # one settled + one voided
    void_row = conn.execute("SELECT pnl_units FROM bets WHERE player='Sat Out'").fetchone()
    assert (void_row["pnl_units"] or 0) == 0
    # Voids never reach the record aggregates or the open list.
    assert ledger.performance(conn)["wins"] == 1
    assert ledger.performance(conn)["losses"] == 0
    assert ledger.open_by_day(conn, "2026-07-27") == []


def test_no_show_stays_open_until_the_whole_slate_is_final():
    """One game still in progress = the player might yet appear in the
    ingest (results land per game). Nothing voids early."""
    from engine import db as hist_db
    conn, hconn = _conn(), hist_db.connect(":memory:")
    _hist_day(hconn, "2026-07-26", n_games=2, n_final=1, players=[])
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, stake_dollars, status, category) VALUES ('mlb', "
        "'2026-07-26', 'Sat Out', 'total_bases', 'OVER', 1.5, -110, 0.1, 1.0, "
        "'open', 'longshot')")
    conn.commit()
    ledger.settle_from_history(conn, hconn)
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"


def test_log_longshots_skips_projected_lineups():
    """A projected hitter is a guess about who plays, not a bet. The board
    shows him with the caveat; the journal waits for confirmation."""
    conn = _conn()
    result = {"sport": "mlb", "date": "2026-07-27", "long_shots": [], "longshot_watch": [
        {"player": "Confirmed Guy", "odds": 400, "book": "FanDuel",
         "model_prob": 0.2, "lineup_confirmed": True},
        {"player": "Projected Guy", "odds": 400, "book": "FanDuel",
         "model_prob": 0.2, "lineup_confirmed": False},
        {"player": "Legacy Row No Flag", "odds": 400, "book": "FanDuel",
         "model_prob": 0.2},
    ]}
    n = ledger.log_longshots(conn, result)
    players = {r["player"] for r in conn.execute("SELECT player FROM bets")}
    assert n == 2
    assert players == {"Confirmed Guy", "Legacy Row No Flag"}


def test_nfl_week_bets_settle_from_weekly_logs():
    """An NFL slate journals as '2025-W05'; results land as period '005'
    within a season. The mapping must join BOTH keys — a bare week number
    repeats every season, and joining period alone would grade a 2025 bet
    against a 2024 stat line."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    r = _result(sport="nfl", date="2025-W05")
    r["recommendations"][0].update(
        {"player": "Bijan Robinson", "market": "rush_yds", "side": "OVER",
         "line": 70.5, "odds": 100})
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        # The season that must NOT settle this bet: same week, huge total.
        {"sport": "nfl", "season": 2024, "period": "005", "game_id": "x",
         "player": "Bijan Robinson", "team": "ATL", "opponent": "TB",
         "position": "RB", "home": 1, "market": "rush_yds", "value": 150.0},
        # The right season: 62 rushing yards — the OVER 70.5 loses.
        {"sport": "nfl", "season": 2025, "period": "005", "game_id": "y",
         "player": "Bijan Robinson", "team": "ATL", "opponent": "TB",
         "position": "RB", "home": 1, "market": "rush_yds", "value": 62.0}])

    assert ledger.settle_from_history(conn, hist, sport="nfl") == 1
    b = conn.execute("SELECT * FROM bets WHERE player='Bijan Robinson'").fetchone()
    assert b["status"] == "lost" and b["actual"] == 62.0


def test_nfl_anytime_td_longshots_settle_from_td_rows():
    """The NFL long-shot board journals now that anytime_td rows ingest;
    a settled 1-TD game grades the 0.5-line OVER as a win."""
    from engine import db as hist_db
    conn = _conn()
    result = {"sport": "nfl", "date": "2025-W03", "long_shots": [
        {"player": "Jahmyr Gibbs", "market": "anytime_td", "odds": 150,
         "book": "FanDuel", "model_prob": 0.45}], "longshot_watch": []}
    assert ledger.log_longshots(conn, result) == 1

    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "nfl", "season": 2025, "period": "003", "game_id": "g",
         "player": "Jahmyr Gibbs", "team": "DET", "opponent": "GB",
         "position": "RB", "home": 1, "market": "anytime_td", "value": 1.0}])
    assert ledger.settle_from_history(conn, hist, sport="nfl") == 1
    b = conn.execute("SELECT * FROM bets").fetchone()
    assert b["status"] == "won" and b["category"] == "longshot"


def test_nfl_no_show_voids_only_when_the_week_is_final():
    """A projected player who never appeared in a FULLY final NFL week
    voids, mapped through the same season+period keys."""
    from engine import db as hist_db
    conn = _conn()
    r = _result(sport="nfl", date="2025-W05")
    r["recommendations"][0].update({"player": "Scratched Guy",
                                    "market": "rush_yds"})
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "nfl", "season": 2025, "period": "005", "game_id": "A@B",
         "home": "B", "away": "A", "home_score": 24, "away_score": 20,
         "spread": -3.0, "total": 44.0, "roof": "", "surface": "",
         "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "nfl", "season": 2025, "period": "005", "game_id": "A@B",
         "player": "Someone Else", "team": "B", "opponent": "A",
         "position": "RB", "home": 1, "market": "rush_yds", "value": 80.0}])
    ledger.settle_from_history(conn, hist, sport="nfl")
    b = conn.execute("SELECT status FROM bets WHERE player='Scratched Guy'").fetchone()
    assert b["status"] == "void"


def _stale_result(**over):
    base = {"sport": "mlb", "date": "2026-07-27", "market_scan": {"stale": [
        # Pre-game, settleable: journals.
        {"player": "Cheap Price Guy", "market": "total_bases", "side": "UNDER",
         "line": 1.5, "book": "Caesars", "odds": 110, "date": "2026-07-27",
         "implied": 0.4762, "consensus": 0.531, "gap_pts": 5.48,
         "live": False, "started": False},
        # Started game: an in-play price is stale for invisible reasons.
        {"player": "Started Guy", "market": "hits", "side": "OVER",
         "line": 0.5, "book": "FanDuel", "odds": -140, "date": "2026-07-27",
         "consensus": 0.62, "gap_pts": 1.2, "live": False, "started": True},
        # Un-settleable market: would sit open forever, then void wrongly.
        {"player": "Pitcher Guy", "market": "strikeouts", "side": "OVER",
         "line": 5.5, "book": "BetMGM", "odds": -105, "date": "2026-07-27",
         "consensus": 0.55, "gap_pts": 3.1, "live": False, "started": False},
    ]}}
    base.update(over)
    return base


def test_stale_flags_journal_pregame_settleable_only():
    conn = _conn()
    assert ledger.log_stale_flags(conn, _stale_result()) == 1
    assert ledger.log_stale_flags(conn, _stale_result()) == 0   # idempotent
    rows = conn.execute("SELECT * FROM bets").fetchall()
    assert len(rows) == 1
    b = rows[0]
    assert (b["player"], b["category"], b["side"]) == \
        ("Cheap Price Guy", "stale", "UNDER")
    assert b["stake_dollars"] == 0.0 and b["grade"] == "Stale"


def test_stale_flags_settle_side_aware_and_stay_out_of_the_record():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_stale_flags(conn, _stale_result())
    # UNDER 1.5 total bases; the player posts 1 — the sampler bet wins.
    n = ledger.settle(conn, {("Cheap Price Guy", "total_bases"): 1.0})
    assert n == 1
    st = ledger.stale_report(conn)
    assert st["wins"] == 1 and st["actual_hit_rate"] == 1.0
    assert st["avg_gap_pts"] is not None and st["avg_gap_pts"] > 5
    # Zero dollar stakes: the bankroll and headline record are untouched.
    assert ledger.bankroll(conn) == 1000.0
    assert ledger.performance(conn)["settled"] == 0


def test_export_json_carries_the_stale_sampler(tmp_path=None):
    import json as _json
    import tempfile
    from pathlib import Path
    conn = _conn()
    ledger.log_stale_flags(conn, _stale_result())
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    data = _json.loads(out.read_text())
    assert data["stale_flags"]["open"] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
