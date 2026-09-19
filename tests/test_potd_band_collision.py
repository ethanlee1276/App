"""`MIN_FAIR` and `MAX_EV` cross, and the band used to claim otherwise.

Two bars that are each defensible alone, multiplied together, shorten
the price band the feature can actually use:

    EV at the fair floor = MIN_FAIR × (1 + payout) − 1

Where that equals `MAX_EV` is the last usable price. Above it a row is
refused as a suspect gap if it clears `MIN_FAIR`, and refused by
`MIN_FAIR` if it does not. There is no price in between.

    floor 50%   +114        the plus side survives to +114   <- shipped
    floor 55%   -106        THE PLUS SIDE IS GONE ENTIRELY
    floor 58%   -118

THE FLOOR WENT TO 55% AND BACK ON 2026-09-16, and this file is why the
second move happened. Raising it closed the plus side completely — net
odds of 0.945 is a FAVOURITE, -106, not "+94"; I told Ethan +94 in chat
by reading a sub-1.0 payout as a plus price. Once that was written down
here, "the floor decides whether there are underdogs at all" became
visible, and underdogs were something he wanted ("i prefer that since it
gives us under dogs"). The arithmetic lives in this file so it is never
done from memory again.

`potd.effective_max_odds` derives it, and `build` publishes THAT as the
card's band instead of `MAX_ODDS`. The card used to read "priced between
-250 and +190" while no bet above -106 could qualify — a stated range
the machinery cannot produce, which is the same shape of untruth as the
NO BET card naming a bet.

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

#: Where the two bars cross at the SHIPPED floor. Update this and
#: docs/PICK_OF_THE_DAY.md §3i-b together whenever `MIN_FAIR` moves.
DOCUMENTED_CEILING = 114


def _last_usable_price():
    """The last price where the loosest allowed fair is still inside the
    trust ceiling, found by walking real prices rather than by algebra —
    so it is an independent check on `effective_max_odds` and not a
    second copy of it."""
    best = None
    for odds in list(range(-300, -99)) + list(range(100, 401)):
        pay = potd.payout(odds)
        if pay is None:
            continue
        if potd.MIN_FAIR * (1.0 + pay) - 1.0 <= potd.MAX_EV + 1e-12:
            if best is None or pay > potd.payout(best):
                best = odds
    return best


def test_the_two_bars_cross_where_the_docs_say_they_do():
    got = _last_usable_price()
    assert got == DOCUMENTED_CEILING, (
        f"the bars now cross at {got:+d}, not {DOCUMENTED_CEILING:+d} — "
        f"MIN_FAIR={potd.MIN_FAIR}, MAX_EV={potd.MAX_EV}. Update "
        f"docs/PICK_OF_THE_DAY.md §3i-b and this constant together.")


def test_the_derivation_agrees_with_walking_the_prices():
    """`effective_max_odds` does it in one line of algebra; the walk
    above does it by trying every price. A disagreement means the
    algebra is wrong, and the algebra is what the card prints."""
    assert potd.effective_max_odds() == _last_usable_price()


def test_the_card_advertises_the_band_it_can_actually_fill():
    """THE FAILURE THIS FILE WAS WRITTEN FOR, now closed. `MAX_ODDS`
    still bounds the candidate pool — a real job — but it is no longer
    what a reader is told."""
    assert potd.effective_max_odds() < potd.MAX_ODDS, (
        "the two agree now; the collision is gone and this file can go")
    import datetime as _dt
    got = potd.build([], "mlb", _dt.date.today().isoformat())
    assert got["band"] == [potd.MIN_ODDS, potd.effective_max_odds()], got["band"]


def test_a_floor_above_even_money_closes_the_plus_side_entirely():
    """WHY THE FLOOR IS AN UNDERDOG SWITCH — not obvious, and the fact
    that sent Ethan back to 0.50 on 2026-09-16.

    ASKED AT 0.55 EXPLICITLY, not at whatever ships. The first version
    of this returned early when `MIN_FAIR` was under 0.55, so the moment
    the floor went back to 0.50 it passed by asserting NOTHING — the
    dead-guard pattern this codebase keeps finding in its own history,
    written by me, in the file whose whole job is to notice when a bar
    stops meaning what it says. `shortfall` and `effective_max_odds`
    both take the floor as an argument; a test about a regime can ask
    for that regime instead of waiting for it to ship.
    """
    assert potd.effective_max_odds(min_fair=0.55) < 0, \
        "a 55% floor is supposed to leave no plus price at all"
    for odds in (100, 120, 150, 190):
        why = potd.shortfall(_row(0.55, odds), min_fair=0.55)
        assert "gap is too big" in why, (odds, why)


def test_the_shipped_floor_keeps_the_plus_side_open():
    """The other half, and the reason 0.50 is the shipped number: Ethan,
    2026-09-16, "i prefer that since it gives us under dogs"."""
    top = potd.effective_max_odds()
    assert top > 0, (
        f"the shipped floor ({potd.MIN_FAIR:.0%}) leaves no plus price "
        f"({top:+d}) — the Pick of the Day can never be an underdog")
    # AT THE CROSSING THE ADMISSIBLE FAIR IS THE FLOOR ITSELF — that is
    # what "crossing" means. The MIN_EV end of the window sits BELOW the
    # floor there (0.477 against 0.50 at +114), so deriving the fair
    # from MIN_EV asks the question at a price the floor already
    # refuses, which is not what this test is about.
    assert potd.shortfall(_row(potd.MIN_FAIR, top)) == "", \
        f"the crossing price {top:+d} is dead at the floor itself"


def _row(fair, odds):
    """A sharp-anchored game row that clears every bar except the two
    under test, so whatever `shortfall` says is about those two."""
    return {"kind": "game", "market": "moneyline", "sharp_anchored": True,
            "bettable": True, "rank_auc": 0.71, "book": "DraftKings",
            "sharp_fair": fair, "odds": odds}


def test_a_price_past_the_crossing_is_refused_whichever_side_it_falls_on():
    """Behavioural, not arithmetic: the refusal is `shortfall`'s, at a
    real price, both ways round. There is no third answer at +150."""
    # Clears MIN_FAIR at +150 → the edge is enormous, past the ceiling.
    # THE FAIR IS THE FLOOR ITSELF, not a hard-coded 0.50, because the
    # floor moved to 0.55 on 2026-09-16 and a fixture under it gets the
    # OTHER refusal — `shortfall` asks confidence first.
    assert potd.shortfall(_row(potd.MIN_FAIR, 150)) == \
        "the gap is too big to trust — the sharp side has probably moved"

    # Inside the ceiling at +150 → the fair has to be under 43%, which
    # is under the confidence floor. THE WORDING OF THAT REFUSAL CHANGED
    # on 2026-09-16: `MIN_FAIR` stopped being "at least a coin flip" and
    # became the floor the day's pick is chosen on, so the sentence names
    # the bar and its value rather than asserting a 50% test that is no
    # longer what the constant means.
    why = potd.shortfall(_row(0.42, 150))
    assert "not confident enough" in why, why
    assert f"{potd.MIN_FAIR:.0%}" in why, why


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

    top = potd.effective_max_odds()
    # Walk AWAY from the crossing toward shorter prices: the window opens
    # as the payout falls, and is shut at the crossing and everywhere
    # past it. Spelled in payouts rather than in American odds because
    # the sign flips across even money and the ordering does not.
    assert window(-130) > window(-115) > window(top)
    # `top` is rounded so as never to advertise an unreachable price, so
    # it is the last price with a window at all — a sliver, not zero.
    # One step shorter and it is shut.
    assert window(top) > 0.0, window(top)
    assert window(top + 1) == 0.0, (top + 1, window(top + 1))
    assert window(int(potd.MAX_ODDS)) == 0.0


def test_the_minus_side_is_still_bounded_by_the_band_itself():
    """`MIN_FAIR` alone cannot reach the bottom of the band — at
    `MIN_ODDS` a row needs a far higher fair than the floor to show any
    edge at all — so on that side `MIN_ODDS` is still the real floor and
    nothing is being hidden."""
    pay = potd.payout(potd.MIN_ODDS)
    assert potd.MIN_FAIR * (1.0 + pay) - 1.0 < potd.MIN_EV, \
        "the floor's own fair now shows an edge at the worst price in the band"


def test_the_bottom_of_the_band_is_still_reachable_by_something():
    """A band shut at both ends is a dead feature. At -250 a fair
    between about 73% and 76% clears every bar, which is narrow and
    real."""
    lo, hi = None, None
    for i in range(500, 1000):
        f = i / 1000.0
        if potd.shortfall(_row(f, potd.MIN_ODDS)) == "":
            lo = f if lo is None else lo
            hi = f
    assert lo is not None, "nothing at all can be picked at MIN_ODDS"
    assert lo < hi, (lo, hi)


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
