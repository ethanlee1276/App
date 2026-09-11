"""College runs the stale-line scan, and its flags reach the shadow book.

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

The best-measured signal in this repository is a book pricing a side a
point under the field's consensus (64.8% against the close on 30,448
harvested quotes). The NFL and MLB builds run `marketscan` over their
priced boards, show the flags, and journal them at a flat 0.1u so
`ledger.stale_verdict` can say per sport whether taking the price pays.
`cfb_build` shipped `market_scan` as an empty literal from the day it
was written: no college flag was ever shown, journaled or judged. The
college prop rows come through the shared `price_props` and carry the
same `all_lines`, so the scan is the shared one, under its public name.

Run directly: `python3 tests/test_cfb_stale_scan.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, pipeline                           # noqa: E402


def _row(player, market, lines, **kw):
    """A college prop row as `price_props` writes it — only the fields
    the scan reads. ``lines`` is ``[(book, line, over, under)]``."""
    r = {"player": player, "team": "TOL", "market": market,
         "market_label": market.replace("_", " "), "has_market": True,
         "game_date": "2026-09-12", "live": False, "warnings": [],
         "all_lines": [{"book": b, "line": ln, "over_odds": o, "under_odds": u}
                       for b, ln, o, u in lines]}
    r.update(kw)
    return r


def test_the_scan_runs_on_college_prop_rows():
    """Three books on 75.5 rushing yards; one pays −102 on the over where
    the other two pay −118 and −120 — 3.8 points under their consensus,
    past the one-point gap — and all three agree on the under. One
    flag, on that book, on the over."""
    rows = [_row("Runner A", "rush_yds", [("DraftKings", 75.5, -118, -110),
                                           ("FanDuel", 75.5, -120, -110),
                                           ("BetMGM", 75.5, -102, -110)]),
            # A prop every book prices the same is never a flag.
            _row("Runner B", "rush_yds", [("DraftKings", 60.5, -110, -110),
                                           ("FanDuel", 60.5, -110, -110),
                                           ("BetMGM", 60.5, -110, -110)])]
    scan = pipeline.market_scan(rows)
    assert set(scan) >= {"stale", "arbs", "middles", "low_holds", "longshots"}, scan.keys()
    assert len(scan["stale"]) == 1, scan["stale"]
    flag = scan["stale"][0]
    assert (flag["player"], flag["market"], flag["book"], flag["side"], flag["line"]) == \
        ("Runner A", "rush_yds", "BetMGM", "OVER", 75.5), flag
    assert flag["odds"] == -102 and flag["gap_pts"] >= 1.0 and flag["books_compared"] == 3


def test_the_scan_is_the_shared_one():
    """College calls the NFL's scan by its public name — not a copy that
    could drift from the thresholds the 64.8% was measured at."""
    assert pipeline.market_scan is pipeline._market_scan
    src = inspect.getsource(pipeline.run_slate)
    assert "_market_scan(" in src, "the NFL board no longer runs the scan"


def test_college_flags_journal_to_the_shadow_book_and_reach_the_verdict():
    rows = [_row("Runner A", "rush_yds", [("DraftKings", 75.5, -118, -110),
                                           ("FanDuel", 75.5, -120, -110),
                                           ("BetMGM", 75.5, -102, -110)]),
            # An in-play price is stale for reasons the scanner cannot
            # see, and is never journaled.
            _row("Runner C", "rec_yds", [("DraftKings", 40.5, -118, -110),
                                          ("FanDuel", 40.5, -120, -110),
                                          ("BetMGM", 40.5, -102, -110)], live=True)]
    result = {"sport": "cfb", "date": "2026-09-12", "market_scan": pipeline.market_scan(rows)}
    assert len(result["market_scan"]["stale"]) == 2
    conn = ledger.connect(":memory:")
    assert ledger.log_stale_flags(conn, result) == 1
    got = conn.execute("SELECT sport, date, player, market, side, line, book, odds, "
                       "stake_units, stake_dollars, category, status FROM bets").fetchall()
    assert [tuple(r) for r in got] == [
        ("cfb", "2026-09-12", "Runner A", "rush_yds", "OVER", 75.5, "BetMGM", -102,
         0.1, 0.0, "stale", "open")], [tuple(r) for r in got]
    # Journaling twice is once.
    assert ledger.log_stale_flags(conn, result) == 0
    # Settled, the row is a college sample for the per-sport verdict —
    # held, at one flag, for the sample floor.
    conn.execute("UPDATE bets SET status='won', actual=80.0, pnl_units=0.098")
    conn.commit()
    v = ledger.stale_verdict(conn)
    assert "cfb" in v and v["cfb"]["n"] == 1 and v["cfb"]["verdict"] == "hold", v


def test_the_build_scans_its_board_and_journals_the_flags():
    import cfb_build as CB
    src = inspect.getsource(CB.main)
    # The scan runs on the priced board, after the props and the long
    # shots exist and before the journal reads it.
    i_props = src.index('out["recommendations"] = _price_props(')
    i_scan = src.index('out["market_scan"] = _market_scan(')
    i_journal = src.index("ledger.log_stale_flags(")
    assert i_props < i_scan < i_journal, (i_props, i_scan, i_journal)
    assert 'out.get("long_shots") or []' in src[i_scan:i_scan + 200]
    # The empty literal stays as the default so the key is on every path
    # — a build that never priced a prop still publishes the shape.
    assert src.count('"market_scan": {"stale": [], "arbs": [], "middles": [], "low_holds": [],') == 1
    # The journal call carries the sport and the slate date the shadow
    # book settles on.
    seg = src[i_journal:i_journal + 300]
    assert '"sport": "cfb"' in seg and '"date": args.date' in seg, seg


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
