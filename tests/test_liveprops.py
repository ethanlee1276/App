"""What a live player prop is worth right now.

Ethan, 2026-08-14: "Are we able too track the win probability of bets we
have made live too? Like player props and shit based of the current live
lines they would display durring the game."

The live LINES are the wrong source and the cost is only half the reason.
Props sit on the Odds API's event endpoint, which bills per game — one
prop market across a fifteen-game slate is fifteen credits for a single
refresh against a plan of five hundred a month. And books PULL prop
markets at first pitch, which is the finding behind `livepicks`'
three-tier lookup: every unmapped name on Ethan's Live Now screenshot was
a pitcher and every mapped one a hitter. We would pay per game, over and
over, to be told the market is gone.

So the number is computed instead, from a race that is already fully
observable for free: what the player has BANKED (the live boxscore)
against how many cracks at it he has LEFT (the linescore). The rates come
from tonight's own projections — the same ones that priced the bet, so
the live number cannot quietly disagree with the pre-game one.

The tests below are mostly about the second half of that race, because it
is where the wrong answer is invisible. A hitter needing one more base
reads the same at 55% and 8%; only the count of plate appearances he has
left tells them apart, and getting THAT wrong produces a confident number
nobody can see is broken.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import liveprops as lp                       # noqa: E402

MEANS = {"hits": 1.05, "total_bases": 1.75, "home_runs": 0.16}


# --- outs left, which is where the ninth stops being symmetric ---------------
def test_the_away_team_batting_counts_this_half_and_every_later_one():
    """Top of the 6th, one out: two outs left here, plus the 7th, 8th and
    9th."""
    assert lp.outs_left(6, "Top", 1, is_home=False) == 11.0


def test_the_away_teams_half_is_over_once_the_bottom_starts():
    """Bottom of the 6th: they are done for this inning, three innings of
    theirs remain."""
    assert lp.outs_left(6, "Bottom", 1, is_home=False) == 9.0


def test_the_home_team_gets_this_inning_too_while_the_top_is_played():
    assert lp.outs_left(6, "Top", 1, is_home=True) == 12.0


def test_a_home_team_leading_after_the_top_of_the_ninth_never_bats():
    """THE ONE THAT MATTERS, and it bites in exactly the spot where the
    bet is closest to resolving. Its hitters' props are finished while
    the game is still officially live, and crediting them with three more
    outs of chances overstates every one of them."""
    assert lp.outs_left(9, "Top", 2, is_home=True,
                        home_score=5, away_score=3) == 0.0


def test_a_home_team_trailing_in_the_ninth_still_bats():
    assert lp.outs_left(9, "Top", 2, is_home=True,
                        home_score=3, away_score=5) == 3.0


def test_the_away_team_is_done_batting_in_the_bottom_of_the_ninth():
    assert lp.outs_left(9, "Bottom", 1, is_home=False) == 0.0


def test_extra_innings_only_count_the_half_being_played():
    """Past the ninth the game ends the moment the home team leads after a
    completed inning. Crediting a hitter with another turn through the
    order is inventing baseball that may never be played."""
    assert lp.outs_left(11, "Top", 1, is_home=False) == 2.0
    assert lp.outs_left(11, "Top", 1, is_home=True) == 0.0


def test_a_game_that_has_not_started_has_no_outs_left_to_report():
    assert lp.outs_left(0, "", 0, is_home=True) == 0.0


# --- remaining plate appearances --------------------------------------------
def test_the_hitter_at_the_plate_is_counted_as_having_this_one():
    """dist 0 — he is up now. Whatever else happens he gets this crack."""
    assert lp.remaining_pa(4, 4, 9.0) >= 1.0


def test_a_hitter_further_down_the_order_gets_fewer():
    """Same outs left, later in the queue: strictly fewer chances."""
    near = lp.remaining_pa(3, 2, 6.0)
    far = lp.remaining_pa(9, 2, 6.0)
    assert near > far


def test_the_order_wraps_rather_than_running_off_the_end():
    """Spot 2 with spot 8 at the plate is three hitters away, not minus
    six. Getting this backwards hands the top of the order the FEWEST
    remaining chances, which is exactly wrong."""
    assert lp.remaining_pa(2, 8, 12.0) > lp.remaining_pa(7, 8, 12.0)


def test_nobody_bats_again_when_there_are_no_outs_left():
    assert lp.remaining_pa(3, 1, 0.0) == 0.0


def test_a_hitter_too_far_down_to_come_up_again_gets_nothing():
    """One out left is about 1.4 plate appearances. The seventh hitter
    with the leadoff man at the plate is six away — he is not batting."""
    assert lp.remaining_pa(7, 1, 1.0) == 0.0


def test_a_full_game_gives_a_hitter_roughly_four_trips():
    """The sanity check on PA_PER_OUT itself: 27 outs, leadoff, should
    land near the four-to-five plate appearances a real leadoff man gets.
    A constant that is wrong by a factor puts every live number out.

    It caught the estimator being wrong on the first build — the exact
    turn count handed the leadoff man 5.11, which is the whole top of the
    order rounded up. See `remaining_pa`."""
    pa = lp.remaining_pa(1, 1, 27.0)
    assert 4.0 <= pa <= 5.0, pa


def test_the_whole_ladder_agrees_with_the_engines_own_pa_table():
    """THE STRONG CHECK, because it is independent. `gamesim.PA_BY_SPOT`
    is a flat lookup written for the pre-game sim; this walks a batting
    order forward from outs remaining and a league plate-appearance rate.
    Two unrelated derivations, and over a full game they agree to within
    0.07 of a plate appearance at every slot.

    That is what makes the live number trustworthy at the top of the
    game. If a later edit to PA_PER_OUT or the estimator drifts them
    apart, the live probabilities have silently stopped matching the
    model that priced the bets — which is precisely the failure a live
    display cannot show you."""
    from engine.mlb.gamesim import PA_BY_SPOT
    for spot in range(1, 10):
        mine = lp.remaining_pa(spot, 1, 27.0)
        assert abs(mine - PA_BY_SPOT[spot]) <= 0.10, (spot, mine, PA_BY_SPOT[spot])


def test_the_ladder_falls_monotonically_down_the_order():
    """Batting ninth is never more chances than batting first."""
    ladder = [lp.remaining_pa(s, 1, 27.0) for s in range(1, 10)]
    assert ladder == sorted(ladder, reverse=True), ladder


# --- the outcome tables ------------------------------------------------------
def test_every_market_table_is_a_probability_distribution():
    for market in lp.HITTER_MARKETS:
        rates = lp.rates_for(market, MEANS, spot=3)
        total = sum(p for _, p in lp.per_pa_outcomes(rates, market))
        assert abs(total - 1.0) < 1e-9, (market, total)


def test_a_walk_advances_nothing_but_still_burns_the_chance():
    """It sits in the zero bucket rather than being dropped: a walk is a
    plate appearance that produced no bases, which is different from a
    plate appearance that never happened."""
    rates = lp.rates_for("total_bases", MEANS, spot=3)
    zero = dict(lp.per_pa_outcomes(rates, "total_bases"))[0]
    assert zero >= rates.bb > 0


def test_total_bases_alone_gets_no_live_number():
    """NO GUESSED SHAPE. A total-bases mean of 1.6 could be four singles
    or one home run, and late in a game those are very different bets.
    Splitting it on a league extra-base share would be inventing the one
    quantity the market is actually about."""
    assert lp.rates_for("total_bases", {"total_bases": 1.75}, 3) is None


def test_hits_and_home_runs_need_only_their_own_mean():
    """They are one-per-plate-appearance events, so a single mean fixes
    the whole table exactly. Nothing is assumed."""
    assert lp.rates_for("hits", {"hits": 1.05}, 3) is not None
    assert lp.rates_for("home_runs", {"home_runs": 0.16}, 3) is not None


def test_a_market_we_do_not_model_gets_nothing():
    assert lp.rates_for("rbis", MEANS, 3) is None


# --- the probability itself --------------------------------------------------
def _rates(market="total_bases"):
    return lp.rates_for(market, MEANS, spot=3)


def test_a_banked_over_is_already_won():
    """2 total bases against a 1.5 line: no more baseball required."""
    assert lp.hitter_probability(_rates(), "total_bases", 1.5, "OVER",
                                 banked=2, pa_left=3) == 1.0


def test_a_banked_over_kills_the_under():
    assert lp.hitter_probability(_rates(), "total_bases", 1.5, "UNDER",
                                 banked=2, pa_left=3) == 0.0


def test_no_chances_left_means_the_over_cannot_come_in():
    assert lp.hitter_probability(_rates(), "total_bases", 1.5, "OVER",
                                 banked=1, pa_left=0) == 0.0


def test_an_under_with_no_chances_left_is_home():
    """The mirror, and the one a careless implementation gets wrong by
    reporting the over's probability whatever the ticket says."""
    assert lp.hitter_probability(_rates(), "total_bases", 1.5, "UNDER",
                                 banked=1, pa_left=0) == 1.0


