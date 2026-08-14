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


# --- the bullpen, re-aimed at the innings that are left ---------------------
def test_the_reproduced_pen_multiplier_matches_the_matchup_code():
    """`bullpen.pen_multiplier` exists to be SUBTRACTED from a projection,
    so it has to be the same number `matchup._hitter_matchup` added. This
    reads the two side by side: if the matchup code changes its pen
    handling and the mirror does not, the live path starts dividing out a
    factor nobody put in."""
    import inspect
    from engine.mlb import matchup
    from engine.mlb.bullpen import pen_multiplier
    src = inspect.getsource(matchup._hitter_matchup)
    # The rank nudges, exactly as the matchup applies them.
    assert "mult *= 1.03" in src and "pen >= 24" in src
    assert "mult *= 0.98" in src and "pen <= 6" in src
    assert abs(pen_multiplier(rank=27) - 1.03) < 1e-9
    assert abs(pen_multiplier(rank=3) - 0.98) < 1e-9
    assert pen_multiplier(rank=15) == 1.0
    # And fatigue rides on top of it, same as there.
    from engine.mlb.bullpen import fatigue_factor
    assert abs(pen_multiplier(rank=27, fatigue=9.0)
               - 1.03 * fatigue_factor(9.0)) < 1e-9


def test_an_unmeasured_pen_changes_nothing():
    """No pen data contributed nothing to the projection, so there is
    nothing to take back out. Moving a number on a missing input is how a
    live display invents a signal."""
    from engine.mlb.bullpen import pen_multiplier
    assert pen_multiplier() == 1.0
    assert lp.pen_rebase(1.0, facing_pen=True) == 1.0
    assert lp.pen_rebase(1.0, facing_pen=False) == 1.0


def test_an_unknown_pitcher_leaves_the_projection_alone():
    """CAUGHT BY THE WIRING TEST. `facing_pen` is three-state: None means
    the game named no probable starter, so we cannot tell who is on the
    mound. Collapsing that into "facing the starter" divided the pen bonus
    out of every game whose pitcher feed came up empty — a real adjustment
    made on the strength of a missing field."""
    assert lp.pen_rebase(1.06, facing_pen=None) == 1.0
    assert lp.pen_rebase(0.98, facing_pen=None) == 1.0
    assert lp.pen_rebase(1.06, facing_pen=False) != 1.0


def test_the_pen_bonus_is_divided_out_while_the_starter_is_in():
    """THE UNAMBIGUOUS HALF. Whatever the pre-game factor was meant to
    describe, it cannot describe a plate appearance against the starter.
    A tired-pen bonus left in place there flatters every hitter for
    innings the pen is not pitching."""
    assert lp.pen_rebase(1.03, facing_pen=False) < 1.0
    assert abs(lp.pen_rebase(1.03, facing_pen=False) - 1 / 1.03) < 1e-9
    # And a GOOD pen's penalty comes back off the same way.
    assert lp.pen_rebase(0.98, facing_pen=False) > 1.0


def test_the_pen_bonus_lands_harder_once_the_starter_is_gone():
    """Un-blended: a whole-game 3% bump earned entirely in the third of
    the game the pen pitches is worth more than 3% per plate appearance
    against the pen itself."""
    A = 1.03
    vs_pen = lp.pen_rebase(A, facing_pen=True)
    assert vs_pen > 1.0
    assert A * vs_pen > A, "the per-PA pen factor is not stronger than the blend"


def test_the_two_sides_of_the_blend_bracket_the_applied_factor():
    """Sanity on the algebra itself: dividing out has to sit below 1 and
    the reliever factor above it, with the pre-game factor in between."""
    for A in (1.03, 1.06, 0.98):
        st = A * lp.pen_rebase(A, facing_pen=False)
        pen = A * lp.pen_rebase(A, facing_pen=True)
        assert abs(st - 1.0) < 1e-9
        assert (pen > A) == (A > 1.0)


