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


def test_a_game_bet_graded_off_a_partial_score_is_repaired():
    """The fourth premature-settle cause, end to end at the ledger.

    The NBA schedule parser passed live in-progress scores into the games
    table, so a total graded UNDER off a halftime 97 — and stayed wrong
    forever, because resettle_mismatches exempted team markets on the
    assumption that a scored games row could only ever mean a final. The
    parser is fixed at the source; this pins the second layer: the repair
    pass now audits game bets against the CURRENT games rows, so any grade
    already poisoned by a partial heals the moment the real final lands.
    """
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "nba", "date": "2026-01-15", "recommendations": [],
              "game_bets": [
                  {"bet_type": "total", "recommended": True, "side": "Over",
                   "line": 224.5, "odds": -110, "matchup": "GSW @ LAL",
                   "win_prob": 0.55, "edge": 0.04, "confidence": 5.5,
                   "grade": "Play", "stake_units": 1.0},
                  {"bet_type": "moneyline", "recommended": True,
                   "pick": "GSW", "side": "GSW", "line": 0.5, "odds": 120,
                   "matchup": "GSW @ LAL", "win_prob": 0.55, "edge": 0.05,
                   "confidence": 5.5, "grade": "Play", "stake_units": 1.0},
              ]}
    assert ledger.log_recommendations(conn, result) == 2

    hist = hist_db.connect(":memory:")
    partial = {"sport": "nba", "season": 2026, "period": "2026-01-15",
               "game_id": "GSW@LAL", "home": "LAL", "away": "GSW",
               "home_score": 52, "away_score": 45, "spread": 0.0,
               "total": None, "roof": "dome", "surface": "court",
               "temp": None, "wind": None, "extra": None}
    hist_db.upsert_games(hist, [partial])
    # The halftime score grades both bets — wrongly. Over 224.5 "loses" at
    # 97 combined; the GSW moneyline "loses" at 45-52.
    assert ledger.settle_from_history(conn, hist, sport="nba") == 2
    t = conn.execute("SELECT * FROM bets WHERE market='total'").fetchone()
    m = conn.execute("SELECT * FROM bets WHERE market='moneyline'").fetchone()
    assert t["status"] == "lost" and t["actual"] == 97.0
    assert m["status"] == "lost"

    # The real final lands: 118-113, 231 combined, GSW wins outright.
    hist_db.upsert_games(hist, [{**partial, "home_score": 113,
                                 "away_score": 118}])
    fixed = ledger.resettle_mismatches(conn, hist)
    assert {(f["market"], f["was"], f["now"]) for f in fixed} == {
        ("total", "lost", "won"), ("moneyline", "lost", "won")}
    t = conn.execute("SELECT * FROM bets WHERE market='total'").fetchone()
    m = conn.execute("SELECT * FROM bets WHERE market='moneyline'").fetchone()
    assert t["status"] == "won" and t["actual"] == 231.0
    assert m["status"] == "won" and m["actual"] == 1.0
    # And the bankroll was restated with the corrected P&L, not stacked on
    # top of the wrong one.
    assert ledger.performance(conn)["net_units"] > 0

    # Idempotent: a second pass finds nothing left to fix.
    assert ledger.resettle_mismatches(conn, hist) == []


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


