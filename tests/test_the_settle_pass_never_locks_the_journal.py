"""The settle pass never locks the boards out of the journal.

Found 2026-10-14 on the box, the evening Ethan got home: the MLB build's
last run printed "Bet journal skipped: database is locked" while the
settle chore ran, the last two runs of every board's build held four MLB
and two college journals skipped that way, and the service log held 198
lock errors in three days. A skipped journal is a pick the record may
never see: the next build tries again, but a game that starts in between
is gone.

Two things held the journal's write lock for a whole settle pass:

* THE AUDIT LABEL (`ledger.audit_reason`) was a row in the shared config
  table, written at the top of every labelled block and left uncommitted
  so nobody else could see it; the write took the lock, and the label kept
  it to the block's last line. The label now lives in a per-connection
  TEMP table, copied onto this connection's audit rows by a TEMP trigger.
* THE SETTLE LOOP (`ledger.settle_from_history`) committed once, after
  the last bet; it now commits each bet before reading the next.

Fixture ledgers in a temp directory, never the box's.

Run directly: `python3 tests/test_the_settle_pass_never_locks_the_journal.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger                                      # noqa: E402


def _ledger():
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(path)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn, path


def _bet(conn, player, market="hits", status="open"):
    cur = conn.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
        "stake_units, stake_dollars, status, category) VALUES ('2026-10-13T16:00:00', 'mlb', "
        "'2026-10-13', '2026-10-13', ?, ?, 'OVER', 1.5, -110, 1, 10, ?, 'main')",
        (player, market, status))
    conn.commit()
    return cur.lastrowid


def _other(path):
    """A second writer that will not wait: a build journalling its picks."""
    return sqlite3.connect(str(path), timeout=0.2)


def test_a_labelled_block_leaves_the_journal_open_to_other_writers():
    conn, path = _ledger()
    mine, theirs = _bet(conn, "A Judge"), _bet(conn, "J Soto")
    other = _other(path)
    with ledger.audit_reason(conn, "settle"):
        # The board's build, mid-block: it writes and commits at once.
        other.execute("UPDATE bets SET status='void' WHERE id=?", (theirs,))
        other.commit()
        assert other.execute("SELECT value FROM config WHERE key='audit_reason'").fetchone() is None, \
            "the label reached the shared table"
        conn.execute("UPDATE bets SET status='won' WHERE id=?", (mine,))
    reasons = {r[0]: r[1] for r in conn.execute("SELECT bet_id, reason FROM bets_audit")}
    assert reasons == {theirs: None, mine: "settle"}, reasons


def test_the_label_nests_and_a_later_write_is_unlabelled():
    conn, _ = _ledger()
    bid = _bet(conn, "A Judge", status="won")
    with ledger.audit_reason(conn, "outer"):
        with ledger.audit_reason(conn, "inner"):
            conn.execute("UPDATE bets SET line=2.5 WHERE id=?", (bid,))
        conn.execute("UPDATE bets SET line=3.5 WHERE id=?", (bid,))
    conn.execute("UPDATE bets SET line=4.5 WHERE id=?", (bid,))
    conn.commit()
    assert [r[0] for r in conn.execute("SELECT reason FROM bets_audit ORDER BY seq")] == \
        ["inner", "outer", None]
    assert not conn.in_transaction


def test_the_settle_pass_lets_a_board_journal_between_bets():
    """Two game bets the pass voids, one after the other; between them a
    board's build writes to the journal and must not wait."""
    conn, path = _ledger()
    first = _bet(conn, "NYY", market="moneyline")
    second = _bet(conn, "LAD", market="moneyline")
    other, seen, wrote = _other(path), [], []
    olds = (ledger._game_bet_evidence, ledger._pick_dh_game, ledger._hist_where)

    def where(b):
        seen.append(b["id"])
        if len(seen) == 2:                      # the first bet is graded, the second not yet
            other.execute("UPDATE bets SET why_note='journalled by a build' WHERE id=?", (second,))
            other.commit()
            wrote.append(True)
        return olds[2](b)

    ledger._game_bet_evidence = lambda h, b, w, a: ([{"game": 1}], lambda g: 0.0)
    ledger._pick_dh_game = lambda rows, b, fn: (None, "void")
    ledger._hist_where = where
    try:
        n = ledger.settle_from_history(conn, db.connect(":memory:"))
    finally:
        ledger._game_bet_evidence, ledger._pick_dh_game, ledger._hist_where = olds
    assert wrote == [True] and n == 2
    assert {r[0] for r in conn.execute("SELECT status FROM bets WHERE id IN (?, ?)", (first, second))} == {"void"}
    assert all(r[0] == "settle" for r in conn.execute("SELECT reason FROM bets_audit WHERE action='update' "
                                                       "AND json_extract(new, '$.status')='void'"))
    assert not conn.in_transaction


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
