"""An exchange's ladder rung never becomes a prop's line.

The droplet, 2026-09-25 (Ethan's box check): Quinshon Judkins's rushing
prop was priced at Under 29.5 +104 on Novig. No sportsbook hangs 29.5 —
DraftKings had it only as an alternate, over at -880 — and his main number
is in the sixties. Our model had him at 31.5, so `betting.pick_side`'s
plausibility filter dropped every sportsbook's main line (our number
disagreed with each of them) and shopped what was left: the one exchange
rung that agreed with the model. The no-pick card then called Over 109.5
at +900 his "likeliest over". David Montgomery (Under 29.5, Novig) and
Elic Ayomanor (Over 9.5 receiving yards, ProphetX/Novig) were the same.

The market's number is now judged on every quote before the model filters
any (`odds.market_field`), an exchange never sets the centre while a
sportsbook quotes, and an exchange's quote is shopped only at a number a
sportsbook also hangs. A model far off the market then meets the market's
own number, and `quote_prices_its_line` refuses it out loud.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import betting as BT                                  # noqa: E402
from engine import odds as O                                      # noqa: E402
from engine.models import SportsbookLine as L                     # noqa: E402
from engine.statmath import prob_over                             # noqa: E402


def _judkins():
    return [L(book="DraftKings", line=64.5, over_odds=-115, under_odds=-115),
            L(book="FanDuel", line=65.5, over_odds=-110, under_odds=-110),
            L(book="BetMGM", line=64.5, over_odds=-120, under_odds=-110),
            L(book="Novig", line=29.5, over_odds=-953, under_odds=104),
            L(book="ProphetX", line=29.5, over_odds=-1300, under_odds=0)]


def test_the_model_far_off_the_market_meets_the_markets_number():
    side, best, *_ = BT.pick_side(_judkins(), lambda x: prob_over(x, 31.5, 27.757))
    assert best.line in (64.5, 65.5), (side, best)
    assert not O.is_exchange(best.book), best
    # …and the plausibility check then refuses it rather than a rung
    # quietly agreeing with us.
    assert not BT.quote_prices_its_line(side, best, lambda x: prob_over(x, 31.5, 27.757))


def test_an_exchange_never_sets_the_centre_while_a_book_quotes():
    assert O.market_centre(_judkins()) in (64.5, 65.5)
    only = [L(book="Novig", line=29.5, over_odds=-110, under_odds=-110)]
    assert O.market_centre(only) == 29.5, "an exchange alone is still a market"


def test_an_exchange_is_shopped_at_the_books_number():
    field = [L(book="DraftKings", line=3.5, over_odds=-130, under_odds=100),
             L(book="Novig", line=3.5, over_odds=-118, under_odds=108),
             L(book="Novig", line=2.5, over_odds=-300, under_odds=240)]
    over = O.best_over_line(field)
    assert (over.line, over.book) == (3.5, "Novig"), "the exchange's price at the book's number is a shop"
    assert O.is_exchange("ProphetX") and O.is_exchange("novig") and not O.is_exchange("DraftKings")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
