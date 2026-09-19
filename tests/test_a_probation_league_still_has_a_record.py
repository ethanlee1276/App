"""A league on probation still has a record, and the page must draw it.

Ethan, 2026-09-19. His Record page said "Nothing journaled for College
Football yet" while the file it was rendering carried 246 graded college
Most Likely rows. Both halves were true at once, which is why four
rounds of reading the journal found nothing.

    cfb   by_sport settled     0  open    0  |  books: likely 246

`by_sport[sport].overall` comes from `ledger.performance`, and that
function's SQL is `category IN ('main','paper') AND stake_units > 0` —
the EDGE book, staked, with a comment saying so: "rows staked at zero
were never money and are reported separately as `unstaked`". A league
whose picks are journaled at a ZERO STAKE therefore reads 0 settled and
0 open there no matter how full its other books are.

A zero stake is exactly what PROBATION means, and college football has
been on it all season — `engine/maintenance` calls it "journaled and
graded, never staked". So the Record page asked the one book college
cannot have rows in, believed the answer, and returned before
`recBookSections` could draw the two that were full.

`book_records` carries no stake filter, so it is the honest test of
whether a league has a record worth rendering.

Run directly: `python3 tests/test_a_probation_league_still_has_a_record.py`
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def has_something(overall, books):
    """`recordHasSomething` run against the real source."""
    js = f"""
    {_fn("recordHasSomething")}
    console.log(JSON.stringify(recordHasSomething(
        {json.dumps(overall)}, {json.dumps(books)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


#: Ethan's own numbers, 2026-09-19.
CFB_OVERALL = {"settled": 0, "open": 0}
CFB_BOOKS = {"likely": {"w": 130, "l": 116}}


# --- the bug -----------------------------------------------------------
def test_a_league_with_a_full_likely_book_and_no_staked_edge_bets_is_not_empty():
    """THE CASE. 246 graded Most Likely rows, zero staked edge bets,
    and a page that said the league had never journaled anything."""
    assert has_something(CFB_OVERALL, CFB_BOOKS) is True, (
        "a league with 246 graded rows in a rendered book reads as empty "
        "— the Record page will bail before drawing them")


def test_the_long_shots_book_counts_too():
    """Probation does not single out one book."""
    assert has_something({"settled": 0, "open": 0},
                         {"longshots": {"w": 3, "l": 9}}) is True


def test_an_edge_record_still_counts_on_its_own():
    """The original test has to keep working: a staked league with no
    other books is not empty either."""
    assert has_something({"settled": 41, "open": 6}, {}) is True
    assert has_something({"settled": 0, "open": 6}, {}) is True


# --- and a genuinely empty league stays empty --------------------------
def test_a_league_with_nothing_anywhere_is_still_empty():
    """The empty state exists for a reason — Ethan, 2026-09-06, on the
    NBA drawing five panels that said nothing. That stays."""
    assert has_something({"settled": 0, "open": 0}, {}) is False
    assert has_something({}, None) is False


def test_a_book_present_but_ungraded_is_not_a_record():
    """A section with a zero-zero record draws an empty card. Counting
    it would put the cluttered page back."""
    assert has_something({"settled": 0, "open": 0},
                         {"likely": {"w": 0, "l": 0}}) is False


def test_a_push_alone_does_not_make_a_record():
    """`recBookSections` itself skips a book on `!(b.w + b.l)`, so the
    two must agree or the page draws a header over nothing."""
    assert has_something({"settled": 0, "open": 0},
                         {"likely": {"w": 0, "l": 0, "push": 4}}) is False


# --- the page actually asks it -----------------------------------------
def test_the_empty_branch_consults_the_books():
    src = APP[APP.index("function renderRecord"):]
    src = src[:src.index("\n}\n")]
    assert "recordHasSomething(o, (d.book_records || {})[scope])" in src, \
        "the empty state is back to asking only the staked edge book"
    assert "if (scoped && !o.settled && !o.open)" not in src, \
        "the old two-field test is still there"


def test_the_helper_agrees_with_what_the_sections_draw():
    """`recBookSections` renders a book when `b.w + b.l` is non-zero.
    If this helper used a different rule the page would either bail with
    rows to show or draw a heading over an empty card."""
    body = _fn("recordHasSomething")
    assert "w" in body and "l" in body, body
    assert "push" not in body, \
        "a push is settled but not graded; recBookSections ignores it"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
