"""A book price that cannot belong to the number beside it is a bad quote,
not an edge — and must not be shopped, staked or ranked.

Ethan, 2026-09-02, from a phone: "How is a under 4.5 bases -200, we need to
figure out how and why we showed that and fix it."

The card: Zack Gelof, UNDER 4.5 Total Bases at -200 on theScore Bet, MODEL
73% against a book-implied 63%, projection 1.7, spark reading 0/10 cleared
4.5. `fix(likely)` established the model half — 96% shrunk to 73% by
`temper_edge` — and stopped the row topping the Most Likely board. It left
the price open: "Either the price is joined to the wrong rung of an
alternate-line ladder in our own ingest, or the book is showing a stale
number."

THE INGEST IS NOT AT FAULT, and the first test here is what says so: fed a
whole alternate ladder in one market, interleaved exactly as The Odds API
returns it, `parse_event_lines` keeps every rung's Over beside its own
Under. It cannot produce the card. Nor can anything below it —
`best_under_line` builds a `BestLine` from a single `SportsbookLine`, and
`evaluate_mlb_prop` passes `best.line` and `best.odds` to the same
`Recommendation` — so a 4.5 carrying a 2.5 price came off the book that
way. (We also never request an alternate-line market: MLB asks for five
plain keys and there is no `_alternate` key anywhere in the adapter, so
there is no ladder in the feed to mis-join in the first place.)

What the ladder DOES show is where -200 belongs: de-vigged it is 63.0%,
the card's "BOOK IMPLIED" to the digit, and that is the 2.5 rung. The 4.5
rung de-vigs to 90.4%. The price is real, and real for another number.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.betting import (
    IMPLAUSIBLE_QUOTE_GAP, MAX_CREDIBLE_EDGE, MISPOSTED_QUOTE_REASON,
    NO_CREDIBLE_EDGE_REASON, REFUSAL_REASONS, pick_side,
    quote_prices_its_line,
)
from engine.models import SportsbookLine
from engine.odds import devig_two_way
from engine.sources.oddsapi import MLB_ODDS_TO_MARKET, parse_event_lines


# The real The Odds API v4 shape: one book, one market, every rung of a
# total-bases ladder for one batter, Over and Under interleaved per point.
# Prices are a coherent ladder for a 1.7 projection.
LADDER = [(0.5, -250, 190), (1.5, 105, -135), (2.5, 155, -200),
          (3.5, 380, -550), (4.5, 900, -1500)]

EVENT = {
    "id": "evt_gelof",
    "home_team": "Athletics",
    "away_team": "Seattle Mariners",
    "bookmakers": [{
        "key": "thescorebet", "title": "theScore Bet",
        "markets": [{"key": "batter_total_bases", "outcomes": [
            o for pt, over, under in LADDER for o in (
                {"name": "Over", "description": "Zack Gelof",
                 "price": over, "point": pt},
                {"name": "Under", "description": "Zack Gelof",
                 "price": under, "point": pt},
            )
        ]}],
    }],
}

#: P(total bases > line) for the card's player: a 1.7 projection whose log
#: reads 0/10 cleared 4.5. The under at 4.5 is ~96%, which is what the
#: spark on the card said too.
GELOF = {0.5: 0.58, 1.5: 0.33, 2.5: 0.16, 3.5: 0.07, 4.5: 0.04}


def p_over_at(line):
    return GELOF[line]


def test_the_ingest_keeps_every_rung_with_its_own_price():
    """The exonerating test. A whole ladder in one market, and no rung
    borrows a neighbour's number."""
    lines = parse_event_lines(EVENT, MLB_ODDS_TO_MARKET)
    got = {ln.line: (ln.over_odds, ln.under_odds)
           for ln in lines[("zack gelof", "total_bases")]}
    assert got == {pt: (over, under) for pt, over, under in LADDER}


def test_minus_200_is_the_2_point_5_rung_not_the_4_point_5_one():
    """Where the card's price actually belongs. -200 de-vigs to the 63%
    the card printed as BOOK IMPLIED; the 4.5 rung is nowhere near it."""
    _, fair_under_2_5 = devig_two_way(155, -200)
    _, fair_under_4_5 = devig_two_way(900, -1500)
    assert round(fair_under_2_5, 3) == 0.630          # the card's 63%
    assert round(fair_under_4_5, 3) == 0.904
    # And ours for that line is nothing like it.
    assert 1.0 - p_over_at(4.5) > 0.95


def test_the_card_is_refused():
    """The row as published: theScore Bet alone, 4.5 carrying that price."""
    lines = [SportsbookLine(book="theScore Bet", line=4.5,
                            over_odds=155, under_odds=-200)]
    side, best, _hit_raw, _fair, _edge = pick_side(lines, p_over_at)
    assert (side, best.line, best.odds) == ("UNDER", 4.5, -200)
    assert round(best.fair_prob, 3) == 0.630
    assert not quote_prices_its_line(side, best, p_over_at)


def test_a_misposted_number_does_not_win_the_shop():
    """The reason this belongs in the shop and not only in a gate.

    `best_under_line` prefers the HIGHEST line and calls it more cushion,
    so a book posting 4.5 while carrying a 2.5 price is SELECTED over a
    real 2.5 — the same way a dead-zone -97 used to win on "highest odds".
    A mis-post does not sit quietly at the bottom of a board.
    """
    real = SportsbookLine(book="DraftKings", line=2.5,
                          over_odds=150, under_odds=-190)
    misposted = SportsbookLine(book="theScore Bet", line=4.5,
                               over_odds=155, under_odds=-200)
    side, best, *_ = pick_side([real, misposted], p_over_at)
    assert (best.book, best.line) == ("DraftKings", 2.5)
    assert quote_prices_its_line(side, best, p_over_at)


