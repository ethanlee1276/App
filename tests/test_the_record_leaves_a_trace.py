"""The track record leaves a trace: audit item P0-1, approved by Ethan
2026-09-30 ("I approve everything").

The audit found the journal was honest by convention, not by construction:
twenty code paths rewrote settled rows, two of them deleted rows every
night, nothing kept the old values, and the forecast hash chain covered
the forecast only and never looked at the bets table. So a re-grade or a
deleted row left no mark anyone could check.

Now:
  * every UPDATE or DELETE on `bets` writes a row to `bets_audit` (a
    database trigger, so it holds for every code path and for a hand-typed
    query on the box), with the reason when the code knows it;
  * the audit rows are hash-chained and sealed like the forecast log;
  * the two nightly sweeps keep their duplicate rows as voids instead of
    deleting them;
  * a settled game-market bet is never re-graded off a game row from today
    or yesterday — the games table has held live scores before;
  * the forecast chain's version 2 also covers the lead time and the seal
    time, and verifying it checks every sealed forecast against the
    journal it protects and says how many drifted, and whether each drift
    has a logged change behind it;
  * the export publishes the recent re-grades and the daily chain heads.

Fixture ledgers in a temp directory — never the box's.

Run directly: `python3 tests/test_the_record_leaves_a_trace.py`
"""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                          # noqa: E402


def _ledger():
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(path)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn, path


def _bet(conn, player="A Judge", status="won", market="hits", category="main",
         date="2026-09-01", actual=2.0, line=1.5, side="OVER", odds=-110):
    cur = conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, "
        "edge, stake_units, stake_dollars, status, actual, pnl_units, pnl_dollars, category, "
        "lead_min) VALUES ('2026-09-01T16:00:00', 'mlb', ?, ?, ?, ?, ?, ?, 0.6, 0.05, 1.0, "
        "10.0, ?, ?, 0.91, 9.09, ?, 180)",
        (date, player, market, side, line, odds, status, actual, category))
    conn.commit()
    return cur.lastrowid


def _audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM bets_audit ORDER BY seq")]


# --- every change leaves a row ------------------------------------------------
def test_an_update_to_a_settled_row_is_logged_with_its_reason():
    conn, _ = _ledger()
    bid = _bet(conn)
    with ledger.audit_reason(conn, "regrade"):
        conn.execute("UPDATE bets SET status='lost', pnl_units=-1.0 WHERE id=?", (bid,))
    conn.commit()
    rows = _audit(conn)
    assert len(rows) == 1
    r = rows[0]
    assert r["bet_id"] == bid and r["action"] == "update" and r["reason"] == "regrade"
    assert json.loads(r["old"])["status"] == "won" and json.loads(r["new"])["status"] == "lost"
    assert r["ts"].endswith("Z")


def test_a_write_that_changes_nothing_audited_leaves_no_row():
    conn, _ = _ledger()
    bid = _bet(conn)
    conn.execute("UPDATE bets SET why_note='a note' WHERE id=?", (bid,))
    conn.commit()
    assert _audit(conn) == []


def test_a_hand_typed_delete_is_logged_without_a_reason():
    conn, _ = _ledger()
    bid = _bet(conn)
    conn.execute("DELETE FROM bets WHERE id=?", (bid,))
    conn.commit()
    r = _audit(conn)[0]
    assert r["action"] == "delete" and r["reason"] is None and r["new"] is None
    assert json.loads(r["old"])["player"] == "A Judge"


def test_the_reason_nests_and_is_cleared_afterwards():
    conn, _ = _ledger()
    bid = _bet(conn)
    with ledger.audit_reason(conn, "outer"):
        with ledger.audit_reason(conn, "inner"):
            conn.execute("UPDATE bets SET line=2.5 WHERE id=?", (bid,))
        conn.execute("UPDATE bets SET line=3.5 WHERE id=?", (bid,))
    conn.execute("UPDATE bets SET line=4.5 WHERE id=?", (bid,))
    conn.commit()
    assert [r["reason"] for r in _audit(conn)] == ["inner", "outer", None]


def test_the_audit_log_refuses_edits_and_deletes():
    conn, _ = _ledger()
    bid = _bet(conn)
    conn.execute("UPDATE bets SET status='lost' WHERE id=?", (bid,))
    conn.commit()
    ledger.seal_audit(conn)
    for sql in ("UPDATE bets_audit SET reason='x'", "DELETE FROM bets_audit"):
        try:
            conn.execute(sql)
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError(f"{sql} was allowed")


