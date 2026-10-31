"""One book, one ROI: every denominator on the Record page is stake at risk.

Ethan, 2026-09-06: "some of the data seems off." One thing that was: the
MLB verdict printed +34.2% ROI and the "Edge bets" header under it, for
the same 99-82-12 book, printed +31.9%; the Running P&L footer agreed
with the header, and its ledger line read "176.3u staked · 249.3u
returned · net +60.29u", which does not add up. `performance()` left
pushed stakes out of its denominator (a push risks nothing) while
`book_records` and `pnl_curve` counted them, and `returned_units`
counted the pushes' refunds against a staked figure that did not.

Now every one of them uses stake at risk, and returned = staked + net.

Run directly: `python3 tests/test_one_stake_definition.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger


def _book():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    rows = [  # date, player, market, odds, stake, status, pnl
        ("2026-08-10", "A", "hits", -110, 1.0, "won", 0.91),
        ("2026-08-10", "B", "hits", -110, 1.0, "lost", -1.0),
        ("2026-08-11", "C", "total", -110, 2.0, "push", 0.0),
        ("2026-08-11", "D", "hits", 150, 1.0, "won", 1.5),
        ("2026-08-12", "E", "total", -110, 1.5, "push", 0.0),
    ]
    conn.executemany(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, pnl_units, pnl_dollars, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(d + "T12:00:00", "mlb", d, p, m, "OVER", 1.5, "DK", o, st, st * 10, s, pnl, pnl * 10, "main")
         for d, p, m, o, st, s, pnl in rows])
    conn.commit()
    return conn


def test_the_verdict_the_book_header_and_the_curve_agree_on_roi():
    conn = _book()
    perf = ledger.performance(conn, "mlb")
    assert perf["units_staked"] == 3.0, "1 + 1 + 1: the two pushes risked nothing"
    assert abs(perf["net_units"] - 1.41) < 1e-9
    assert abs(perf["roi"] - 1.41 / 3.0) < 1e-9
    book = ledger.book_records(conn)["mlb"]["edge"]
    assert book["staked"] == 3.0 and abs(book["roi"] - round(1.41 / 3.0, 4)) < 1e-9
    assert book["markets"]["total"]["staked"] == 0.0, "a market that only pushed risked nothing"
    curve = ledger.pnl_curve(conn, "mlb")
    assert sum(p["staked"] for p in curve) == 3.0
    assert sum(p["staked_d"] for p in curve) == 30.0
    assert [p["n"] for p in curve] == [2, 2, 1], "the pushes still count as settled slates"


def test_returned_is_staked_plus_net():
    conn = _book()
    perf = ledger.performance(conn, "mlb")
    assert abs(perf["returned_units"] - (perf["units_staked"] + perf["net_units"])) < 1e-9
    assert abs(perf["returned_units"] - 4.41) < 1e-9, "1.91 back on A, 2.50 back on D, nothing on the pushes"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