def test_an_honest_heavy_under_still_prices_its_line():
    """The bar must not refuse a book that quotes 4.5 properly. -1500 is
    heavy, and heavy is what a 96% event costs."""
    lines = [SportsbookLine(book="FanDuel", line=4.5,
                            over_odds=900, under_odds=-1500)]
    side, best, *_ = pick_side(lines, p_over_at)
    assert (side, best.odds) == ("UNDER", -1500)
    assert quote_prices_its_line(side, best, p_over_at)


def test_the_bar_sits_clear_of_the_credibility_bar():
    """These answer different questions and must not collapse into one.

    MAX_CREDIBLE_EDGE asks "do we disagree too much to bet this?" and
    answers Pass — the price is real and our number may be the wrong one.
    This asks "is this a price for this line at all?". Everything between
    the two is already unbettable, so widening cannot cost a bet; keeping
    them apart is what stops an honest-but-badly-modelled market being
    called corrupt.
    """
    assert IMPLAUSIBLE_QUOTE_GAP > MAX_CREDIBLE_EDGE

    # An 18-point disagreement: past credibility, nowhere near mis-posted.
    lines = [SportsbookLine(book="BetMGM", line=2.5,
                            over_odds=150, under_odds=-330)]
    side, best, hit_raw, fair, _edge = pick_side(lines, p_over_at)
    model = hit_raw
    assert MAX_CREDIBLE_EDGE < abs(model - fair) < IMPLAUSIBLE_QUOTE_GAP
    assert quote_prices_its_line(side, best, p_over_at)


def test_the_refusal_names_the_price_not_the_model():
    """A mis-posted quote fails `credible` too, so without its own branch
    the card would blame our model for a gap the arithmetic pins on the
    book — and `NO_CREDIBLE_EDGE_REASON` would tell a reader the line was
    unavailable while it sat on the screen."""
    assert MISPOSTED_QUOTE_REASON in REFUSAL_REASONS
    assert "cannot be a price for it" in MISPOSTED_QUOTE_REASON
    assert "unavailable" not in MISPOSTED_QUOTE_REASON


# --- a proxy is not a posted price ------------------------------------------
def _jacobs_at(book, line):
    """The sample slate's first prop — Josh Jacobs rushing yards, projected
    105.9 ± 41.4 — re-lined at ``line`` on one ``book`` at -110/-110.
    Evaluated end to end, so the reason on the card is the one the
    engine actually inserts."""
    import copy
    from engine.data_loader import load_slate
    from engine.projection import build_projection
    from engine.betting import evaluate_prop
    sl = load_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    prop = copy.deepcopy(sl.props[0])
    assert prop.player == "Josh Jacobs" and prop.market == "rush_yds"
    prop.lines = [SportsbookLine(book=book, line=line,
                                 over_odds=-110, under_odds=-110)]
    game, opp = sl.game_for(prop), sl.team(prop.opponent)
    proj = build_projection(prop, game, opp)
    return evaluate_prop(prop, proj, game=game), proj


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_a_stale_proxy_is_not_called_a_misposted_quote():
    """Ethan's Blackburn card, 2026-09-05, after kickoff: the player
    markets are not re-bought once a game starts, so every row sat on a
    proxy — and one receiver trending +2 catches a game was refused with
    "The price posted beside this number cannot be a price for it".
    Nobody posted a price. The placeholder was stale, which is
    `has_market`'s sentence to say, not this one's."""
    from engine.betting import prob_over
    rec, proj = _jacobs_at("proxy", 40.5)   # a 105.9 projection over 40.5
    assert rec.has_market is False
    # The RAW model number, not `hit_prob` — that one has been shrunk
    # toward the -110 fair by the tier haircut and cannot show the gap
    # the quote check saw.
    assert prob_over(40.5, proj.mean, proj.std) > 0.5 + IMPLAUSIBLE_QUOTE_GAP, \
        "the setup must disagree with -110 by more than the quote gap"
    assert MISPOSTED_QUOTE_REASON not in rec.reasons, rec.reasons
    assert rec.reasons[0] == NO_CREDIBLE_EDGE_REASON, rec.reasons


def test_the_same_number_on_a_real_book_is_still_a_bad_quote():
    """The negative control. A book that really posts -110 at 40.5 on a
    106-yard projection is the Gelof card again, and keeps its sentence."""
    rec, _proj = _jacobs_at("FanDuel", 40.5)
    assert rec.has_market is True
    assert rec.reasons[0] == MISPOSTED_QUOTE_REASON, rec.reasons


def test_both_engines_skip_the_quote_check_on_a_proxy():
    """The MLB engine keeps its own copy of the gate, so the fix has to
    be in both or the two boards would name the same row differently."""
    import inspect
    from engine import betting
    from engine.mlb import betting as mlb
    for mod in (betting, mlb):
        src = inspect.getsource(mod)
        i = src.index("prices_line = (allow_synthetic_line")
        clause = src[i:i + 200]
        assert '(best.book or "").lower() == "proxy"' in clause, mod.__name__


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