def test_the_reliever_factor_cannot_exceed_the_engines_own_matchup_bound():
    """`matchup._hitter_matchup` clamps its whole multiplier to
    [0.88, 1.15]. Un-blending divides by roughly a third, so an unclamped
    version hands a hitter a 1.25 per-plate-appearance factor — further
    than the engine allows any matchup to move anyone.

    THIS TEST EARNED ITS KEEP IMMEDIATELY: the cap first shipped as 1.12,
    which is `matchup`'s STRIKEOUT bound, not its hitter one. Reading the
    clamp out of the function instead of trusting the comment beside the
    constant is what caught it."""
    worst = 1.06 * 1.03                       # tired AND badly ranked
    per_pa = worst * lp.pen_rebase(worst, facing_pen=True)
    lo, hi = lp.PEN_PER_PA_CAP
    assert per_pa <= hi + 1e-9
    assert per_pa > 1.12, "the cap is binding lower than the hitter bound"
    from engine.mlb import matchup
    import inspect
    assert f"clamp(mult, {lo}, {hi})" in inspect.getsource(matchup._hitter_matchup), \
        "the matchup bound moved — PEN_PER_PA_CAP has to move with it"


def test_scaling_keeps_the_table_a_distribution():
    """`out` absorbs the change; the six outcomes still sum to one. A
    plain multiply-everything would leave a table that is not a
    probability distribution and quietly break every downstream count."""
    rates = _rates()
    for f in (0.94, 1.0, 1.12):
        s = lp.scale_rates(rates, f)
        total = s.out + s.bb + s.single + s.double + s.triple + s.hr
        assert abs(total - 1.0) < 1e-9, (f, total)


def test_scaling_moves_the_reaching_outcomes_in_the_right_direction():
    rates = _rates()
    up, down = lp.scale_rates(rates, 1.10), lp.scale_rates(rates, 0.90)
    assert up.hr > rates.hr > down.hr
    assert up.out < rates.out < down.out


def test_scaling_works_on_the_single_market_table_too():
    """`hits` and `home_runs` use the duck-typed binomial table, which is
    not a `BatterRates` and would throw in `_scale_reaching`."""
    b = lp.rates_for("hits", {"hits": 1.05}, 3)
    s = lp.scale_rates(b, 1.10)
    assert abs(s.rate - b.rate * 1.10) < 1e-9
    assert abs(s.out + s.single - 1.0) < 1e-9


def test_a_scaled_rate_cannot_reach_certainty():
    """Scaling a high rate up must not produce a table where the hitter
    reaches base every time — `p_at_least` would then report 1.0 on a bet
    that is not won."""
    b = lp.rates_for("hits", {"hits": 4.2}, 3)      # a mean equal to his PA
    s = lp.scale_rates(b, 1.12)
    assert s.rate < 1.0


# --- the leash, for the man still on the mound ------------------------------
def test_a_gassed_pen_lengthens_the_start():
    """The measured behaviour `leash_factor` was built for, now reaching
    the live number: no available relievers means more batters faced, and
    more batters faced is more chances at a strikeout line."""
    normal = lp.bf_left(18, banked_bf=10, own_pen_score=None)
    gassed = lp.bf_left(18, banked_bf=10, own_pen_score=12.0)
    assert gassed > normal


def test_a_rested_pen_does_not_shorten_the_start():
    """`leash_factor` floors at 1.0 by design — the tired-pen effect is
    the reliably observable one. The live path must inherit that
    one-directionality rather than inventing the mirror."""
    assert lp.bf_left(18, 10, own_pen_score=0.0) == lp.bf_left(18, 10)


def test_the_leash_never_conjures_batters_the_game_does_not_have():
    """A short pen stretches the manager's patience, not the innings. In
    the ninth there are only so many hitters left however gassed the pen
    is."""
    assert lp.bf_left(2, banked_bf=5, own_pen_score=20.0) \
        == lp.bf_left(2, banked_bf=5)


def test_the_leash_uses_the_outs_reading_not_the_strikeout_one():
    """`leash_factor` has two strengths. This is a question about LENGTH —
    how many more hitters he faces — which is the outs reading. The
    halved strikeout reading describes the per-batter rate, and applying
    it here would understate the extra work."""
    from engine.mlb.bullpen import leash_factor
    score = 12.0
    grew = lp.bf_left(30, 0, own_pen_score=score) / lp.bf_left(30, 0)
    assert abs(grew - leash_factor(score, market_is_outs=True)) < 1e-9


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
