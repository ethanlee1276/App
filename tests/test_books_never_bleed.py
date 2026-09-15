"""The edge book and the Most Likely book never share a number.

Ethan, 2026-09-05: "i wanna make sure by tieing in the best bets into
the record page for the sports and shit, that the roi for edge bets and
the roi for most likley bets are kept seperate and its all tracked and
kept seprerate. obv show it on the same page without it been cluttered
but we just dont want the data to interfeer with itself."

The ledger already keeps them apart by construction: every headline
reader — `performance`, `pnl_curve`, `recent_settled`, `calibration`,
the splits, the eras — is filtered to the edge book (main and paper),
and the likely book has its own report and its own section. This file
turns that from a property of today's code into a promise: it journals
both books into one temporary ledger and asserts that adding rows to
either leaves the other's every number exactly where it was.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                    # noqa: E402

_SEQ = [0]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


def _bet(conn, sport, category, market, status, pnl, stake=1.0, hit=0.6):
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
        "pnl_units) VALUES (?,?,?,?,'OVER',0.5,-120,'DK',?,0,?,0,"
        "'now',?,?,?)",
        (sport, "2026-09-01", f"P{_SEQ[0]}", market, hit, stake, status,
         category, pnl))
    conn.commit()


def _edge_rows(conn):
    _bet(conn, "mlb", "main", "hits", "won", 0.8)
    _bet(conn, "mlb", "main", "home_runs", "lost", -1.0)
    _bet(conn, "mlb", "main", "total_bases", "won", 0.9)


def _likely_rows(conn):
    # The likely book: flat 0.1 stake, all winners — the shape most able
    # to flatter an edge record it leaked into.
    for m in ("hits", "hits", "total_bases", "home_runs", "strikeouts"):
        _bet(conn, "mlb", "likely", m, "won", 0.08, stake=0.1, hit=0.7)


def _edge_view(conn):
    """Every number the sport's Record page prints for the edge book."""
    rep = ledger.sport_report(conn, "mlb")
    return {
        "overall": rep["overall"],
        "curve": rep["curve"],
        "recent": [(r["player"], r["market"], r["status"]) for r in rep["recent"]],
        "calibration": rep["calibration"],
        "splits": ledger.calibration_splits(conn, sport="mlb"),
        "books_edge": ledger.book_records(conn)["mlb"].get("edge"),
    }


def test_adding_likely_rows_moves_no_edge_number():
    conn = _conn()
    _edge_rows(conn)
    before = _edge_view(conn)
    assert before["overall"]["settled"] == 3
    _likely_rows(conn)
    after = _edge_view(conn)
    assert after == before, {k: (before[k], after[k])
                             for k in before if before[k] != after[k]}


def test_adding_edge_rows_moves_no_likely_number():
    conn = _conn()
    _likely_rows(conn)
    before = (ledger.likely_report(conn),
              ledger.book_records(conn)["mlb"].get("likely"))
    _edge_rows(conn)
    after = (ledger.likely_report(conn),
             ledger.book_records(conn)["mlb"].get("likely"))
    assert after == before


def test_the_two_rois_are_different_numbers_on_the_same_page():
    """Same sport, same page, two record spots: 5-0 at +80% is the likely
    book and 2-1 at +23% is the edge book, and neither is the other."""
    conn = _conn()
    _edge_rows(conn)
    _likely_rows(conn)
    br = ledger.book_records(conn)["mlb"]
    assert (br["edge"]["w"], br["edge"]["l"]) == (2, 1)
    assert (br["likely"]["w"], br["likely"]["l"]) == (5, 0)
    # `book_records` rounds ROI to four places; compare at that grain.
    assert abs(br["edge"]["roi"] - (0.7 / 3.0)) < 1e-4
    assert abs(br["likely"]["roi"] - (0.4 / 0.5)) < 1e-4
    rep = ledger.sport_report(conn, "mlb")["overall"]
    assert rep["settled"] == 3 and rep["wins"] == 2, \
        "the sport headline is the edge book alone"


def test_no_headline_reader_admits_the_likely_book_by_default():
    """The property the two tests above rest on, stated at the source so
    a future default cannot quietly widen."""
    import inspect
    for fn in (ledger.performance, ledger.pnl_curve, ledger.recent_settled,
               ledger.calibration, ledger.calibration_splits, ledger.era_report):
        src = inspect.getsource(fn)
        assert "'likely'" not in src and '"likely"' not in src, fn.__name__
    assert ledger.BOOK == ("main", "paper"), ledger.BOOK


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
