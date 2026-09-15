"""Adding a book spends nothing; adding a pull window spends everything.

Ethan, 2026-09-15, delegating the call with a constraint: "I would like
you too choose what you think is best. I just don't want too drain my
100k api credits immediately is all. We still need too keep a budget for
100k credits a month and remember nfl prioritizes all on thurdays,
sundays, and mondays."

THE TWO LEVERS PRICE DIFFERENTLY AND THAT IS THE WHOLE DECISION. The API
bills per MARKET per region — `oddsbudget`'s header records the 4-8x
overspend that burned 19k of a 20k plan in a day when the pacer counted
requests while the meter counted credits. `bookmakers` is a FILTER on a
response already paid for. So:

    more books   free      taken
    more pulls   billed    declined, pending a free measurement

This file is what stops the first half of that from quietly becoming
false. If a future change makes the book list a cost multiplier, the
reasoning above stops holding and the list needs to shrink again — and
nothing else in the codebase would notice.

Run directly: `python3 tests/test_books_are_free.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget                                 # noqa: E402
from engine.sources import oddsapi                            # noqa: E402


def test_the_credit_estimate_has_no_book_term():
    """THE LOAD-BEARING FACT. `affordable_events` takes credits per
    EVENT; nothing in its signature or body knows how many books were
    asked for. If that ever changes, lengthening the list starts costing
    money and the comment justifying it becomes a lie."""
    sig = inspect.signature(oddsbudget.affordable_events)
    assert "book" not in str(sig).lower(), sig
    body = inspect.getsource(oddsbudget.affordable_events)
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "book" not in code.lower(), \
        "the credit estimate now depends on the book list"


def test_the_pacer_meters_markets_and_not_books():
    """The other half of the same claim, one level up: the per-event
    credit figure is built from MARKETS."""
    # The statement lives on the constant that encodes it, which is
    # BELOW the imports — a first draft here sliced above `from
    # __future__` and failed on a module that says the right thing in
    # the right place.
    src = inspect.getsource(oddsbudget)
    assert "per MARKET per region" in src, \
        "the module no longer states what it is billed on"
    i = src.index("per MARKET per region")
    near = src[i:i + 600]
    assert "multiplies the event count" in near, near[:300]


def test_every_book_we_ask_for_has_a_name_to_print():
    """A key with no title renders as a raw slug on a card — the failure
    that made "Moneyline · best" ship (see `likely`'s note on it)."""
    for key in oddsapi.DEFAULT_BOOKS:
        assert key in oddsapi.BOOK_TITLES, key
        assert oddsapi.BOOK_TITLES[key].strip(), key


def test_the_sharp_set_is_not_a_place_to_park_a_hunch():
    """`engine/booksharp` exists because "received wisdom about which
    book is sharp is the single most repeated claim in this industry and
    the least often checked". Naming a book sharp is a PRICING claim: it
    decides which number other prices are judged against, and
    `odds.is_sharp_book` also stops that book being quoted as the
    ticket. Growing this set belongs to a measurement, not to a commit
    message."""
    assert oddsapi.SHARP_BOOKS == {"pinnacle"}, (
        "a book was named sharp — if booksharp measured it, update this "
        "test and say which run; if not, that is the claim this guards")


def test_a_bettable_book_is_never_also_the_sharp_reference():
    """The two roles are exclusive by construction: the reference must
    never be quoted as the price to take, so anything in the sharp set
    that a reader could click would be a ticket nobody can buy."""
    from engine.odds import is_sharp_book
    bettable = [b for b in oddsapi.DEFAULT_BOOKS if b not in oddsapi.SHARP_BOOKS]
    assert bettable, "every book is a reference and none is a ticket"
    for key in bettable:
        assert not is_sharp_book(key), key
    for key in oddsapi.SHARP_BOOKS:
        assert is_sharp_book(key), key


def test_the_list_only_grows_with_a_reason_written_beside_it():
    """The comment above DEFAULT_BOOKS is what a future reader needs to
    know before shortening it to "save credits" — which would save
    nothing and cost the consensus tier."""
    src = inspect.getsource(oddsapi)
    i = src.index("DEFAULT_BOOKS = [")
    head = src[max(0, i - 1800):i]
    assert "FILTERS" in head or "filter" in head.lower(), head[-400:]
    assert "MIN_CONSENSUS_BOOKS" in head, \
        "the reason more books helps the selector is not written down"


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