def test_the_watchlist_is_never_journaled():
    """The board's three picks are the record. The watchlist — every
    real-priced homer on the slate — used to journal alongside them at a
    couple of hundred rows a night, which was most of the journal by volume
    and all of the noise in it: every audit, settle pass and stuck-bet
    report came back a wall of names nobody had bet."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    assert ledger.log_longshots(conn, _ls_result()) == 1     # the pick, alone
    assert ledger.log_longshots(conn, _ls_result()) == 0     # idempotent
    assert ledger.performance(conn)["open"] == 0             # never the record
    assert ledger.performance(conn, category="longshot")["open"] == 1
    assert ledger.performance(conn, category="longshot_watch")["open"] == 0
    assert {r["player"] for r in conn.execute("SELECT player FROM bets")} \
        == {"Slugger"}


def test_a_journaled_longshot_still_carries_no_dollar_exposure():
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_longshots(conn, _ls_result())
    ledger.settle(conn, {("Slugger", "home_runs"): 1.0})
    assert ledger.bankroll(conn) == 1000.0
    ls = ledger.longshot_report(conn)
    assert ls["wins"] == 1 and ls["losses"] == 0
    assert abs(ls["net_units"] - 0.32) < 1e-9                # +320 at 0.1u
    assert ls["recent"][0]["player"] == "Slugger"
    # Main performance and curve stay untouched.
    assert ledger.performance(conn)["settled"] == 0
    assert ledger.pnl_curve(conn) == []


def test_split_watch_repairs_a_dart_board_record():
    """The old journal put the whole watchlist in the record bucket. The
    repair moves grade='Watch' rows (settled P&L intact) into the
    calibration bucket, leaving a picks-only record."""
    conn = _conn()
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, "
        "odds, hit_prob, grade, stake_units, stake_dollars, status, pnl_units, "
        "category) VALUES ('t','mlb','2026-07-25','Real Pick','home_runs',"
        "'OVER',0.5,'FanDuel',320,0.24,'Strong Play',0.1,0,'won',0.32,'longshot')")
    for i, status in enumerate(["won", "lost", "lost", "open"]):
        pnl = {"won": 0.45, "lost": -0.1, "open": None}[status]
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, hit_prob, grade, stake_units, stake_dollars, status, "
            "pnl_units, category) VALUES ('t','mlb','2026-07-25',?,"
            "'home_runs','OVER',0.5,'DraftKings',450,0.15,'Watch',0.1,0,?,?,"
            "'longshot')", (f"Dart {i}", status, pnl))
    conn.commit()
    assert ledger.split_watch_from_longshots(conn) == 4
    assert ledger.split_watch_from_longshots(conn) == 0     # no-op once clean
    ls = ledger.longshot_report(conn)
    assert ls["wins"] == 1 and ls["losses"] == 0            # Real Pick only
    assert ls["watch"]["graded"] == 3 and ls["watch"]["open"] == 1
    assert abs(ls["watch"]["net_units"] - 0.25) < 1e-9      # +0.45 - 0.2
    assert ls["calibration_n"] == 4                          # both buckets


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
    assert ledger.log_longshots(conn, _ls_result()) == 1
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
    assert ledger.log_longshots(conn, _ls_result(date="2026-07-25")) == 1


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


def test_log_loss_punishes_the_confident_miss_far_harder_than_brier():
    """Why both proper rules are published rather than the gentler one.

    Nineteen right at 95% and one wrong. Brier charges 0.9025 for the miss,
    log loss charges 3.00 — a factor of more than three. A model that is
    nearly right most nights and catastrophically wrong occasionally reads
    fine on Brier alone, and that is exactly the shape that empties a
    bankroll."""
    import math
    conn = _conn()
    for i in range(19):
        _insert_settled(conn, f"Hit{i}", status="won", hit_prob=0.95, edge=0.05)
    _insert_settled(conn, "Miss", status="lost", hit_prob=0.95, edge=0.05)
    c = ledger.calibration(conn)
    assert c["n"] == 20
    assert abs(c["brier_model"] - (19 * 0.05 ** 2 + 0.95 ** 2) / 20) < 1e-9
    expect_ll = (19 * -math.log(0.95) + -math.log(0.05)) / 20
    assert abs(c["logloss_model"] - round(expect_ll, 4)) < 1e-4
    # The single miss costs 0.90 of Brier and 3.00 of log loss.
    assert 0.95 ** 2 < 1.0 < -math.log(0.05)


def test_log_loss_is_scored_against_the_market_on_the_same_bets():
    """Same comparison Brier already made, or the number is decoration."""
    conn = _conn()
    for i, st in enumerate(("won", "won", "won", "lost")):
        _insert_settled(conn, f"P{i}", status=st, hit_prob=0.60, edge=0.05)
    c = ledger.calibration(conn)
    assert c["logloss_market"] is not None
    assert c["logloss_edge"] == round(c["logloss_market"] - c["logloss_model"], 4)


def test_log_loss_is_clamped_so_one_row_cannot_swallow_the_score():
    """A 0% forecast on something that happened costs infinity under the raw
    rule, which would turn an honesty metric into a single-row lottery."""
    import math
    conn = _conn()
    _insert_settled(conn, "Impossible", status="won", hit_prob=0.0, edge=0.05)
    c = ledger.calibration(conn)
    assert c["logloss_model"] is not None
    assert math.isfinite(c["logloss_model"])
    assert c["logloss_model"] == round(-math.log(ledger.LOGLOSS_CLAMP), 4)


def test_ece_is_zero_on_a_perfectly_calibrated_book():
    conn = _conn()
    # 60% claimed, 60% realized — ten bets, six winners, one bucket.
    for i in range(10):
        _insert_settled(conn, f"C{i}", status="won" if i < 6 else "lost",
                        hit_prob=0.60, edge=0.05)
    assert ledger.calibration(conn)["ece"] == 0.0


def test_ece_weights_buckets_by_population():
    """A five-bet bucket miles off the diagonal must not outvote a large one
    sitting on it. Ten bets at 60% that hit 60% (error 0), plus two bets at
    20% that both hit (error 0.80) -> 2/12 * 0.80 = 0.1333."""
    conn = _conn()
    for i in range(10):
        _insert_settled(conn, f"Big{i}", status="won" if i < 6 else "lost",
                        hit_prob=0.60, edge=0.05)
    for i in range(2):
        _insert_settled(conn, f"Small{i}", status="won", hit_prob=0.20, edge=0.05)
    c = ledger.calibration(conn)
    assert abs(c["ece"] - (2 / 12) * 0.80) < 1e-3
    # And the unweighted average would have been 0.40 — three times higher.
    assert c["ece"] < 0.20


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


def test_product_mix_is_a_different_signal_from_concentration():
    """The reason both are scored, stated as the case that separates them.

    An account spread evenly across eight prop markets scores CLEAN on
    concentration — no single market is more than an eighth of it — while
    being exactly the all-props profile that gets limited first. One book
    does that; the other puts the same volume through main lines, equally
    unconcentrated. Concentration cannot tell them apart. Mix can."""
    conn = _conn()
    props = ["hits", "home_runs", "total_bases", "strikeouts",
             "rush_yds", "rec_yds", "receptions", "pass_yds"]
    for i, m in enumerate(props * 2):
        _insert_settled(conn, f"P{i}", status="won", book="AllProps",
                        market=m, closing=52.0, stake_dollars=25.0)
    for i, m in enumerate((["moneyline", "total", "spread", "team_total"] * 4)):
        _insert_settled(conn, f"M{i}", status="won", book="MainLines",
                        market=m, closing=52.0, stake_dollars=25.0)

    books = {b["book"]: b for b in ledger.account_health(conn)["books"]}
    ap, ml = books["AllProps"], books["MainLines"]
    assert ap["prop_share"] == 1.0 and ml["prop_share"] == 0.0
    # Concentration genuinely cannot separate them — same bets per market.
    assert abs(ap["concentration"] - 0.125) < 1e-9
    assert abs(ml["concentration"] - 0.25) < 1e-9
    # ...yet the all-props book scores higher, and the gap is the mix weight.
    assert ap["score"] > ml["score"]
    assert any("player props" in d for d in ap["drivers"])
    assert any("main lines" in d for d in ml["drivers"])


def test_the_all_props_advice_is_not_given_twice():
    """Concentration and mix can both fire on one book, and both want to say
    'add main lines'. Saying it in two sentences reads as a bug."""
    conn = _conn()
    for i in range(10):
        _insert_settled(conn, f"H{i}", status="won", book="OneMarket",
                        market="home_runs", closing=52.0, stake_dollars=25.0)
    b = ledger.account_health(conn)["books"][0]
    assert b["concentration"] == 1.0 and b["prop_share"] == 1.0
    mainline_advice = [a for a in b["actions"] if "main" in a or "sides" in a]
    assert len(mainline_advice) == 1, mainline_advice


def test_the_score_names_what_it_cannot_see():
    """Four of the seven signals a risk desk uses are not in this number.
    Dropping them silently implies a completeness the score doesn't have."""
    h = ledger.account_health(_conn())
    spots = {s["signal"] for s in h["blind_spots"]}
    assert len(spots) == 4
    assert any("timing" in s for s in spots)
    assert any("Promo" in s for s in spots)
    # And the device/fingerprint one is a DECISION, not a limitation — the
    # guardrail belongs on the page, not only in the docs.
    device = next(s for s in h["blind_spots"] if "Device" in s["signal"])
    assert "fraud" in device["why"]


def test_the_health_weights_still_sum_to_one_hundred():
    """The score is read as a 0–100 and banded at 35/65. Weights that no
    longer total 100 would silently move every band."""
    assert (ledger.HEALTH_W_CLV + ledger.HEALTH_W_CONCENTRATION
            + ledger.HEALTH_W_PROP_MIX + ledger.HEALTH_W_STAKES
            + ledger.HEALTH_W_VOLUME) == 100


