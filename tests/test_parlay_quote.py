"""The one number the parlay model has never had.

No odds feed we ingest carries same-game-parlay quotes, and an SGP price
is not derivable from the leg prices — the whole point of the correlation
tax is that only the book knows it. So every ticket in the journal has
been graded against `assumed_dec`: the naive product less the MID-POINT
of a 15-to-30-point band the doc guesses at. Which end of that band a
book actually sits on is the entire difference between a ticket worth
taking and a dead one.

Two things start working the moment real quotes exist, and neither can
work without them. Grading runs on money instead of an assumption. And
`_tax_by_book` — written months ago, measuring nothing since, because it
divides by a column that was always NULL — starts filling in what each
book charges. That table IS the parlay edge: the same ticket is +EV at a
book taxing 18% and dead at one taxing 26%.

Run directly: `python3 tests/test_parlay_quote.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlayledger as PL


def _conn(status="open", naive=4.00, assumed=3.10, tax=0.225):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    c.execute("INSERT INTO parlays (ts,sport,date,legs_key,n_legs,parlay_type,"
              "grade,naive_product_dec,assumed_dec,correlation_tax,status,"
              "notional_units,source) VALUES ('t','nfl','2026-09-13','k',2,'A',"
              "'marginal',?,?,?,?,1.0,'edge')", (naive, assumed, tax, status))
    c.commit()
    return c


def _row(c, i=1):
    return dict(c.execute("SELECT * FROM parlays WHERE id=?", (i,)).fetchone())


def test_a_bare_number_is_refused():
    """"340" is +340 to a bettor and 340.0 to a parser, and the two
    differ by a factor of a hundred. A price entered wrong is worse than
    no price, because the tax table cannot tell that it is wrong."""
    c = _conn()
    for bad in ("340", "3.40", "abc", ""):
        try:
            PL.record_quote(c, 1, bad)
        except ValueError as exc:
            assert "sign" in str(exc) or "American" in str(exc), (bad, exc)
        else:
            raise AssertionError(f"{bad!r} was accepted")
    assert _row(c)["quoted_dec"] is None


def test_a_price_no_book_could_post_is_refused():
    c = _conn()
    for bad in ("+50", "-99", "+0"):
        try:
            PL.record_quote(c, 1, bad)
        except ValueError as exc:
            assert "book" in str(exc) or "sign" in str(exc), (bad, exc)
        else:
            raise AssertionError(f"{bad!r} was accepted")


def test_the_tax_is_derived_rather_than_asked_for():
    """The person entering this can see one number: what the book
    offered. Asking them for the tax as well would be asking them to do
    arithmetic the row already contains."""
    c = _conn(naive=4.00)
    got = PL.record_quote(c, 1, "+290", "dk")
    assert got["quoted_dec"] == 3.9
    assert abs(got["correlation_tax"] - (1 - 3.9 / 4.0)) < 1e-9
    r = _row(c)
    assert r["price_basis"] == "quoted" and r["book"] == "dk"
    assert abs(r["correlation_tax"] - 0.025) < 1e-9


def test_a_real_quote_beats_the_assumption_when_grading():
    """THE POINT. `assumed_dec` is a guess at the mid-point of a band;
    once a book has told us its price, grading against the guess throws
    away the only real number on the row."""
    src = (ROOT / "engine" / "parlayledger.py").read_text()
    assert 'price = float(p["quoted_dec"] or p["assumed_dec"] or 0.0)' in src
    # And a voided leg reprices at the ticket's OWN measured tax, not the
    # assumed band — the book already said what it charges on these legs.
    i = src.index('if void:', src.index('price = float(p["quoted_dec"]'))
    block = src[i:i + 700]
    assert 'p["quoted_dec"] and p["naive_product_dec"]' in block, block[:300]


def test_a_graded_ticket_is_reopened_rather_than_rescored_here():
    """A second copy of the settle arithmetic living in a recorder is the
    one that drifts. Same rule the home-run side repair follows."""
    c = _conn(status="lost")
    c.execute("UPDATE parlays SET pnl_units=-1.0, legs_won=0, legs_lost=2")
    c.commit()
    got = PL.record_quote(c, 1, "+290")
    assert got["reopened"] is True
    r = _row(c)
    assert r["status"] == "open" and r["pnl_units"] is None
    assert r["legs_won"] is None and r["legs_lost"] is None


def test_an_open_ticket_is_not_reopened():
    c = _conn(status="open")
    assert PL.record_quote(c, 1, "+290")["reopened"] is False
    assert _row(c)["status"] == "open"


def test_a_quote_above_the_naive_product_is_recorded_and_flagged():
    """A negative tax is a boost or a typo, never an ordinary SGP price.
    Refusing it would lose a real promo; accepting it silently would let
    a boost average into the by-book table and make that book look
    cheaper than it is on the tickets you would actually take."""
    c = _conn(naive=4.00)
    got = PL.record_quote(c, 1, "+450")
    assert got["boosted"] is True and got["correlation_tax"] < 0
    assert _row(c)["quoted_dec"] == 5.5


def test_the_work_list_shows_only_tickets_without_a_price():
    c = _conn()
    assert [r["id"] for r in PL.awaiting_quote(c)] == [1]
    PL.record_quote(c, 1, "+290")
    assert PL.awaiting_quote(c) == []


def test_the_work_list_includes_tickets_the_screen_refused():
    """The tax is a fact about a BOOK, not about a ticket we liked. A
    refused ticket is priced by the same book on the same kind of legs;
    recording only the qualified ones would measure the tax exactly where
    we happened to approve of it."""
    c = _conn()
    c.execute("UPDATE parlays SET qualified=0, grade='short'")
    c.commit()
    assert [r["id"] for r in PL.awaiting_quote(c)] == [1]


def test_an_unknown_ticket_is_refused_rather_than_silently_missed():
    c = _conn()
    try:
        PL.record_quote(c, 999, "+290")
    except KeyError as exc:
        assert "999" in str(exc)
    else:
        raise AssertionError("a quote landed on nothing")


def test_the_by_book_table_can_finally_measure_something():
    """`_tax_by_book` divides by `quoted_dec`. It has returned nothing
    since it was written, because that column was never once populated."""
    c = _conn(naive=4.00)
    assert not (PL._tax_by_book(c).get("books") or [])
    PL.record_quote(c, 1, "+290", "dk")
    out = PL._tax_by_book(c)
    books = out.get("books") or []
    assert [b["book"] for b in books] == ["dk"], books
    # +290 against a 4.00 naive product: the book kept 2.5% of the
    # theoretical price. The key is `avg_tax`, which is what the report
    # renders — asserting on a name I found convenient would have passed
    # here and shown a blank column on the page.
    assert abs(books[0]["avg_tax"] - 0.025) < 1e-6, books
    # And the note beside the table must stop saying the table is empty
    # the moment it is not. A column of real numbers under a sentence
    # explaining that no real numbers exist is worse than either alone.
    assert "Empty until" not in out["note"], out["note"]
    assert "dk" not in out["note"]


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
