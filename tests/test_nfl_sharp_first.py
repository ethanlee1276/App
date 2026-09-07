"""NFL game markets: a sharp book's disagreement is the pick; the model is the note.

Ethan, 2026-09-07: "I just want a wining nfl model for our best bets AND
edge models. I don't want you too stop till that is completed."

What was measured that day (engine/nflinfo.py, docs/NFL_MONEYLINE_
ARITHMETIC.md): the NFL model's disagreement with the closing line —
its own rating, and every input the database can add to it — carries
nothing. Baseball reached the same place on 2026-08 and adopted a
policy: a game card priced from the model alone is market information,
shown and never recommended; a card priced from a sharp book's
de-vigged number against a soft book's is a pick, because that edge is
one book disagreeing with a sharper one and involves no model opinion
at all. `engine/pipeline._game_bets` now runs the NFL on that policy.

Run directly: `python3 tests/test_nfl_sharp_first.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import Game, Weather                        # noqa: E402
from engine.pipeline import (_game_bets, _NFL_NO_ANCHOR,        # noqa: E402
                             NFL_MODEL_GAME_RECOMMENDATIONS)
from engine.rules import RuleConfig                            # noqa: E402


def _game(**kw):
    base = dict(home="KC", away="DEN", weather=Weather(dome=True),
                home_rating=4.0, away_rating=-2.0,
                home_off=3.0, home_def=-1.0, away_off=-2.0, away_def=1.0,
                total=44.5, spread=-3.5, home_ml=-180, away_ml=155,
                total_over_odds=-110, total_under_odds=-110,
                spread_home_odds=-110, spread_away_odds=-110)
    base.update(kw)
    return Game(**base)


def _by(cards, market):
    return [c for c in cards if c["market"] == market]


def test_without_a_sharp_quote_every_game_card_is_information():
    cards = _game_bets([_game()], RuleConfig())
    assert {c["market"] for c in cards} == {"moneyline", "total", "team_total", "spread"}
    for c in cards:
        assert c["recommended"] is False, c["market"]
        assert c["grade"] == "Pass" and c["stake_units"] == 0.0, c["market"]
        assert _NFL_NO_ANCHOR in c["warnings"], c["market"]
    # The model's own number is still on the card — the Most Likely
    # board ranks on it, and a reader is owed it.
    ml = _by(cards, "moneyline")[0]
    assert 0.0 < ml["win_prob"] < 1.0 and ml["has_market"]


def test_a_sharp_moneyline_disagreement_is_priced_and_can_be_a_pick():
    """Pinnacle at −110/−110 says the game is a coin flip; a soft book
    still pays plus money on the home side. Every card in the sweep is
    the sharp card — and NONE recommends, and that is arithmetic worth
    knowing: a game card's context is fixed at 35 points, so B+ (70)
    needs 35 of the 40 edge points, about 3.3 percentage points on a
    moneyline; at even money that is 7% of EV, exactly where the pricer
    calls the gap suspect. Near a coin flip the sharp path shows and
    never stakes.

    On a favourite the two bars come apart. Pinnacle −150/+130 (58% fair
    on the home side); a soft book at −120 implies 54.5% — 3.5 points of
    edge at +6.3% EV — and that IS a recommendation, B+, the only grade a
    game card can reach. The window is narrow (−122 is 3.0 points and
    Pass; −118 is +7.1% and suspect), which is why sharp-anchored game
    picks are rare, and why they are the only NFL game picks left."""
    for soft in (104, 106, 108, 110, 112):        # +2% … +6% EV at even money
        g = _game(home_ml=soft, away_ml=-125, sharp_home_ml=-110, sharp_away_ml=-110)
        ml = _by(_game_bets([g], RuleConfig()), "moneyline")[0]
        assert ml["reasons"][0].startswith("Sharp anchor"), ml["reasons"][0]
        assert _NFL_NO_ANCHOR not in ml.get("warnings", [])
        assert ml["team"] == "KC" and ml["odds"] == soft
        assert 0.02 <= ml["ev_per_unit"] <= 0.07
        assert ml["grade"] == "Pass" and ml["recommended"] is False, (soft, ml["grade"])
    picks = {}
    for soft in (-125, -122, -120, -118):
        g = _game(home_ml=soft, away_ml=115, sharp_home_ml=-150, sharp_away_ml=130)
        ml = _by(_game_bets([g], RuleConfig()), "moneyline")[0]
        picks[soft] = (ml["grade"], ml["recommended"], round(ml["ev_per_unit"], 3))
    assert picks[-120] == ("B+", True, 0.063), picks
    assert picks[-125][1] is False and picks[-122][1] is False, picks   # under the edge bar
    assert picks[-118][1] is False and picks[-118][2] > 0.07, picks       # over the suspect cap


def test_a_sharp_gap_beyond_the_suspect_cap_is_shown_and_refused():
    """+125 against a coin-flip fair is +12.5% EV — inside the 15% ceiling
    the sharp pricer prices at all, past the 7% it will stake. The card
    says so and takes nothing. (Past 15% the pricer returns None and the
    model card is what shows — a gap that big is a data fault, not a bet.)"""
    g = _game(home_ml=125, away_ml=-145, sharp_home_ml=-110, sharp_away_ml=-110)
    ml = _by(_game_bets([g], RuleConfig()), "moneyline")[0]
    # The moneyline path builds a MoneylineRec, whose suspect marker is
    # the reason itself (`_sharpify`'s `suspect_gap` flag is the dict-
    # shaped total/spread cards').
    assert ml["ev_per_unit"] > 0.07, ml["ev_per_unit"]
    assert ml["reasons"][0].startswith("Gap too large to trust"), ml["reasons"][0]
    assert ml["grade"] == "Pass" and ml["recommended"] is False and ml["stake_units"] == 0.0
    assert _NFL_NO_ANCHOR not in ml.get("warnings", []), "it was priced by the sharp path"
    # And beyond the ceiling, the model card, informational.
    g2 = _game(home_ml=150, away_ml=-170, sharp_home_ml=-110, sharp_away_ml=-110)
    ml2 = _by(_game_bets([g2], RuleConfig()), "moneyline")[0]
    assert _NFL_NO_ANCHOR in ml2["warnings"]
    assert not ml2["reasons"][0].startswith(("Sharp anchor", "Gap too large")), ml2["reasons"][0]
    assert ml2["recommended"] is False and ml2["stake_units"] == 0.0


def test_totals_and_spreads_anchor_only_at_the_same_line():
    """Fair probabilities at 44.5 say nothing about a bet at 45. A sharp
    quote at another line leaves the model card, informational."""
    # Same line: the sharp card. Soft +108 on the away side against a
    # coin-flip fair is +4% EV — inside the band the pricer stakes from.
    g = _game(total_over_odds=-120, total_under_odds=100,
              sharp_total=44.5, sharp_total_over_odds=-105, sharp_total_under_odds=-115,
              spread_home_odds=-125, spread_away_odds=108,
              sharp_spread=-3.5, sharp_spread_home_odds=-110, sharp_spread_away_odds=-110)
    cards = _game_bets([g], RuleConfig())
    tot, sp = _by(cards, "total")[0], _by(cards, "spread")[0]
    assert tot["reasons"][0].startswith("Sharp anchor") and tot["side"] == "Under"
    assert sp["reasons"][0].startswith("Sharp anchor") and sp["team"] == "DEN"
    # Another line: the model card, and it is information.
    g2 = _game(total_over_odds=-120, total_under_odds=100,
               sharp_total=45.0, sharp_total_over_odds=-105, sharp_total_under_odds=-115,
               spread_home_odds=-125, spread_away_odds=108,
               sharp_spread=-3.0, sharp_spread_home_odds=-110, sharp_spread_away_odds=-110)
    cards2 = _game_bets([g2], RuleConfig())
    for m in ("total", "spread"):
        c = _by(cards2, m)[0]
        assert not c["reasons"][0].startswith("Sharp anchor"), m
        assert c["recommended"] is False and _NFL_NO_ANCHOR in c["warnings"], m


def test_team_totals_have_no_sharp_reference_and_stay_informational():
    g = _game(sharp_total=44.5, sharp_total_over_odds=-105, sharp_total_under_odds=-115,
              total_over_odds=-120, total_under_odds=100)
    for c in _by(_game_bets([g], RuleConfig()), "team_total"):
        assert c["recommended"] is False and _NFL_NO_ANCHOR in c["warnings"]


def test_an_informational_moneyline_still_reaches_the_most_likely_board():
    """The Most Likely board is a different cut of the same evaluation:
    it ranks on the model's probability, not on whether the edge board
    would stake it. Demoting the card must not starve the board."""
    from engine import likely
    ml = _by(_game_bets([_game()], RuleConfig()), "moneyline")[0]
    assert ml["recommended"] is False
    row = likely.from_game_bet(ml, sport="nfl")
    assert row is not None, "the Most Likely board lost its NFL moneylines"
    assert row["market"] == "moneyline"


def test_the_policy_is_a_constant_and_every_model_path_goes_through_it():
    import inspect
    from engine import pipeline
    assert NFL_MODEL_GAME_RECOMMENDATIONS is False
    src = inspect.getsource(pipeline._game_bets)
    # Four model paths — moneyline, total, team totals, spread — each demoted.
    assert src.count("_info_only(") >= 4, src.count("_info_only(")
    for name in ("price_moneyline_sharp(", "price_total_sharp(", "price_spread_sharp("):
        assert name in src, name
    # And the reason on the card names both halves of the policy.
    assert "sharp-anchor" in _NFL_NO_ANCHOR and "NFL close" in _NFL_NO_ANCHOR


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