def test_the_game_market_list_has_exactly_one_definition():
    """The settler uses it to decide whether to look for a games row or a
    player log; account_health uses it to score mix. A second copy would
    drift the day a market is added, and fail silently in both places."""
    src = open(ledger.__file__, encoding="utf-8").read()
    assert src.count('"moneyline", "total", "spread"') == 1
    assert "GAME_MARKETS = (" in src
    assert src.count("in GAME_MARKETS") >= 2


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
                        "odds": 320, "book": "FanDuel", "model_prob": 0.28},
                       {"player": "Mike Trout", "market": "home_runs",
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

    picks = {r["player"]: r for r in ledger.recent_settled(conn, category="longshot")}
    assert picks["Aaron Judge"]["status"] == "won"
    assert picks["Mike Trout"]["status"] == "lost"
    # Flat 0.1u at +320 → +0.32u; measurement only, zero dollars at risk.
    assert abs(picks["Aaron Judge"]["pnl_units"] - 0.32) < 1e-6
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


def test_the_repair_runs_itself_on_every_settle_pass():
    """"Make sure they only go under the long shot record" cannot depend
    on a human remembering --repair-journal. The journal gate refuses
    long-shot markets at the door, and BOTH settle passes now sweep any
    stray back out — main is self-healing, not merely defended."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fname in ("launch.py", os.path.join("engine", "maintenance.py")):
        src = open(os.path.join(root, fname), encoding="utf-8").read()
        # In the settle path, not just the manual repair flag.
        i = src.index("relabel_cross_league")
        assert "move_longshots_out_of_main" in src[i:i + 1600], \
            f"{fname}: the stray sweep is not beside the settle repairs"


def test_the_restated_view_is_main_only_like_the_headline():
    """The restated record answers "what would OUR record read at today's
    sizing" — and "our record" is the main bucket, exactly as
    performance() defines it. Blending the long-shot dimes back in would
    re-create the pollution the buckets exist to prevent."""
    conn = _conn()
    _insert_settled(conn, "MainWin", status="won", market="hits", odds=-110)
    conn.execute("UPDATE bets SET hit_prob=0.57 WHERE player='MainWin'")
    conn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,"
                 "hit_prob,stake_units,stake_dollars,status,pnl_units,"
                 "category) VALUES ('mlb','2026-07-20','Dart','home_runs',"
                 "'OVER',0.5,400,0.24,0.1,0,'won',0.4,'longshot')")
    conn.commit()
    r = ledger.restated_performance(conn)
    assert r["settled"] == 1 and r["wins"] == 1, \
        "the long-shot dart leaked into the restated main record"


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
    result = {"sport": "mlb", "date": "2026-07-27", "long_shots": [
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


def test_era_report_splits_the_record_at_the_retune():
    """Losses earned by gates that no longer exist stay in their own era;
    the current era starts clean at the re-tune date and reports its own
    W-L / ROI / per-sport split."""
    conn = _conn()
    _insert_settled(conn, "Old Guy", status="lost", date="2026-07-20")
    _insert_settled(conn, "Old Guy 2", status="won", odds=100, date="2026-07-25")
    _insert_settled(conn, "New Guy", status="won", odds=100, date="2026-07-30")
    # The fixture leaves pnl_units at 0 — give the eras real P&L to split.
    conn.execute("UPDATE bets SET pnl_units=-1.0 WHERE player='Old Guy'")
    conn.execute("UPDATE bets SET pnl_units=1.0 WHERE player='New Guy'")
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, stake_dollars, status, category) VALUES ('mlb', "
        "'2026-07-30', 'Open Guy', 'total_bases', 'OVER', 1.5, -110, 0.5, 5, "
        "'open', 'main')")
    conn.commit()
    er = ledger.era_report(conn)
    assert er["current"] == "v2"
    v1, v2 = er["eras"]
    assert (v1["wins"], v1["losses"]) == (1, 1)
    assert (v2["wins"], v2["losses"]) == (1, 0)
    assert v2["open"] == 1
    assert v2["net_units"] > 0
    assert v1["to"] == "2026-07-29" and v2["from"] == "2026-07-29"
    assert "nfl" in v1["by_sport"] or "mlb" in v1["by_sport"]


def _dh_hist(final2=True):
    """History DB for a Braves@Mets doubleheader day: leg 1 final 4-2,
    leg 2 final 7-1 (or still open); the hitter went 0 TB in leg 1 and
    3 TB in leg 2."""
    from engine import db as hist_db
    hist = hist_db.connect(":memory:")
    games = [{"sport": "mlb", "season": 2026, "period": "2026-07-29",
              "game_id": "ATL@NYM", "home": "NYM", "away": "ATL",
              "home_score": 4, "away_score": 2, "spread": 0.0, "total": None,
              "roof": "", "surface": "", "temp": None, "wind": None,
              "extra": None},
             {"sport": "mlb", "season": 2026, "period": "2026-07-29",
              "game_id": "ATL@NYM-G2", "home": "NYM", "away": "ATL",
              "home_score": 7 if final2 else None,
              "away_score": 1 if final2 else None, "spread": 0.0,
              "total": None, "roof": "", "surface": "", "temp": None,
              "wind": None, "extra": None}]
    hist_db.upsert_games(hist, games)
    logs = [{"sport": "mlb", "season": 2026, "period": "2026-07-29",
             "game_id": "DH Guy-2026-07-29", "player": "DH Guy",
             "team": "NYM", "opponent": "ATL", "position": "C", "home": 1,
             "market": "total_bases", "value": 0.0}]
    if final2:
        logs.append({**logs[0], "game_id": "DH Guy-2026-07-29-G2",
                     "value": 3.0})
    hist_db.upsert_player_logs(hist, logs)
    return hist


def test_dh_prop_bet_grades_against_its_own_leg():
    """A bet that KNOWS its doubleheader leg settles on that game's stat
    line — 0 TB in leg 1 must not grade a leg-2 bet."""
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-29")
    r["recommendations"][0].update(player="DH Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100,
                                   doubleheader=True, game_number=2)
    ledger.log_recommendations(conn, r)
    assert conn.execute("SELECT leg FROM bets").fetchone()["leg"] == 2
    assert ledger.settle_from_history(conn, _dh_hist(), sport="mlb") == 1
    b = conn.execute("SELECT status, actual FROM bets").fetchone()
    assert b["status"] == "won" and b["actual"] == 3.0    # leg 2's line


def test_legacy_ambiguous_dh_bet_voids_only_when_day_final():
    """A pre-leg bet whose two legs disagree: while any leg runs it stays
    open; once the day is fully final it VOIDS — grading it against a
    coin-flip choice of game would be invention."""
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-29")
    r["recommendations"][0].update(player="DH Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)
    # Leg 2 still running → 0 TB (leg 1) is not evidence — stays open.
    assert ledger.settle_from_history(conn, _dh_hist(final2=False),
                                      sport="mlb") == 0
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"
    # Day fully final, outcomes differ (0 vs 3 TB on a 1.5 line) → void.
    ledger.settle_from_history(conn, _dh_hist(), sport="mlb")
    b = conn.execute("SELECT status, pnl_units FROM bets").fetchone()
    assert b["status"] == "void" and b["pnl_units"] == 0


def test_tonights_bet_does_not_grade_against_a_game_nobody_has_played():
    """The Record page showed props marked LOST for games that had not
    started.

    The old guard asked "is there a game row without a final score?" — but
    parse_results only writes games that FINISHED, so a game yet to start
    has no row at all. The guard abstained on exactly the case it existed
    to catch, and the settler graded tonight's props against a stat line of
    zeros: every UNDER a winner, every OVER a loser, hours before first
    pitch. Today the burden of proof runs the other way.
    """
    from engine import db as hist_db
    import datetime as _dt
    today = _dt.date.today().isoformat()
    conn = _conn()
    r = _result(sport="mlb", date=today)
    r["recommendations"][0].update(player="Tonight Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)
    hist = hist_db.connect(":memory:")
    # A zeroed line for a game with no games row — first pitch is hours off.
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": int(today[:4]), "period": today,
         "game_id": f"Tonight Guy-{today}", "player": "Tonight Guy",
         "team": "NYM", "opponent": "ATL", "position": "C", "home": 1,
         "market": "total_bases", "value": 0.0}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 0
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"

    # Once the game is final and ingested, the same call grades it.
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": int(today[:4]), "period": today,
         "game_id": "ATL@NYM", "home": "NYM", "away": "ATL",
         "home_score": 4, "away_score": 2, "spread": 0.0, "total": None,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "lost"


def test_tonights_bet_never_grades_against_last_nights_stat_line():
    """The hole the first fix left open, and the one that kept the bug alive.

    Two mechanisms leave a bet with no stat row on its own date. The
    date-shape drift (a 9pm Eastern game filed under yesterday in UTC) wants
    the neighbour-day fallback; the ingest's withholding guard — which holds
    back today's rows precisely BECAUSE the game has not been played — must
    not get it. Nothing distinguished them, and the second case happens every
    single evening: today withheld by design, the player logged yesterday
    because baseball teams play most days. The fallback then graded tonight's
    bet against last night's line, hours before first pitch.
    """
    from engine import db as hist_db
    import datetime as _dt
    today = _dt.date.today().isoformat()
    y = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    conn = _conn()
    r = _result(sport="mlb", date=today)
    r["recommendations"][0].update(player="Tonight Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    # Yesterday: played and final, 0 total bases. Today: the slate is on the
    # board with no score yet, and the stat row is correctly withheld.
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "ATL@NYM",
         "home": "NYM", "away": "ATL", "home_score": 4, "away_score": 2,
         "spread": 0.0, "total": None, "roof": "", "surface": "", "temp": None,
         "wind": None, "extra": None},
        {"sport": "mlb", "season": 2026, "period": today,
         "game_id": "PHI@NYM", "home": "NYM", "away": "PHI",
         "home_score": None, "away_score": None, "spread": 0.0, "total": None,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "g-y",
         "player": "Tonight Guy", "team": "NYM", "opponent": "ATL",
         "position": "C", "home": 1, "market": "total_bases", "value": 0.0}])

    assert ledger.settle_from_history(conn, hist, sport="mlb") == 0
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"


def test_the_neighbour_day_repair_still_works_when_the_team_is_idle():
    """The control. Kill the fallback outright and the UTC date-shape bug it
    was built for comes straight back — thirty home-run bets dated 07-27
    whose players are all logged on 07-26. It must still fire when the
    team has no unfinished game on the bet's own date."""
    from engine import db as hist_db
    import datetime as _dt
    today = _dt.date.today().isoformat()
    y = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    conn = _conn()
    r = _result(sport="mlb", date=today)
    r["recommendations"][0].update(player="Skew Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    # The game was played last night; the team is NOT on today's slate — but
    # today's slate IS on the board, which is what makes "this team has no
    # game today" a fact rather than an absence of information.
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "ATL@NYM",
         "home": "NYM", "away": "ATL", "home_score": 4, "away_score": 2,
         "spread": 0.0, "total": None, "roof": "", "surface": "", "temp": None,
         "wind": None, "extra": None},
        {"sport": "mlb", "season": 2026, "period": today,
         "game_id": "SD@LAD", "home": "LAD", "away": "SD",
         "home_score": None, "away_score": None, "spread": 0.0, "total": None,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "g-y",
         "player": "Skew Guy", "team": "NYM", "opponent": "ATL",
         "position": "C", "home": 1, "market": "total_bases", "value": 3.0}])

    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "won"