# --- the audit chain ----------------------------------------------------------
def test_the_audit_chain_seals_verifies_and_catches_a_tamper():
    conn, _ = _ledger()
    bid = _bet(conn)
    for s in ("lost", "won", "lost"):
        conn.execute("UPDATE bets SET status=? WHERE id=?", (s, bid))
    conn.commit()
    assert ledger.seal_audit(conn) == 3
    assert ledger.seal_audit(conn) == 0, "idempotent"
    v = ledger.verify_audit_log(conn)
    assert v["ok"] and v["n"] == 3 and v["head"]
    conn.execute("DROP TRIGGER bets_audit_no_update")          # a deliberate tamper
    conn.execute("UPDATE bets_audit SET old=replace(old, 'lost', 'won') WHERE seq=2")
    conn.commit()
    v = ledger.verify_audit_log(conn)
    assert not v["ok"] and v["broken_at"] == 2 and v["verified_through"] == 1


# --- the nightly sweeps keep their duplicates ---------------------------------
def test_the_longshot_sweep_voids_a_duplicate_instead_of_deleting_it():
    conn, _ = _ledger()
    _bet(conn, player="Big Bat", market="home_runs", category="main", line=0.5)
    _bet(conn, player="Big Bat", market="home_runs", category="longshot", line=0.5)
    n = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    assert ledger.move_longshots_out_of_main(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == n, "no row deleted"
    kept = conn.execute("SELECT category, status FROM bets WHERE category LIKE 'dropped:%'").fetchone()
    assert tuple(kept) == ("dropped:main", "void")
    assert ledger.performance(conn)["settled"] == 0
    assert any(r["reason"] == "move_longshots" for r in _audit(conn))


def test_the_watch_split_voids_a_duplicate_instead_of_deleting_it():
    conn, _ = _ledger()
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, "
                 "stake_units, status, category, grade) VALUES "
                 "('t','mlb','2026-09-01','Dart','home_runs','OVER',0.5,500,0.1,'lost','longshot','Watch')")
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, "
                 "stake_units, status, category, grade) VALUES "
                 "('t','mlb','2026-09-01','Dart','home_runs','OVER',0.5,500,0.1,'lost',"
                 "'longshot_watch','Watch')")
    conn.commit()
    assert ledger.split_watch_from_longshots(conn) == 1
    cats = sorted(r[0] for r in conn.execute("SELECT category FROM bets"))
    assert cats == ["dropped:longshot", "longshot_watch"]


# --- no re-grade off a live score --------------------------------------------
def test_a_game_market_is_not_regraded_off_todays_game_row():
    conn, _ = _ledger()
    today = dt.date.today().isoformat()
    hist = sqlite3.connect(":memory:")
    hist.row_factory = sqlite3.Row
    from engine import db
    hist.executescript(db.SCHEMA)
    # Graded UNDER 8.5 at a final 7 — but today's row now reads 9 (a live score).
    hist.execute("INSERT INTO games (sport, season, period, game_id, home, away, "
                 "home_score, away_score) VALUES ('mlb', 2026, ?, 'g1', 'NYY', 'BOS', 5, 4)",
                 (today,))
    hist.commit()
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, "
                 "stake_units, stake_dollars, status, actual, pnl_units, category) VALUES "
                 "('t','mlb',?,'BOS@NYY','total','UNDER',8.5,-110,1.0,10.0,'won',7,0.91,'main')",
                 (today,))
    conn.commit()
    assert ledger.resettle_mismatches(conn, hist) == []
    assert conn.execute("SELECT status FROM bets").fetchone()[0] == "won"


