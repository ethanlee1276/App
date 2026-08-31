"""Does betting EARLY beat the close? The book now measures it.

Ethan, 2026-08-31: "make the model better… making more money and
winning more." The models rank well and show no edge over the CLOSING
price — but nobody has to bet the close. Every journaled pick carries
`lead_min` and, settled, the closing price beside the price taken; if
picks made days out consistently beat the close while same-day picks do
not, "bet Tuesday, not Sunday" becomes the book's own measured
instruction — the one kind of edge a small operation can keep, because
it comes from WHEN, not from out-modelling the market.

Run directly: `python3 tests/test_leadtime_clv.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger
from engine.clvboard import leadtime, leadtime_lines, LEAD_BUCKETS


def _conn(rows):
    c = ledger.connect(":memory:")
    for i, r in enumerate(rows):
        # `[{...}] * 45` is 45 references to ONE dict — copy before
        # naming, or every row shares player P0 and the unique key balks.
        r = dict(r)
        r.setdefault("player", f"P{i}")
        c.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, "
            "book, odds, closing_odds, lead_min, status, category, "
            "stake_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("nfl", "2026-09-13", r.get("player", "P"), "anytime_td",
             "over", 0.5, "dk", r["odds"], r.get("closing_odds"),
             r["lead_min"], r.get("status", "won"),
             r.get("category", "main"), 1.0))
    c.commit()
    return c


def test_early_winners_and_late_losers_land_in_their_buckets():
    """+150 closing at +120 is positive CLV (the market came to us);
    +150 closing at +180 is negative. 2+ days out gets the good ones,
    under-2h the bad — the exact split the instrument exists to see."""
    rows = ([{"odds": 150, "closing_odds": 120, "lead_min": 4000}] * 45
            + [{"odds": 150, "closing_odds": 180, "lead_min": 60}] * 45)
    got = leadtime(_conn(rows))
    by = {b["label"]: b for b in got["buckets"]}
    early, late = by["2+ days out"], by["under 2 hours"]
    assert early["settled"] == 45 and late["settled"] == 45
    assert early["avg_clv"] > 0 and early["verdict"] == "beats the close"
    assert late["avg_clv"] < 0 and late["verdict"] == "loses to the close"


def test_below_the_floor_the_counts_print_and_the_call_is_refused():
    rows = [{"odds": 150, "closing_odds": 120, "lead_min": 4000}] * 10
    got = leadtime(_conn(rows))
    early = [b for b in got["buckets"] if b["label"] == "2+ days out"][0]
    assert early["with_close"] == 10 and early["avg_clv"] is not None
    assert early["verdict"] is None, "a 10-close verdict is noise spoken aloud"


def test_a_pick_with_no_close_counts_as_settled_but_not_graded():
    rows = [{"odds": 150, "closing_odds": None, "lead_min": 4000}] * 5
    got = leadtime(_conn(rows))
    early = [b for b in got["buckets"] if b["label"] == "2+ days out"][0]
    assert early["settled"] == 5 and early["with_close"] == 0
    assert early["avg_clv"] is None


def test_the_likely_book_is_graded_apart_from_the_staked_one():
    rows = ([{"odds": 150, "closing_odds": 120, "lead_min": 4000}] * 3
            + [{"odds": 150, "closing_odds": 120, "lead_min": 4000,
                "category": "likely"}] * 7)
    c = _conn(rows)
    assert leadtime(c, "main")["buckets"][0]["settled"] == 3
    assert leadtime(c, "likely")["buckets"][0]["settled"] == 7


def test_the_buckets_tile_the_whole_timeline():
    """No lead time may fall between buckets — a pick that vanishes from
    every row is the silent-census bug in a new coat."""
    edges = sorted((lo, hi) for lo, hi, _ in LEAD_BUCKETS)
    assert edges[0][0] == 0
    for (lo1, hi1), (lo2, _) in zip(edges, edges[1:]):
        assert hi1 == lo2, (hi1, lo2)
    assert edges[-1][1] is None


def test_the_log_lines_name_both_books():
    c = _conn([{"odds": 150, "closing_odds": 120, "lead_min": 4000}])
    lines = "\n".join(leadtime_lines(c))
    assert "staked book" in lines and "likely book" in lines


def test_the_export_and_the_page_carry_it():
    with open(os.path.join(ROOT, "engine", "ledger.py"),
              encoding="utf-8") as f:
        led = f.read()
    assert '"clv_leadtime": _clv_leadtime(conn, since),' in led
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        app = f.read()
    assert "function recLeadtimeSection(lt)" in app
    assert "recLeadtimeSection(d.clv_leadtime)" in app
    with open(os.path.join(ROOT, "engine", "maintenance.py"),
              encoding="utf-8") as f:
        mnt = f.read()
    assert "leadtime_lines" in mnt


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