def test_a_day_we_cannot_see_is_never_treated_as_a_quiet_day():
    """The hole the 152-row audit exposed. The team-is-playing check reads
    the games table for the bet's own date — so if that day's slate was
    never ingested, "no unfinished game" means "no information", and
    reaching back a day would grade tonight's bet off last night again by a
    different route. Inside the strict window, unknown is not permission."""
    from engine import db as hist_db
    import datetime as _dt
    today = _dt.date.today().isoformat()
    y = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    conn = _conn()
    r = _result(sport="mlb", date=today)
    r["recommendations"][0].update(player="Blind Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)
    hist = hist_db.connect(":memory:")
    # Yesterday final and ingested; TODAY has no games rows at all.
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "ATL@NYM",
         "home": "NYM", "away": "ATL", "home_score": 4, "away_score": 2,
         "spread": 0.0, "total": None, "roof": "", "surface": "", "temp": None,
         "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": y, "game_id": "g-y",
         "player": "Blind Guy", "team": "NYM", "opponent": "ATL",
         "position": "C", "home": 1, "market": "total_bases", "value": 0.0}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 0
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"


def test_a_settled_past_date_with_no_games_rows_still_grades():
    """The control for the guard above. Backfilled player logs predate the
    games table for whole seasons; requiring a final there would strand
    every one of those bets as open forever."""
    from engine import db as hist_db
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-24")
    r["recommendations"][0].update(player="Old Guy", market="total_bases",
                                   side="OVER", line=1.5, odds=100)
    ledger.log_recommendations(conn, r)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "g", "player": "Old Guy", "team": "NYM",
         "opponent": "ATL", "position": "C", "home": 1,
         "market": "total_bases", "value": 3.0}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "won"


def test_dh_moneyline_grades_against_its_own_game():
    """Team markets had the same collapse: both legs shared one games row.
    With per-leg rows, a leg-2 moneyline grades on game 2's score, and a
    legacy bet settles when both legs agree."""
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-29")
    r["recommendations"] = []
    r["game_bets"] = [{"recommended": True, "bet_type": "moneyline",
                       "pick": "NYM", "odds": -120, "stake_units": 0.5,
                       "grade": "Strong Play", "doubleheader": True,
                       "game_number": 2}]
    ledger.log_recommendations(conn, r)
    assert conn.execute("SELECT leg FROM bets").fetchone()["leg"] == 2
    assert ledger.settle_from_history(conn, _dh_hist(), sport="mlb") == 1
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "won"
    # Legacy (no leg): NYM won BOTH legs — identical outcome settles it.
    conn2 = _conn()
    r["game_bets"][0] = {"recommended": True, "bet_type": "moneyline",
                         "pick": "NYM", "odds": -120, "stake_units": 0.5,
                         "grade": "Strong Play"}
    ledger.log_recommendations(conn2, r)
    assert ledger.settle_from_history(conn2, _dh_hist(), sport="mlb") == 1
    assert conn2.execute("SELECT status FROM bets").fetchone()["status"] == "won"


def test_dh_slate_ingest_keeps_both_legs():
    """The root collapse: both legs' stat lines shared one game_id and the
    second overwrote the first — the settler then graded against whichever
    survived. Same-date entries now get -G{n} suffixes and BOTH persist."""
    from types import SimpleNamespace as NS
    from engine import db as hist_db
    from engine.ingest import mlb_rows_from_slate
    weather = NS(temp_f=75.0, wind_mph=5.0)
    g1 = NS(home="NYM", away="ATL", park="citi field", total=8.5,
            weather=weather, live=NS(state="final"), game_number=1)
    g2 = NS(home="NYM", away="ATL", park="citi field", total=7.5,
            weather=weather, live=NS(state="final"), game_number=2)
    p = NS(player="DH Guy", team="NYM", position="C", market="total_bases",
           logs=[NS(date="2026-07-29", game=1, opponent="ATL", home=True,
                    value=0.0),
                 NS(date="2026-07-29", game=2, opponent="ATL", home=True,
                    value=3.0)])
    grows, prows = mlb_rows_from_slate(NS(games=[g1, g2], props=[p]),
                                       "2026-07-29")
    assert [r["game_id"] for r in grows] == ["ATL@NYM", "ATL@NYM-G2"]
    assert [r["game_id"] for r in prows] == \
        ["DH Guy-2026-07-29", "DH Guy-2026-07-29-G2"]
    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, prows)
    assert hist.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == 2


