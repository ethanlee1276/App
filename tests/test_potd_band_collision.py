"""`MIN_FAIR` and `MAX_EV` meet at +114, and the band says +190.

Two bars that are each defensible alone, multiplied together, quietly
shorten the price band the feature advertises. `potd.MAX_ODDS` reads 190
and since 2026-09-16 no row above +114 can reach the pick at all:

    EV at the fair floor = MIN_FAIR × (1 + payout) − 1

At +114 that is exactly 7.0% — `MAX_EV`. At +115 it is 7.5%, so a row
there is refused as a suspect gap if it clears `MIN_FAIR` and refused by
`MIN_FAIR` if it does not. There is no price in between.

WHY THIS FILE EXISTS RATHER THAN A COMMENT. The crossing point is a
PRODUCT of two constants neither of which mentions the other, so it
moves whenever either moves and nothing anywhere would notice. That is
the failure mode: `MAX_ODDS` is the number a reader trusts, and it has
been describing a band the selector cannot use since the ceiling landed.
Anyone who moves `MIN_FAIR` or `MAX_EV` should be told what the real
ceiling became, and docs/PICK_OF_THE_DAY.md §3i-b should be updated to
match.

THIS IS NOT AN ARGUMENT THAT THE BARS ARE WRONG. `MIN_FAIR` is Ethan's
product bar; `MAX_EV` is the pricer's own trust line. The file measures
the consequence and refuses to let it go unnoticed.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

#: The highest plus price at which a row can satisfy both bars, and the
#: figure docs/PICK_OF_THE_DAY.md §3i-b quotes.
DOCUMENTED_CEILING = 114


def _highest_reachable_plus_price():
    """The last plus price where even the loosest allowed fair is still
    inside the trust ceiling. Derived, never restated."""
    best = None
    for odds in range(100, int(potd.MAX_ODDS) + 1):
        pay = potd.payout(odds)
        if pay is None:
            continue
        if potd.MIN_FAIR * (1.0 + pay) - 1.0 <= potd.MAX_EV + 1e-12:
            best = odds
    return best


def test_the_two_bars_cross_where_the_docs_say_they_do():
    got = _highest_reachable_plus_price()
    assert got == DOCUMENTED_CEILING, (
        f"the bars now cross at {got:+d}, not {DOCUMENTED_CEILING:+d} — "
        f"MIN_FAIR={potd.MIN_FAIR}, MAX_EV={potd.MAX_EV}. Update "
        f"docs/PICK_OF_THE_DAY.md §3i-b and this constant together.")


def test_the_advertised_band_is_wider_than_the_usable_one():
    """The whole point. If these ever agree, the collision is gone and
    this file can go with it."""
    assert potd.MAX_ODDS > DOCUMENTED_CEILING, (
        "MAX_ODDS no longer overstates the plus side — delete this file")


def _row(fair, odds):
    """A sharp-anchored game row that clears every bar except the two
    under test, so whatever `shortfall` says is about those two."""
    return {"kind": "game", "market": "moneyline", "sharp_anchored": True,
            "bettable": True, "rank_auc": 0.71, "book": "DraftKings",
            "sharp_fair": fair, "odds": odds}


def test_a_price_past_the_crossing_is_refused_whichever_side_it_falls_on():
    """Behavioural, not arithmetic: the refusal is `shortfall`'s, at a
    real price, both ways round. There is no third answer at +150."""
    # Clears MIN_FAIR at +150 → the edge is 25%, past the ceiling.
    assert potd.shortfall(_row(0.50, 150)) == \
        "the gap is too big to trust — the sharp side has probably moved"

    # Inside the ceiling at +150 → the fair has to be under 43%.
    assert potd.shortfall(_row(0.42, 150)) == \
        "more likely to lose than to win, even at a good price"


def test_the_minus_side_of_the_band_is_untouched():
    """The collision is a plus-money fact. A favourite at -130 needing a
    57% fair is an ordinary row and still clears everything."""
    assert potd.shortfall(_row(0.58, -130)) == "", potd.shortfall(_row(0.58, -130))


def test_the_plus_side_window_closes_as_the_price_climbs():
    """The shape of the thing, not one point on it. At +100 there is a
    real spread of fairs that clear both bars; by the crossing it is a
    single value; past it there is nothing."""
    def window(odds):
        pay = potd.payout(odds)
        lo = max(potd.MIN_FAIR, (1.0 + potd.MIN_EV) / (1.0 + pay))
        hi = (1.0 + potd.MAX_EV) / (1.0 + pay)
        return max(0.0, hi - lo)

    assert window(100) > window(110) > window(DOCUMENTED_CEILING - 1)
    assert window(DOCUMENTED_CEILING) < 1e-9, window(DOCUMENTED_CEILING)
    assert window(DOCUMENTED_CEILING + 1) == 0.0
    assert window(int(potd.MAX_ODDS)) == 0.0


def test_the_minus_side_is_still_bounded_by_the_band_itself():
    """`MIN_FAIR` cannot bite on a favourite — a minus price needs a fair
    above 50% to show any edge at all — so on that side `MIN_ODDS` is
    still the real floor and nothing is being hidden."""
    pay = potd.payout(potd.MIN_ODDS)
    assert potd.MIN_FAIR * (1.0 + pay) - 1.0 < potd.MIN_EV, \
        "a 50% fair now shows an edge at the worst price in the band"


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
