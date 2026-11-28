"""The Record's bet list is read once a change to the journal (step AGP, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". The Record's list of settled bets
(/api/record/bets) counted and sorted every settled bet on every ask: 577 ms on the live site, 400 of it the
server's own work, which every other page in the one process waits behind. The sign-up screen's newest graded pick
read the same first page on every rebuild (1.2 s of one). Both change only when a bet is journalled or settled, so
each is kept until the journal changes (engine/ledger.change_stamp): the file and its write-ahead log, since a
settle commits into the log first and the file itself moves only when the log is folded into it. The strategy lab's
kept answer reads the same stamp now (it read the file's time alone).

Offline. Run directly: `python3 tests/test_the_record_list_is_read_once_a_change.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import firstlook, ledger  # noqa: E402

DAY = max(dt.date.today() - dt.timedelta(days=2), dt.date.fromisoformat(ledger.RECORD_EPOCH)).isoformat()


def _bet(conn, player, status="won"):
    conn.execute("INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,book,hit_prob,stake_units,"
                 "stake_dollars,status,category,pnl_units) VALUES ('nfl',?,?,?,'receptions','OVER',5.5,-110,"
                 "'DraftKings',0.6,1.0,10.0,?,'main',?)", (DAY, DAY, player, status, 0.91 if status == "won" else -1.0))
    conn.commit()


def _ledger():
    path = os.path.join(tempfile.mkdtemp(), "ledger.db")
    conn = ledger.connect(path)
    _bet(conn, "Amon-Ra St. Brown")
    return path, conn


def _handler():
    import server
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, json.loads(body)))
    return h, sent


def test_the_stamp_moves_with_a_settle_in_the_log():
    path, conn = _ledger()
    before = ledger.change_stamp(path)
    assert before[0] is not None
    _bet(conn, "Jahmyr Gibbs", "lost")
    assert ledger.change_stamp(path) != before, "a commit lands in the write-ahead log, and the stamp says so"
    conn.close()
    assert ledger.change_stamp(os.path.join(tempfile.mkdtemp(), "none.db")) == (None, None)


def test_the_list_is_kept_per_filter_until_the_journal_changes():
    import server
    path, conn = _ledger()
    saved, real, calls = ledger.DEFAULT_DB, ledger.settled_page, []

    def counting(*a, **k):
        calls.append(k.get("kind"))
        return real(*a, **k)
    ledger.DEFAULT_DB = Path(path)
    ledger.settled_page = counting
    server._BETS_CACHE.clear()
    try:
        h, sent = _handler()
        h._record_bets({})
        h._record_bets({})
        assert len(calls) == 1 and sent[0] == sent[1] and sent[0][1]["total"] == 1, "kept"
        h._record_bets({"kind": ["props"]})
        assert len(calls) == 2, "another filter is its own answer"
        _bet(conn, "Jahmyr Gibbs", "lost")
        h._record_bets({})
        assert len(calls) == 3 and sent[-1][1]["total"] == 2, "a settle since: read again, with it"
        h._record_bets({"kind": ["parlays"]})
        assert sent[-1][0] == 400 and len(calls) == 3, "a bad filter is refused before anything is read"
    finally:
        ledger.DEFAULT_DB, ledger.settled_page = saved, real
        server._BETS_CACHE.clear()
        conn.close()
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    lab = src[src.index("    def _record_lab(self"):src.index("    def _explain(self")]
    assert "stamp = L.change_stamp()" in lab and "os.path.getmtime" not in lab, "the lab's kept answer too"


def test_the_first_looks_newest_graded_pick_is_read_once_a_change():
    path, conn = _ledger()
    saved, real, calls = ledger.DEFAULT_DB, firstlook.last_graded, []
    ledger.DEFAULT_DB = Path(path)
    firstlook.last_graded = lambda c: (calls.append(1), real(c))[1]
    firstlook._LAST.clear()
    web = Path(tempfile.mkdtemp())
    try:
        a = firstlook.build(web)
        b = firstlook.build(web)
        assert len(calls) == 1 and a["last"] == b["last"] and a["last"]["player"] == "Amon-Ra St. Brown", calls
        _bet(conn, "Jahmyr Gibbs", "lost")
        firstlook.build(web)
        assert len(calls) == 2, "a settle since: read again"
        mem = ledger.connect(":memory:")
        firstlook.build(web, conn=mem)
        assert len(calls) == 3, "a connection handed in is always read (a test's journal)"
        mem.close()
    finally:
        ledger.DEFAULT_DB, firstlook.last_graded = saved, real
        firstlook._LAST.clear()
        conn.close()


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