def test_calibration_since_scopes_to_the_current_era():
    """The all-time chart mixes retired gates with tonight's model; the
    since= filter judges the current era on its own picks only."""
    conn = _conn()
    _insert_settled(conn, "Old Miss", status="lost", hit_prob=0.60,
                    edge=0.05, date="2026-07-20")
    _insert_settled(conn, "New Hit", status="won", hit_prob=0.60,
                    edge=0.05, date="2026-07-30")
    all_time = ledger.calibration(conn)
    era = ledger.calibration(conn, since="2026-07-29")
    assert all_time["n"] == 2 and all_time["since"] is None
    assert era["n"] == 1 and era["since"] == "2026-07-29"
    assert era["buckets"][0]["actual"] == 1.0     # only the new pick counts


def test_partial_stat_lines_never_settle_a_live_game():
    """The premature-settle bug: MLB's game-log API includes an in-progress
    game's partial line, and one ingested partial row graded tonight's bet
    "lost" in the 4th inning. When the games table says the team's game has
    no final score yet, the settler must leave the bet open."""
    from engine import db as hist_db
    conn = _conn()
    r = _result(sport="mlb", date="2026-07-29")
    r["recommendations"][0].update(player="Austin Wells", market="total_bases",
                                   side="OVER", line=0.5, odds=100)
    ledger.log_recommendations(conn, r)

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "NYY@CHW", "home": "CHW", "away": "NYY",
         "home_score": None, "away_score": None,      # still in progress
         "spread": 0.0, "total": 8.5, "roof": "", "surface": "",
         "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "w", "player": "Austin Wells", "team": "NYY",
         "opponent": "CHW", "position": "C", "home": 0,
         "market": "total_bases", "value": 0.0}])      # partial: 0 TB so far
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 0
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "open"

    # Game goes final: score lands, the stat row updates — NOW it settles.
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "NYY@CHW", "home": "CHW", "away": "NYY",
         "home_score": 2, "away_score": 5, "spread": 0.0, "total": 8.5,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "w", "player": "Austin Wells", "team": "NYY",
         "opponent": "CHW", "position": "C", "home": 0,
         "market": "total_bases", "value": 2.0}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    b = conn.execute("SELECT status, actual FROM bets").fetchone()
    assert b["status"] == "won" and b["actual"] == 2.0


def test_resettle_fixes_bets_graded_off_partial_stats():
    """The user-facing repair: a bet already marked "lost" at 0 total bases
    mid-game flips to "won" (with P&L and bankroll restated) once the final
    number lands. Clean journals are a no-op."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, "
        "odds, stake_units, stake_dollars, status, actual, pnl_units, "
        "pnl_dollars, category) VALUES ('t','mlb','2026-07-29','Austin Wells',"
        "'total_bases','OVER',0.5,'BetMGM',100,0.1,1.0,'lost',0.0,-0.1,-1.0,"
        "'main')")
    conn.commit()

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "NYY@CHW", "home": "CHW", "away": "NYY",
         "home_score": 2, "away_score": 5, "spread": 0.0, "total": 8.5,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "w", "player": "Austin Wells", "team": "NYY",
         "opponent": "CHW", "position": "C", "home": 0,
         "market": "total_bases", "value": 2.0}])
    fixed = ledger.resettle_mismatches(conn, hist)
    assert [(f["was"], f["now"]) for f in fixed] == [("lost", "won")]
    b = conn.execute("SELECT * FROM bets").fetchone()
    assert b["status"] == "won" and b["actual"] == 2.0
    assert abs(b["pnl_units"] - 0.1) < 1e-9        # +100 at 0.1u
    assert abs(b["pnl_dollars"] - 1.0) < 1e-9
    assert ledger.bankroll(conn) == 1001.0         # restated, not stacked
    assert ledger.resettle_mismatches(conn, hist) == []   # idempotent


def test_resettle_waits_while_the_game_is_still_running():
    """The repair must not "fix" a grade using another partial line — an
    unfinished game's numbers aren't evidence in either direction."""
    from engine import db as hist_db
    conn = _conn()
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, "
        "odds, stake_units, stake_dollars, status, actual, pnl_units, "
        "pnl_dollars, category) VALUES ('t','mlb','2026-07-29','Austin Wells',"
        "'total_bases','OVER',0.5,'BetMGM',100,0.1,1.0,'lost',0.0,-0.1,-1.0,"
        "'main')")
    conn.commit()
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "NYY@CHW", "home": "CHW", "away": "NYY",
         "home_score": None, "away_score": None, "spread": 0.0, "total": 8.5,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-29",
         "game_id": "w", "player": "Austin Wells", "team": "NYY",
         "opponent": "CHW", "position": "C", "home": 0,
         "market": "total_bases", "value": 1.0}])     # partial again
    assert ledger.resettle_mismatches(conn, hist) == []
    assert conn.execute("SELECT status FROM bets").fetchone()["status"] == "lost"


def test_slate_ingest_withholds_same_day_rows_for_teams_in_play():
    """Layer zero of the premature-settle fix: a live slate's game-log rows
    for TODAY are only written once the team's day is final — MLB's API
    includes the in-progress game with partial stats."""
    from types import SimpleNamespace as NS
    from engine.ingest import mlb_rows_from_slate
    weather = NS(temp_f=75.0, wind_mph=5.0)
    g = NS(home="NYY", away="CHW", park="Yankee Stadium", total=8.5,
           weather=weather, live=NS(state="live"))
    p = NS(player="Austin Wells", team="NYY", position="C",
           market="total_bases",
           logs=[NS(date="2026-07-29", game=1, opponent="CHW", home=True,
                    value=0.0),
                 NS(date="2026-07-27", game=2, opponent="BOS", home=False,
                    value=2.0)])
    _, prows = mlb_rows_from_slate(NS(games=[g], props=[p]), "2026-07-29")
    assert [r["period"] for r in prows] == ["2026-07-27"]
    # Once the game is final the same-day row flows through.
    g.live = NS(state="final")
    _, prows = mlb_rows_from_slate(NS(games=[g], props=[p]), "2026-07-29")
    assert "2026-07-29" in [r["period"] for r in prows]


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


def test_spread_and_team_total_picks_journal_and_settle():
    """The last unjournaled game-bet types. A -3.5 favorite covering by 4
    wins, covering by exactly the number would push, and a team total
    grades against the team's own score."""
    from engine import db as hist_db
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "mlb", "date": "2026-07-28", "game_bets": [
        {"bet_type": "spread", "team": "NYY", "line": -1.5, "odds": 120,
         "matchup": "BOS @ NYY", "recommended": True, "grade": "Play",
         "stake_units": 0.5, "win_prob": 0.55, "edge": 0.04,
         "confidence": 6.5, "book": "DK"},
        {"bet_type": "team_total", "team": "BOS", "side": "Under",
         "line": 4.5, "odds": -110, "matchup": "BOS @ NYY",
         "recommended": True, "grade": "Lean", "stake_units": 0.3,
         "win_prob": 0.54, "edge": 0.03, "confidence": 6.0, "book": "FD"},
    ]}
    assert ledger.log_recommendations(conn, result) == 2

    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-28",
         "game_id": "BOS@NYY", "home": "NYY", "away": "BOS",
         "home_score": 6, "away_score": 3, "spread": -1.5, "total": 8.5,
         "roof": "", "surface": "", "temp": None, "wind": None,
         "extra": None}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 2
    spread = conn.execute(
        "SELECT * FROM bets WHERE market='spread'").fetchone()
    # NYY won by 3 laying 1.5 — covers (actual margin 3 > stored line 1.5).
    assert spread["status"] == "won" and spread["actual"] == 3.0
    tt = conn.execute(
        "SELECT * FROM bets WHERE market='team_total'").fetchone()
    # BOS scored 3; Under 4.5 wins.
    assert tt["status"] == "won" and tt["actual"] == 3.0


