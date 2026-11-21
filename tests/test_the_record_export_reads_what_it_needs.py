"""The record export reads only what it shows (engine/ledger.recent_regrades,
_loss_patterns_block).

The export's own sampler at 20:08 on Saturday 7 November: 52.7 seconds, of
them 9.9 re-mining the loss patterns and 4.4 parsing every grade the journal
ever made to find the few re-grades. What these hold:

  * the re-grade list leaves the first gradings to SQLite and gives exactly
    the list the full read gave, deletions and odd rows included; a
    database without SQLite's JSON reader reads them all, as before;
  * the loss-pattern block is the miner's saved result, the one every
    board's veto reads, and mines only while nothing is saved.

Run directly: `python3 tests/test_the_record_export_reads_what_it_needs.py`
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, losspatterns                            # noqa: E402


def _old_way(conn, limit=50):
    """recent_regrades before 8 November: every update and deletion parsed."""
    rows = conn.execute("SELECT * FROM bets_audit WHERE action IN "
                        "('update', 'delete') ORDER BY seq DESC").fetchall()
    out = []
    for r in rows:
        old = json.loads(r["old"] or "{}")
        new = json.loads(r["new"]) if r["new"] else None
        if new is not None and old.get("status") not in ("won", "lost", "push", "void"):
            continue
        changes = ({f: [old.get(f), None] for f in ("status",)} if new is None else
                   {f: [old.get(f), new.get(f)] for f in ledger.REGRADE_FIELDS
                    if not ledger._same(old.get(f), new.get(f))})
        if not changes:
            continue
        out.append({"ts": r["ts"], "bet_id": r["bet_id"], "action": r["action"],
                    "reason": r["reason"], "sport": old.get("sport"),
                    "date": old.get("game_day") or old.get("date"),
                    "player": old.get("player"), "market": old.get("market"),
                    "side": old.get("side"), "line": old.get("line"),
                    "changes": changes})
    return {"n": len(out), "recent": out[:limit]}


def _journal():
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    for i in range(30):
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
                     "stake_units, stake_dollars, status, category) VALUES (?, 'nba', '2026-11-07', ?, "
                     "'pts', 'OVER', 20.5, 'DraftKings', -110, 1, 10, 'open', 'main')",
                     (f"2026-11-07T12:{i:02d}:00", f"Player {i}"))
    conn.commit()
    # First gradings (open → won/lost), the bulk of any real audit log.
    for i in range(1, 31):
        conn.execute("UPDATE bets SET status=?, actual=?, pnl_units=? WHERE id=?",
                     ("won" if i % 2 else "lost", 25.0, 0.91 if i % 2 else -1.0, i))
    conn.commit()
    # Re-grades of settled picks, a void, a deletion, and a no-change touch.
    conn.execute("UPDATE bets SET status='lost', actual=19.0, pnl_units=-1.0 WHERE id=1")
    conn.execute("UPDATE bets SET status='void', pnl_units=0 WHERE id=3")
    conn.execute("UPDATE bets SET why_note='a note' WHERE id=5")
    conn.execute("DELETE FROM bets WHERE id=7")
    conn.commit()
    # And rows a hand once wrote: an empty new half, a missing old half.
    conn.execute("INSERT INTO bets_audit (ts, bet_id, action, old, new, reason) VALUES "
                 "('2026-11-07T23:00:00', 9, 'update', ?, '', 'hand')",
                 (json.dumps({"status": "open", "player": "Player 8"}),))
    conn.execute("INSERT INTO bets_audit (ts, bet_id, action, old, new, reason) VALUES "
                 "('2026-11-07T23:01:00', 11, 'update', NULL, ?, 'hand')",
                 (json.dumps({"status": "won"}),))
    conn.commit()
    return conn


def test_the_regrade_list_is_the_full_reads_list():
    conn = _journal()
    n_audit = conn.execute("SELECT COUNT(*) FROM bets_audit WHERE action='update'").fetchone()[0]
    assert n_audit >= 33, n_audit
    got, want = ledger.recent_regrades(conn), _old_way(conn)
    assert got == want, (got, want)
    assert got["n"] >= 3 and {r["bet_id"] for r in got["recent"]} >= {1, 3, 7}, got
    assert ledger.recent_regrades(conn, limit=2) == _old_way(conn, limit=2)


def test_without_sqlites_json_reader_it_reads_them_all():
    conn = _journal()

    class _NoJson:
        def __init__(self, c):
            self.c = c

        def execute(self, sql, *a):
            if "json_extract" in sql:
                raise sqlite3.OperationalError("no such function: json_extract")
            return self.c.execute(sql, *a)
    assert ledger.recent_regrades(_NoJson(conn)) == _old_way(conn)
    assert ledger.recent_regrades(ledger.connect(":memory:")) == {"n": 0, "recent": []}


def test_the_loss_pattern_block_is_the_saved_result_and_mines_only_without_one():
    conn = ledger.connect(":memory:")
    saved = losspatterns.DEFAULT_PATH
    with tempfile.TemporaryDirectory() as td:
        losspatterns.DEFAULT_PATH = Path(td) / "losspatterns.json"
        try:
            mined = ledger._loss_patterns_block(conn)
            assert mined["findings"] == [] and mined["closed"] == [], "nothing saved: mined"
            store = {"n_records": 812, "tested": 40, "findings": [{"sport": "nba"}],
                     "closed": [{"sport": "nba", "market": "pts"}], "generated": "2026-11-07T20:00:00"}
            losspatterns.save(store)
            assert ledger._loss_patterns_block(conn) == store, "the saved result, as the vetoes read it"
        finally:
            losspatterns.DEFAULT_PATH = saved
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = src.index("def _loss_patterns_block(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "lp.load()" in body and body.index("lp.load()") < body.index("lp.mine(")


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