def test_the_two_sides_always_sum_to_one():
    """Half-point lines cannot push, so there is no third outcome to
    absorb the difference."""
    for banked in (0, 1, 2):
        for pa in (0.0, 1.4, 3.0):
            o = lp.hitter_probability(_rates(), "total_bases", 1.5, "OVER", banked, pa)
            u = lp.hitter_probability(_rates(), "total_bases", 1.5, "UNDER", banked, pa)
            assert abs(o + u - 1.0) < 1e-9, (banked, pa)


def test_more_chances_left_is_never_worse_for_an_over():
    rates = _rates()
    ps = [lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, pa)
          for pa in (0.0, 1.0, 2.0, 3.0, 4.0)]
    assert ps == sorted(ps), ps


def test_banking_more_is_never_worse_for_an_over():
    rates = _rates()
    ps = [lp.hitter_probability(rates, "total_bases", 2.5, "OVER", b, 3.0)
          for b in (0, 1, 2, 3)]
    assert ps == sorted(ps), ps


def test_a_fractional_plate_appearance_lands_between_the_whole_ones():
    """2.4 chances means some nights two and some nights three. Rounding
    would make the number jump a whole plate appearance at a time as the
    game moved — a chart showing movement that came from our arithmetic
    rather than the field."""
    rates = _rates()
    p2 = lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, 2.0)
    p24 = lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, 2.4)
    p3 = lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, 3.0)
    assert p2 < p24 < p3