def test_spread_lands_exactly_on_the_number_pushes():
    from engine import db as hist_db
    conn = _conn()
    result = {"sport": "mlb", "date": "2026-07-28", "game_bets": [
        {"bet_type": "spread", "team": "SD", "line": -2.0, "odds": -105,
         "matchup": "SD @ LAD", "recommended": True, "grade": "Play",
         "stake_units": 0.5, "confidence": 6.5, "edge": 0.03}]}
    ledger.log_recommendations(conn, result)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-28",
         "game_id": "SD@LAD", "home": "LAD", "away": "SD",
         "home_score": 3, "away_score": 5, "spread": 2.0, "total": 8.0,
         "roof": "", "surface": "", "temp": None, "wind": None,
         "extra": None}])
    ledger.settle_from_history(conn, hist, sport="mlb")
    b = conn.execute("SELECT * FROM bets").fetchone()
    assert b["status"] == "push" and b["pnl_units"] == 0.0


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


def test_nba_stale_flags_journal_and_settle_from_boxscores():
    """NBA joins the sampler: an ISO-dated flag settles straight against
    the ingested boxscore log for that date."""
    from engine import db as hist_db
    conn = _conn()
    result = {"sport": "nba", "date": "2026-01-15", "market_scan": {"stale": [
        {"player": "Nikola Jokic", "market": "reb", "side": "OVER",
         "line": 12.5, "book": "FanDuel", "odds": 105, "consensus": 0.55,
         "gap_pts": 3.0, "live": False, "started": False}]}}
    assert ledger.log_stale_flags(conn, result) == 1

    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "nba", "season": 2026, "period": "2026-01-15",
         "game_id": "g", "player": "Nikola Jokic", "team": "DEN",
         "opponent": "LAL", "position": "S", "home": 1,
         "market": "reb", "value": 14.0}])
    assert ledger.settle_from_history(conn, hist, sport="nba") == 1
    b = conn.execute("SELECT * FROM bets").fetchone()
    assert b["status"] == "won" and b["category"] == "stale"


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



def test_near_miss_sampler_journals_and_reports():
    """The looser-gates sampler: near-misses journal at flat stake in
    category='loose', settle from actuals, and report their own ROI —
    never touching the headline record."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    result = {"sport": "mlb", "date": "2026-07-30", "near_miss": [
        {"player": "Close Call", "market": "total_bases", "side": "OVER",
         "line": 1.5, "odds": -110, "book": "FanDuel", "edge": 0.024,
         "quality": 66.0, "hit_prob": 0.55, "grade": "B"},
        {"player": "HR Guy", "market": "home_runs", "side": "OVER",
         "line": 0.5, "odds": 300, "book": "FanDuel"},   # not settleable here
        {"player": "Proxy Guy", "market": "hits", "side": "OVER",
         "line": 0.5, "odds": -110, "book": "proxy"},    # refused
    ]}
    assert ledger.log_near_misses(conn, result) == 1
    assert ledger.log_near_misses(conn, result) == 0     # idempotent
    ledger.settle(conn, {("Close Call", "total_bases"): 2.0})
    lo = ledger.loose_report(conn)
    assert lo["wins"] == 1 and lo["losses"] == 0
    assert ledger.performance(conn)["settled"] == 0      # headline untouched
    assert ledger.bankroll(conn) == 1000.0               # zero exposure


def test_near_misses_pick_only_the_just_under_bar():
    """Selection: real-priced Tier 1/2 close to the bar only — comfortable
    passes, structural failures, and HR quarantine are all excluded."""
    from engine.mlb.pipeline import near_misses
    rows = [
        {"recommended": True, "player": "Picked", "market": "hits",
         "tier": 2, "edge": 0.05, "quality": 90},
        {"recommended": False, "player": "Near Edge", "market": "total_bases",
         "market_label": "Total Bases", "side": "OVER", "line": 1.5,
         "odds": -110, "book": "FanDuel", "tier": 2, "edge": 0.025,
         "quality": 80, "hit_prob": 0.55, "grade": "B"},
        {"recommended": False, "player": "Near Quality", "market": "hits",
         "market_label": "Hits", "side": "OVER", "line": 0.5, "odds": -105,
         "book": "BetMGM", "tier": 2, "edge": 0.04, "quality": 63,
         "hit_prob": 0.6, "grade": "B"},
        {"recommended": False, "player": "Way Off", "market": "hits",
         "tier": 2, "edge": 0.005, "quality": 30, "book": "FanDuel"},
        {"recommended": False, "player": "HR Dart", "market": "home_runs",
         "tier": 3, "edge": 0.05, "quality": 80, "book": "FanDuel"},
        {"recommended": False, "player": "No Price", "market": "hits",
         "tier": 2, "edge": 0.028, "quality": 75, "has_market": False},
    ]
    nm = near_misses(rows)
    assert [r["player"] for r in nm] == ["Near Quality", "Near Edge"]
    assert "edge 2.5%" in nm[1]["missed_by"]
    assert "quality 63/70" in nm[0]["missed_by"]


def test_the_breakeven_comes_from_the_prices_actually_taken():
    """The record page printed "break-even ≈ 52.4% at −110" beside the win
    rate, whatever the book was made of.

    That is the right number only for a book of −110s. This journal buys
    short prices: its real bar is near 58%, so a 47.0% win rate read as
    five points short when it was ten — the site flattering the record on
    the one figure a bettor checks first.
    """
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for i in range(100):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,status,category,stake_units,pnl_units) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01T10:00:00", "mlb", "2026-08-01", f"P{i}", "hits",
             "OVER", 1.5, "dk", -200, 0.6, "won" if i < 47 else "lost",
             "main", 1.0, 0.5 if i < 47 else -1.0))
    conn.commit()
    p = ledger.performance(conn)
    assert abs(p["win_rate"] - 0.47) < 1e-9
    # -200 needs 66.7%, not 52.4%.
    assert abs(p["breakeven"] - 0.6667) < 0.001


def test_the_breakeven_follows_a_plus_money_book_too():
    """A book of dogs needs LESS than 52.4%, and calling that book losing
    would be the same error in the other direction."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for i in range(60):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,status,category,stake_units,pnl_units) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01T10:00:00", "mlb", "2026-08-01", f"P{i}", "hits",
             "OVER", 1.5, "dk", 150, 0.45, "won" if i < 27 else "lost",
             "main", 1.0, 1.5 if i < 27 else -1.0))
    conn.commit()
    p = ledger.performance(conn)
    assert abs(p["breakeven"] - 0.40) < 0.001
    assert p["win_rate"] > p["breakeven"], "a profitable dog book read as losing"


