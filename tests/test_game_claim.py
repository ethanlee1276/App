"""A game card printed the book's own number under the word MODEL.

Ethan, 2026-09-03, on a MIN ML −220 card sitting on the Most Likely
board: *"These lines along with more are completely wrong, none of these
teams are favored to win on any sports book."*

The card contradicted itself, and both halves were on screen at once:

    MODEL 67%   BOOK IMPLIED 67%
    ✓ Model win probability 33% vs book's 33% — a +0.1% edge on GB
    ✗ Model disagrees with the market by more than 10% — a rating error
    ✓ Power rating: MIN +0.5 vs GB +1.1 net pts/game (incl. home field)

It cannot both agree to a tenth of a point and disagree by more than
ten. And the power-rating line argues against the pick: our own ratings
make GREEN BAY the better team, while the card makes Minnesota a 67%
favourite.

BOTH FOLLOW FROM ONE THING. `gamebets.temper` publishes

    win_prob = fair + shrink x (raw - fair)

and NFL's moneyline shrink is measured at no information — the card says
so itself: "over 1181 graded games this model's disagreements with the
closing number carried no information. Priced at the market until that
changes." So `win_prob` IS the book's de-vigged number, printed as the
model's; the ✓ line quotes it, and the ✗ flag reads `credible`, which
`temper_edge` computes from the RAW claim. Two numbers, one label.

WHY THE BOARD ADMITTED IT. `likely.engine_credible` — the guard written
for the Gelof card on 2026-09-02 — asks the engine's question of the
engine's number: is the PRE-SHRINK claim within MAX_CREDIBLE_EDGE of the
book's fair? Game rows carried no `engine_raw_prob`, so it answered True
for every one of them and the whole shelf went through ungated. The bar
existed and was blind to this board.

So the makers carry the claim, `from_game_bet` flips it with the side
(every one of these markets is two-way, and an unflipped claim would be
compared against the other team's fair), and the existing bar does the
rest.

ONLY ON A MARKET THAT CLAIMS A RANKING. Spreads and totals ship as
labelled leans because Ethan asked to see them, and there the model
disagrees with the close by thirty points as a matter of course —
feeding those to this bar would empty both shelves and reverse his call
without asking.

Run directly: `python3 tests/test_game_claim.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamebets as G, likely                     # noqa: E402
import engine.gamecal as gamecal                             # noqa: E402


def _no_information(fn):
    """Run with NFL's measured moneyline haircut: priced at the market."""
    def run(*a, **k):
        real = gamecal.shrink_for
        gamecal.shrink_for = lambda sport, market: 0.0
        try:
            return fn(*a, **k)
        finally:
            gamecal.shrink_for = real
    run.__name__ = fn.__name__
    run.__doc__ = fn.__doc__
    return run


def _ml(home, away, home_rating, away_rating, home_ml, away_ml):
    wp = G.nfl_win_prob(home_rating, away_rating)
    return G.moneyline_to_dict(
        G.price_moneyline(home, away, wp, home_ml, away_ml, sport="nfl"))


#: The screenshot: GB @ MIN, our ratings making GB the better side, the
#: feed making MIN a −220 favourite.
def _the_card():
    return _ml("MIN", "GB", 0.5, 1.1, -220, +200)


# --- the report ------------------------------------------------------------
@_no_information
def test_the_card_stops_calling_the_books_number_its_own():
    """With the haircut at no information the two are equal by
    construction — so the row has to carry the claim they came from, or
    nothing downstream can tell them apart."""
    card = _the_card()
    assert card["engine_raw_prob"] is not None, \
        "the moneyline card does not carry its pre-shrink claim"
    assert abs(card["win_prob"] - card["fair_prob"]) < 0.005, \
        "this fixture is not exercising a market-priced card"
    assert abs(card["engine_raw_prob"] - card["fair_prob"]) > 0.10, \
        "the model's own claim does not disagree; wrong fixture"


@_no_information
def test_the_screenshots_row_is_refused_by_the_board():
    """THE BUG. Our ratings put Minnesota near a coin flip; the board
    ranked them a 67% favourite on the book's number."""
    row = likely.from_game_bet(dict(_the_card()), "nfl")
    assert row is not None and row["player"].startswith("MIN"), row
    why = likely.admissible(row)
    assert why, "the board still admits a row the engine does not credit"
    assert "disagree" in why, why


@_no_information
def test_a_favourite_the_ratings_agree_with_still_ships():
    """The bar must not empty the shelf. Where the model and the market
    both make a team a heavy favourite, that is the row this board is
    for."""
    row = likely.from_game_bet(dict(_ml("KC", "DEN", 6.0, 0.0, -220, +200)), "nfl")
    assert row is not None, "a favourite we agree with was refused outright"
    assert likely.admissible(row) == "", likely.admissible(row)


@_no_information
def test_the_claim_flips_with_the_side():
    """Every market here is two-way. The edge card backs the dog on
    price and the board shows the favourite, so an unflipped claim would
    be compared against the OTHER team's fair — a guard reading two
    numbers about different teams."""
    card = _the_card()
    row = likely.from_game_bet(dict(card), "nfl")
    assert row["flipped"] is True, row
    assert abs(row["engine_raw_prob"] - (1.0 - card["engine_raw_prob"])) < 1e-9, \
        "the pre-shrink claim did not flip with the side"


# --- the half that must NOT change ----------------------------------------
def test_an_unranked_lean_is_not_held_to_the_ranking_bar():
    """Ethan asked to see spreads and totals as labelled leans
    (2026-09-02). The model disagrees with the close there by thirty
    points routinely, so this bar would empty both shelves — and that is
    a product decision, not a bug fix."""
    # LEANS THE BOARD ALREADY SHIPS. A spread the model reads far from
    # the close (proj margin −9, or even −4, against a −3.5 line) is refused BEFORE
    # this change too, by the older bar on the shown number — checked
    # against HEAD rather than assumed, after the first version of this
    # test blamed that refusal on the new one.
    for card, what in ((G.price_total("nfl", "KC", "DEN", 41.0, 47.5, -110, -110), "total"),
                       (G.price_spread("nfl", "KC", "DEN", -3.5, -3.5), "spread")):
        row = likely.from_game_bet(dict(card), "nfl")
        assert row is not None, f"the {what} lean was refused outright"
        assert row.get("engine_raw_prob") is None, \
            f"the {what} lean is being held to the ranking bar"
        assert likely.admissible(row) == "", \
            f"the {what} lean no longer ships: {likely.admissible(row)}"


def test_the_makers_still_carry_the_claim_for_a_reader():
    """The field is on the CARD for every market even where the board
    does not gate on it — the prop page shows the model's own number
    beside a shrunk one, and a game card should be able to do the same."""
    for card, what in ((G.price_total("nfl", "KC", "DEN", 41.0, 47.5, -110, -110), "total"),
                       (G.price_spread("nfl", "KC", "DEN", -9.0, -3.5), "spread")):
        assert card.get("engine_raw_prob") is not None, what


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
