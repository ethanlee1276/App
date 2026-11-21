"""Anytime-touchdown prices follow the exchange rule the props follow.

Ethan, 2026-09-26: "if the Novig prices are almost the same as the sports
book prices, then it does not matter." The prop shop took an exchange's
price only when the best sportsbook was within odds.EXCHANGE_NEAR_PROB;
the scorer shop (oddsapi.best_scorer_price, both football leagues) took
the highest number wherever it was — "McCaffrey · Anytime TD · Novig -223"
on the board that evening. Now both answer to one rule.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources.oddsapi import best_scorer_price  # noqa: E402


def test_novig_far_better_than_every_book_is_not_the_price():
    q = [{"book": "Novig", "yes_odds": -150}, {"book": "DraftKings", "yes_odds": -220},
         {"book": "FanDuel", "yes_odds": -230}]
    assert best_scorer_price(q)["book"] == "DraftKings"


def test_novig_about_the_same_as_a_book_is_fine():
    q = [{"book": "Novig", "yes_odds": -215}, {"book": "DraftKings", "yes_odds": -220},
         {"book": "FanDuel", "yes_odds": -230}]
    assert best_scorer_price(q)["book"] == "Novig"


def test_an_exchange_alone_is_still_a_price_and_a_book_best_is_untouched():
    assert best_scorer_price([{"book": "Novig", "yes_odds": 140}])["book"] == "Novig"
    q = [{"book": "FanDuel", "yes_odds": 160}, {"book": "Novig", "yes_odds": 150}]
    assert best_scorer_price(q)["book"] == "FanDuel"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