def test_an_empty_book_reports_no_breakeven_rather_than_a_default():
    p = ledger.performance(_conn())
    assert p["breakeven"] is None


def test_the_page_prints_the_measured_breakeven_not_a_constant():
    app = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "js", "app.js"),
        encoding="utf-8").read()
    i = app.index('recTile("Win rate"')
    tile = app[i:i + 500]
    assert "o.breakeven" in tile, "the tile still hardcodes a break-even"
    assert "at the prices taken" in tile
    # The -110 wording survives only as the no-odds fallback.
    assert "o.breakeven == null" in tile


# --- CLV that can see a fixed-line market ------------------------------------
def test_price_clv_measures_what_the_line_cannot():
    """A home-run prop is quoted OVER 0.5 and closes at 0.5. Its line is
    incapable of moving, so line CLV reads 0 forever and the whole market —
    two thirds of this journal — is invisible to the instrument. Those
    props move on PRICE, and the snapshots have carried it all along."""
    took_better = {"side": "OVER", "odds": 400, "closing_odds": 350}
    took_worse = {"side": "OVER", "odds": 400, "closing_odds": 500}
    flat = {"side": "OVER", "odds": 300, "closing_odds": 300}
    # Closing SHORTER than we took = the market came to us.
    assert ledger._bet_price_clv(took_better) > 0
    assert ledger._bet_price_clv(took_worse) < 0
    assert ledger._bet_price_clv(flat) == 0.0
    # In probability points, so +400→+350 and −150→−170 are comparable.
    assert abs(ledger._bet_price_clv(took_better) - 0.0222) < 0.001


def test_price_clv_declines_to_guess_on_an_under():
    """The snapshots record the OVER price. Measuring an under against
    1 − P(over at close) compares two different quantities: the vig means
    an over and an under at one book do not sum to 1, and that hold is
    4–5 points — enough to swamp a CLV signal measured in single points.
    None is the honest answer until the taken over price is journaled."""
    assert ledger._bet_price_clv(
        {"side": "UNDER", "odds": -140, "closing_odds": 400}) is None


def test_price_clv_survives_a_row_that_predates_the_column():
    for bad in ({"side": "OVER", "odds": 400},
                {"side": "OVER", "odds": 400, "closing_odds": None},
                {"side": "OVER", "odds": 0, "closing_odds": 400}):
        assert ledger._bet_price_clv(bad) is None


def test_the_two_clvs_are_reported_apart_and_never_averaged_together():
    """Line points and probability points are different units. Mixing them
    would be arithmetic on two things that are not the same thing."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for i, (took, close) in enumerate([(400, 350), (400, 500), (250, 200)] * 10):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,status,category,stake_units,pnl_units,"
            "closing_line,closing_odds) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01T10:00:00", "mlb", "2026-08-01", f"P{i}", "home_runs",
             "OVER", 0.5, "dk", took, 0.2, "lost", "main", 0.1, -0.1,
             0.5, close))
    conn.commit()
    p = ledger.performance(conn)
    # The line never moved, so the line measure is a zero that says nothing…
    assert p["avg_clv"] == 0.0 and p["clv_n"] == 30
    # …while the price measure has a real reading on the same bets.
    assert p["avg_price_clv"] != 0.0 and p["price_clv_n"] == 30


def test_the_closing_price_comes_from_the_free_snapshots():
    """Same source as the line close: it accrues on pulls already paid for,
    so seeing a fixed-line market costs no extra credits."""
    import inspect
    from engine import linemoves
    src = inspect.getsource(linemoves.closing_odds_by_date)
    assert "over_odds" in src and "under_odds" in src
    assert "_pregame_only" in src, "an in-play re-price could become the close"
    assert "_median" in src, "one outlier book could define the close"


def _snap(player, market, ts, over=None, under=None):
    return {"player": player, "market": market, "ts": ts, "line": 1.5,
            "over_odds": over, "under_odds": under, "book": "FanDuel"}


def test_the_close_carries_both_sides():
    """THE BUG, found 2026-08-09 by CLV's own internal check running
    backwards: win rate when we 'beat the close' was 41.2%, when we did
    not 61.9%. Beating the close is supposed to PREDICT winning.

    This returned the OVER price alone and `_settle_all` looked it up
    with a key carrying no side, so every UNDER bet in the journal banked
    the OVER's closing price as its own and was measured against the
    opposite of what it bought. The snapshot table has carried
    `under_odds` since it was created; nothing read it."""
    from engine.linemoves import closing_odds_by_date
    import time as _t
    ts = _t.time() - 7200
    got = closing_odds_by_date([_snap("Aaron Judge", "hits", ts,
                                      over=-120, under=100)])
    key = [k for k in got][0]
    assert got[key]["over"] == -120
    assert got[key]["under"] == 100


def test_a_row_quoted_only_on_the_under_is_not_thrown_away():
    """The old guard skipped any row without an over price, which is how
    an under-only quote became no close at all."""
    from engine.linemoves import closing_odds_by_date
    import time as _t
    got = closing_odds_by_date([_snap("X Y", "hits", _t.time() - 7200,
                                      over=None, under=-105)])
    assert got, "an under-only quote produced no close"
    key = [k for k in got][0]
    assert got[key]["under"] == -105
    assert got[key]["over"] is None, "a missing side must be None, not faked"


def test_the_settle_picks_the_side_the_bet_actually_took():
    """The other half of the fix. A correct lookup is no use if the
    caller still asks for the over."""
    import inspect
    from engine import ledger
    src = inspect.getsource(ledger)
    i = src.index('_sides = closes_cache["_snapshot_odds"]')
    body = src[i:i + 400]
    assert '"under" if' in body and 'UNDER' in body
    assert '"over"' in body


def test_the_field_is_journaled_beside_the_book_we_shopped_to():
    """`edge` is measured against the book being BET (engine/odds.
    best_over_line de-vigs that book's own quote), so the benchmark moves
    with the outlier: shopping selects the price furthest from the field,
    and that same price defines fair. Whether it costs anything is a
    question for the record — and the record can only answer it if the
    field was captured when the pick was made. Reconstructing it later
    from snapshots is a looser number."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, {"sport": "mlb", "date": "2026-08-06",
        "recommendations": [{
            "player": "A", "market": "hits", "side": "OVER", "line": 1.5,
            "book": "dk", "odds": -110, "projection": 1.8, "hit_prob": 0.56,
            "raw_prob": 0.62, "edge": 0.05, "confidence": 7, "grade": "B",
            "stake_units": 1.0, "recommended": True,
            "fair_consensus": 0.512, "consensus_books": 5}]})
    r = conn.execute(
        "SELECT fair_consensus, consensus_books FROM bets").fetchone()
    assert abs(r["fair_consensus"] - 0.512) < 1e-9
    assert r["consensus_books"] == 5


