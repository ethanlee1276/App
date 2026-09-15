"""A likelihood row does not print the edge board's refusal of it.

Ethan, 2026-09-08, with the Vikings card filling his phone: a green
"67%" badge and the words "The likely side" at the top, and four lines
below it, in red:

    ✗ Model disagrees with the market by more than 10% — a rating
      error, not an edge

Both sentences were true of their own board and the card carried them
together. The edge board is deciding whether to put money on OUR
number, and a rating ten points from the close is a rating error — that
refusal is why the card is not staked, and it belongs there. The
likelihood board ranks this row on the MARKET's number, where the same
disagreement was measured on 1,356 NFL closes to say nothing about how
the market's number lands (`likely.engine_credible`,
`gamerank --raw-bar`, 2026-09-08). One card, two boards' verdicts, and
a reader left to referee them.

So on a row that ranks on the market's number the staking refusal comes
off — by NAME (`gamebets.RATING_ERROR_REASON`) rather than by matching
text, so a reworded refusal cannot slip back on — and `rank_note` says
what this row is actually doing: ranked on the book's 67%, with the
model's own rating printed as 53%, and why that gap does not bar it.

What does NOT change: the edge card keeps the sentence, because that
card really is refusing to stake; a row that ranks on the MODEL's own
number keeps it too, because there the refusal is about the number the
row is sorted on.

Run directly: `python3 tests/test_row_does_not_refuse_itself.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import gamebets as G, likely as K                  # noqa: E402
import engine.gamecal as gamecal                               # noqa: E402


def _no_information(fn):
    """NFL's measured moneyline haircut: priced at the market."""
    def run(*a, **k):
        real = gamecal.shrink_for
        gamecal.shrink_for = lambda sport, market: 0.0
        try:
            return fn(*a, **k)
        finally:
            gamecal.shrink_for = real
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run


def _card(home_rating=0.5, away_rating=1.1, home_ml=-220, away_ml=200):
    """The screenshot: GB @ MIN, our ratings making GB the better side,
    the feed making MIN a -220 favourite."""
    wp = G.nfl_win_prob(home_rating, away_rating)
    # The context `pipeline._game_bets` passes, so the fixture's card
    # carries the same reasoning the screenshot's did.
    ctx = [f"Power rating: MIN {home_rating:+.1f} vs GB {away_rating:+.1f} "
           f"net pts/game (incl. home field)"]
    card = G.moneyline_to_dict(
        G.price_moneyline("MIN", "GB", wp, home_ml, away_ml, ctx, sport="nfl"))
    # `book` the way `pipeline._finish_bet` fills it: the Most Likely
    # board refuses a football game price it cannot attribute to one
    # (2026-09-09, tests/test_game_price_names_its_book.py).
    card.update(home="MIN", away="GB", matchup="GB @ MIN", date="2026-09-13",
                live=False, started=False, conditional=False,
                book="DraftKings", game_spread=-1.5)
    return card


# --- the sentence has a name --------------------------------------------------
def test_the_refusal_is_named_once_and_used_by_the_pricers():
    src = open(os.path.join(ROOT, "engine", "gamebets.py"), encoding="utf-8").read()
    assert "a rating error, not an edge" in G.RATING_ERROR_REASON
    assert "10%" in G.RATING_ERROR_REASON, "the bar is named in the sentence"
    assert "efficiently priced" in G.RATING_ERROR_REASON_EFFICIENT
    # Written down once each: the constant, and the two pricers that use it.
    assert src.count('f"Model disagrees with the market by more than "') == 0, \
        "the sentence is typed inline again and can drift from the constant"
    assert src.count("RATING_ERROR_REASON") >= 2


@_no_information
def test_the_edge_card_still_refuses_to_stake_in_its_own_words():
    card = _card()
    assert G.RATING_ERROR_REASON in card["reasons"], card["reasons"]
    assert card["grade"] == "Pass" and card["stake_units"] == 0.0


# --- the row -------------------------------------------------------------------
@_no_information
def test_a_market_ranked_row_does_not_carry_it():
    row = K.from_game_bet(_card(), "nfl")
    assert row is not None and row["prob_source"] == "market"
    assert G.RATING_ERROR_REASON not in row["reasons"], row["reasons"]
    assert not any("rating error" in r for r in row["reasons"]), row["reasons"]
    # The row still says the thing that matters, in the note that is about it.
    assert "own rating has this side at" in row["rank_note"]
    assert "does not bar the row" in row["rank_note"]
    # And the rest of the card's reasoning is untouched.
    assert any("Power rating" in r for r in row["reasons"]), row["reasons"]
    assert any(r.startswith("The likely side.") for r in row["reasons"])


@_no_information
def test_a_model_ranked_row_keeps_it():
    """Where the row is sorted on the model's own number, a refusal of
    that number is about the row. Only the moneyline ranks on the market
    (GAME_RANK_MARKET); a sport without that entry ranks on the model."""
    row = K.from_game_bet(_card(), "mlb")
    if row is None:
        return                      # MLB game markets are unmeasured here
    assert row["prob_source"] == "model"
    assert G.RATING_ERROR_REASON in row["reasons"]


@_no_information
def test_the_efficient_market_wording_comes_off_too():
    """Spreads and totals carry the other spelling. A spread does not
    rank on the market, so it keeps it — but the filter must know both,
    or the day a second market ranks on the market's number the sentence
    is back."""
    row = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
               has_market=True, home="MIN", away="GB", team="MIN",
               pick_is_home=True, pick_label="MIN ML", side="", line=0.0,
               matchup="GB @ MIN", win_prob=0.33, fair_prob=0.67, edge=-0.34,
               odds=-220, home_odds=-220, away_odds=200, ev_per_unit=-0.02,
               confidence=5.0, stake_units=0.0, grade="Pass", credible=False,
               headline="MIN ML", recommended=False, live=False,
               book="DraftKings",
               date="2026-09-13", game_spread=-1.5, engine_raw_prob=0.47,
               reasons=[G.RATING_ERROR_REASON_EFFICIENT, "Power rating: even"])
    got = K.from_game_bet(row, "nfl")
    assert got is not None and got["prob_source"] == "market"
    assert G.RATING_ERROR_REASON_EFFICIENT not in got["reasons"], got["reasons"]
    assert "Power rating: even" in got["reasons"], "a real reason was swept out"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