def test_the_distribution_is_exact_not_sampled():
    """A sampler would put noise on a number that redraws every sixty
    seconds, so the display would flicker while nothing happened in the
    game. Same inputs, same answer, every time."""
    rates = _rates()
    seen = {lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, 2.4)
            for _ in range(12)}
    assert len(seen) == 1


def test_the_multi_base_path_is_counted():
    """A home run clears an over-1.5 in ONE plate appearance. A model that
    only counted hits would price a slugger's last at-bat like a slap
    hitter's."""
    rates = _rates()
    p = lp.hitter_probability(rates, "total_bases", 1.5, "OVER", 0, 1.0)
    assert p >= rates.double + rates.triple + rates.hr - 1e-9


# --- pitchers ----------------------------------------------------------------
def test_a_pitcher_out_of_the_game_is_a_settled_bet():
    """The single most useful thing this can say about a strikeout prop,
    and it costs nothing: once he is pulled the number cannot move."""
    assert lp.pitcher_probability(0.25, 5.5, "OVER", banked=6, bf_left=0) == 1.0
    assert lp.pitcher_probability(0.25, 5.5, "OVER", banked=5, bf_left=0) == 0.0


def test_a_pitcher_still_in_gets_a_forecast_between_the_two():
    p = lp.pitcher_probability(0.25, 5.5, "OVER", banked=5, bf_left=8)
    assert 0.0 < p < 1.0


def test_the_leash_caps_a_cruising_starter():
    """Without it a starter in the third is credited with every batter
    left in the game — an outing nobody actually makes."""
    assert lp.bf_left(18, banked_bf=20, leash=25) == 5.0


def test_the_game_caps_a_starter_in_a_short_one():
    """And the other way round: a fresh pitcher in the ninth does not get
    his full leash, because there are not that many hitters left."""
    assert lp.bf_left(3, banked_bf=5, leash=25) < 5.0


def test_a_nonsense_rate_gets_no_number():
    for bad in (None, "x", 0.0, 1.0, -0.2):
        assert lp.pitcher_probability(bad, 5.5, "OVER", 5, 8) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