# --- the forecast chain, version 2, checked against the journal --------------
def test_version_two_covers_lead_time_and_old_links_still_verify():
    conn, _ = _ledger()
    bid = _bet(conn, player="One")
    # A version-1 chain row sealed the old way, as the box already has.
    d = dict(conn.execute("SELECT id AS bet_id, ts, sport, date, player, market, side, line, "
                          "odds, hit_prob, category FROM bets WHERE id=?", (bid,)).fetchone())
    h = ledger._forecast_hash(ledger.GENESIS_HASH, d)
    conn.execute("INSERT INTO forecast_log (sealed_ts, bet_id, ts, sport, date, player, market, "
                 "side, line, odds, hit_prob, category, prev_hash, hash) VALUES "
                 "('2026-09-01T12:00:00',?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (d["bet_id"], d["ts"], d["sport"], d["date"], d["player"], d["market"],
                  d["side"], d["line"], d["odds"], d["hit_prob"], d["category"],
                  ledger.GENESIS_HASH, h))
    conn.commit()
    _bet(conn, player="Two")
    assert ledger.seal_forecasts(conn) == 1
    rows = conn.execute("SELECT v, lead_min, sealed_ts FROM forecast_log ORDER BY seq").fetchall()
    assert [r["v"] or 1 for r in rows] == [1, 2]
    assert rows[1]["lead_min"] == 180 and rows[1]["sealed_ts"].endswith("Z")
    assert ledger.verify_forecast_log(conn)["ok"]
    conn.execute("UPDATE forecast_log SET lead_min=999 WHERE seq=2")
    conn.commit()
    assert ledger.verify_forecast_log(conn)["broken_at"] == 2, "the lead time is under the hash"


def test_verify_says_how_many_forecasts_no_longer_match_the_journal():
    conn, _ = _ledger()
    a = _bet(conn, player="Logged Change")
    b = _bet(conn, player="Quiet Change")
    ledger.seal_forecasts(conn)
    assert ledger.verify_forecast_log(conn)["drifted"] == 0
    with ledger.audit_reason(conn, "repair"):
        conn.execute("UPDATE bets SET side='UNDER' WHERE id=?", (a,))
    conn.execute("DROP TRIGGER bets_audit_update")              # what a hand edit would need
    conn.execute("UPDATE bets SET line=9.5 WHERE id=?", (b,))
    conn.commit()
    v = ledger.verify_forecast_log(conn)
    assert v["ok"], "the chain itself is intact"
    assert v["drifted"] == 2 and v["unexplained"] == 1 and v["missing"] == 0


# --- published ---------------------------------------------------------------
def test_the_export_publishes_regrades_heads_and_the_audit_chain():
    conn, path = _ledger()
    bid = _bet(conn)
    with ledger.audit_reason(conn, "regrade"):
        conn.execute("UPDATE bets SET status='lost', actual=1.0, pnl_units=-1.0 WHERE id=?", (bid,))
    conn.commit()
    head = ledger.record_heads(conn, post=False)
    assert head and head["forecast_n"] == 1 and head["audit_n"] == 1
    assert ledger.record_heads(conn, post=False) is None, "once a day"
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    d = json.loads(out.read_text())
    rg = d["regrades"]
    assert rg["n"] == 1 and rg["recent"][0]["changes"]["status"] == ["won", "lost"]
    assert rg["recent"][0]["reason"] == "regrade"
    assert d["audit_log"]["ok"] and d["audit_log"]["n"] == 1
    assert d["forecast_heads"][-1]["forecast_head"] == head["forecast_head"]
    assert "drifted" in d["forecast_log"]


def test_the_integrity_report_and_the_doctor_check():
    conn, _ = _ledger()
    _bet(conn)
    ledger.seal_forecasts(conn)
    rep = ledger.integrity_report(conn)
    assert rep["triggers"] is True and rep["forecast"]["ok"] and rep["audit"]["ok"]
    conn.execute("DROP TRIGGER bets_audit_delete")
    conn.commit()
    assert ledger.integrity_report(conn)["triggers"] is False
    doc = (ROOT / "doctor.py").read_text()
    assert "def check_record_integrity" in doc
    import doctor
    assert doctor.check_record_integrity in doctor.CHECKS
    assert doctor.check_record_integrity in doctor.DATA_CHECKS


def test_the_page_says_what_the_chain_covers_and_shows_the_changes():
    app = (ROOT / "web" / "js" / "app.js").read_text()
    i = app.index("function recForecastLog(f")
    body = app[i:i + 5000]
    assert "the lead time" in body and "unexplained" in body
    assert "function recRegrades(" in app and "recRegrades(d.regrades" in app
    # The daily heads ride record.json so a reader can save one; the page
    # has to show them or the export is a value nobody reads.
    assert "d.forecast_heads" in app and "function recHeadsList(" in app


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