def test_a_pick_with_no_field_journals_null_rather_than_a_guess():
    """Fewer than three books is not a consensus. NULL says "we could not
    see a field here", which a later analysis must be able to exclude —
    a fabricated one would look like evidence."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, {"sport": "mlb", "date": "2026-08-06",
        "recommendations": [{
            "player": "B", "market": "hits", "side": "OVER", "line": 1.5,
            "book": "dk", "odds": -110, "hit_prob": 0.56, "edge": 0.05,
            "confidence": 7, "grade": "B", "stake_units": 1.0,
            "recommended": True}]})
    r = conn.execute(
        "SELECT fair_consensus, consensus_books FROM bets").fetchone()
    assert r["fair_consensus"] is None
    assert r["consensus_books"] is None or r["consensus_books"] == 0


def test_nothing_prices_from_the_field_yet():
    """Evidence, not pricing. The edge that gates and sizes a bet still
    comes from the taken book — changing that moves every number on the
    board and belongs behind the measurement, not in front of it."""
    import inspect
    from engine import betting
    from engine.mlb import betting as mlb_betting
    for mod in (betting.evaluate_prop, mlb_betting.evaluate_mlb_prop):
        src = inspect.getsource(mod)
        assert "consensus_fair(prop.lines" in src, "the field is not captured"
        # The field is read once and carried onto the Recommendation. It
        # must not appear anywhere a decision is made — the gate, the
        # stake and the grade all still run off `edge` against the taken
        # book, which is what makes this evidence rather than a change.
        head = src.split("_field = consensus_fair")[0]
        assert "_field" not in head, "the field reached a decision"
        for decision in ("gate_ok = ", "stake = ", "grade = "):
            line = next((ln for ln in src.splitlines()
                         if ln.strip().startswith(decision)), "")
            assert "_field" not in line and "consensus" not in line, decision


def test_the_snapshot_writes_both_sides_of_the_price():
    """FOUND BY --clv PRINTING ITS GROUP COUNTS: "CLV BY SIDE: not shown
    — OVER 113". Not 98 and 15. Every single rebuilt close was an OVER,
    on a book that plainly contains UNDERs.

    The snapshot writer recorded `over_odds` and never `under_odds`, so
    the entire line history is over-only and no UNDER bet can ever have a
    close rebuilt from it. The line object has carried the field all
    along and the odds_history table has a column for it; only this
    writer dropped it.

    It does not recover the past — those rows are on disk without an
    under price. It starts the clock."""
    import inspect
    from engine import linemoves
    src = inspect.getsource(linemoves)
    i = src.index('"ts": ts, "player": prop.player')
    row = src[i:i + 400]
    assert '"over_odds"' in row and '"under_odds"' in row, row


def test_a_recorded_snapshot_round_trips_the_under_price():
    """Behavioural, not a source scan: write one and read it back through
    the close builder, which is the only consumer that matters."""
    import tempfile
    import time as _t
    from pathlib import Path
    from engine import linemoves

    class _Ln:
        book = "FanDuel"
        line = 1.5
        over_odds = -115
        under_odds = -105

    class _Prop:
        player = "Test Hitter"
        market = "hits"
        lines = [_Ln()]

    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        linemoves.record_snapshots([_Prop()], path=Path(path),
                                   ts=_t.time() - 7200)
        got = linemoves.closing_odds_by_date(linemoves.load_history(path))
    finally:
        os.unlink(path)
    assert got, "nothing was recorded"
    sides = got[[k for k in got][0]]
    assert sides["over"] == -115
    assert sides["under"] == -105, f"the under price did not survive: {sides}"


def _paper_result():
    return {"sport": "mlb", "date": "2026-08-10", "recommendations": [
        {"player": "Paper Hitter", "market": "hits", "side": "OVER",
         "line": 1.5, "odds": -110, "book": "FanDuel", "hit_prob": 0.55,
         "edge": 0.04, "confidence": 70, "grade": "B", "stake_units": 0.4,
         "projection": 1.8, "recommended": True}]}


def test_paper_mode_journals_the_pick_with_zero_dollars():
    """Ethan, 2026-08-09, after the cleaned CLV read came back at zero:
    keep the machine running and stop paying for it.

    The stake in UNITS is kept as sized — that is the whole point, since
    a paper book has to answer "what would this have returned" and a zero
    stake cannot. What makes it costless is the category, not the size."""
    conn = ledger.connect(":memory:")
    ledger.set_paper_mode(conn, True)
    assert ledger.log_recommendations(conn, _paper_result()) == 1
    row = conn.execute("SELECT category, stake_units, stake_dollars "
                       "FROM bets").fetchone()
    assert row[0] == "paper"
    assert row[1] == 0.4, "the sized stake must survive — it is the measurement"
    assert row[2] == 0.0, "paper mode must move no dollars"


def test_paper_bets_never_enter_the_headline_record():
    """The one guarantee the whole feature rests on."""
    conn = ledger.connect(":memory:")
    ledger.set_paper_mode(conn, True)
    ledger.log_recommendations(conn, _paper_result())
    conn.execute("UPDATE bets SET status='won', pnl_units=0.36, "
                 "pnl_dollars=0.0")
    conn.commit()
    perf = ledger.performance(conn, "mlb")
    assert perf["settled"] == 0, f"a paper bet reached the record: {perf}"


def test_paper_mode_is_off_unless_it_was_turned_on():
    """A default that silently stopped betting real money would be a
    worse surprise than one that silently kept going."""
    conn = ledger.connect(":memory:")
    assert ledger.paper_mode(conn) is False
    ledger.log_recommendations(conn, _paper_result())
    row = conn.execute("SELECT category, stake_dollars FROM bets").fetchone()
    assert row[0] == "main"
    assert row[1] > 0, "real mode must still size dollars"


def test_the_toggle_survives_a_reconnect():
    """It is stored config rather than a nightly flag precisely so it
    outlives the process that set it."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        c1 = ledger.connect(path)
        ledger.set_paper_mode(c1, True)
        c1.close()
        c2 = ledger.connect(path)
        assert ledger.paper_mode(c2) is True
        c2.close()
    finally:
        os.unlink(path)


def test_the_site_payload_carries_the_paper_book_and_the_switch():
    """The page has to be able to say "these are paper" — a paper record
    rendered without that label is just a second, quieter lie about how
    the model is doing."""
    import json
    import tempfile
    conn = ledger.connect(":memory:")
    ledger.set_paper_mode(conn, True)
    ledger.log_recommendations(conn, _paper_result())
    conn.execute("UPDATE bets SET status='won', pnl_units=0.36, "
                 "pnl_dollars=0.0")
    conn.commit()
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        ledger.export_json(conn, path)
        out = json.load(open(path))
    finally:
        os.unlink(path)
    assert out["paper_mode"] is True
    assert out["paper"]["settled"] == 1
    assert out["overall"]["settled"] == 0, "the paper win reached the record"
    assert out["paper"]["net_units"] == 0.36


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
