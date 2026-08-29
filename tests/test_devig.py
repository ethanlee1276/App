"""The price a one-way market is really offering.

`engine/tdbook` used to say the anytime-touchdown market "cannot be
de-vigged without the other side, which does not exist here". It can:
sum every listed scorer's raw implied probability in one game and compare
it to how many distinct scorers the game line supports. The ratio is the
book's hold, measured off the very board being priced.

These tests assert the parts that are easy to get backwards:

  * the constants are the MEASURED ones, not the handbook's, and the
    difference is not cosmetic;
  * an unmeasurable board returns None rather than 1.0, because "no hold"
    and "no idea" are different claims;
  * correcting the hold moves EV DOWN, so nobody can wire it in believing
    it finds money;
  * the value picks and the watchlist price against the SAME hold — the
    two-lists-one-player bug this codebase has now hit twice.

Run directly: `python3 tests/test_devig.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.devig import (
    SCORERS_SLOPE, SCORERS_BASE, TD_OFFSET, TD_DIVISOR, MIN_PRICED,
    K_MIN, K_MAX, PROPORTIONAL, POWER, DEFAULT_METHOD, Devig, as_devig,
    expected_distinct_scorers, expected_tds_affine, hold_multiplier,
    power_exponent, fair_probability, american, game_prices, board_hold,
    board_devig,
)
from engine.longshots import build_pick, calibrated_prob, ONE_SIDED_HOLD
from engine.odds import american_to_prob
from engine.models import (
    Prop, Game, Team, DefenseProfile, Weather, GameLog, SportsbookLine, ANYTIME_TD,
)


def _handbook_scorers(total_tds):
    """The form the handbook gives: one repeat scorer in ten, flat."""
    return 0.90 * total_tds + 0.12


# --- the constants ---------------------------------------------------------
def test_distinct_scorers_uses_the_measured_slope_not_the_handbook_s():
    assert (SCORERS_SLOPE, SCORERS_BASE) == (0.666, 0.920)


def test_the_handbook_s_constants_would_over_count_high_scoring_games():
    """Repeat scorers grow with scoring, so a flat one-in-ten repeat rate
    breaks at the top. Over 1,216 games with both teams logged, a 9-15 TD
    game produced 7.03 distinct scorers; the handbook's form says 8.67.

    The direction is what matters: over-counting scorers makes the sum
    look SMALLER relative to them, which under-states the hold, which
    makes the book look fairer than it is and quietly inflates every
    edge on the board."""
    realised_high = 7.03
    ours = expected_distinct_scorers(4.75, 4.75)          # 9.5 offensive TDs
    theirs = _handbook_scorers(9.5)
    assert abs(ours - realised_high) < 0.3
    assert theirs - realised_high > 1.5                   # off by 23%
    assert ours < theirs                                  # so we hold MORE vig


def test_the_measured_form_is_closer_at_every_level_of_scoring():
    """Not just in the tails. The two forms cross at 3.4 total offensive
    touchdowns — below almost every real NFL game — so the measured one
    sits under the handbook's across the whole live range, and the
    correction is a level shift rather than a tail patch.

    Fitted bands, 1,216 games with both teams logged (the table in
    engine/devig): ours is nearer the realised count at each one."""
    bands = [(5.5, 4.36), (8.0, 5.74), (9.5, 7.03)]
    for total, actual in bands:
        ours = expected_distinct_scorers(total / 2, total / 2)
        theirs = _handbook_scorers(total)
        # A margin, not a bare comparison: "nearer by a rounding error"
        # would not be a reason to prefer one form over the other.
        assert abs(ours - actual) + 0.10 < abs(theirs - actual), total
        assert ours < theirs, total          # so we always hold more vig
    # And the crossover really is below the live range: a game has to be
    # a 3-TD affair before the handbook's form is the conservative one.
    assert expected_distinct_scorers(1.5, 1.5) > _handbook_scorers(3.0)
    assert expected_distinct_scorers(2.0, 2.0) < _handbook_scorers(4.0)


def test_distinct_scorers_rises_with_scoring_and_never_goes_negative():
    assert expected_distinct_scorers(3.0, 3.0) > expected_distinct_scorers(1.0, 1.0)
    assert expected_distinct_scorers(-5.0, -5.0) == SCORERS_BASE
    # The base is not zero on purpose: defensive and special-teams scores
    # take equity out of the offensive market a book is pricing.
    assert SCORERS_BASE > 0


def test_the_affine_team_total_form_is_offered_but_is_not_what_the_board_uses():
    """The handbook's (total - 4.5) / 7.2 fitted to (total - 5.36) / 7.18
    here, confirming its divisor and correcting its offset. It is still
    NOT the default: measured against the same 2,848 team-games the
    proportional form the board already uses fits the tails better (3.61
    against a realised 3.39, where the affine one gives 4.10).

    So this pins the decision, not just the constant: `expected_team_tds`
    must stay proportional — zero points means zero touchdowns and
    doubling the total doubles them — which the affine form is not."""
    from engine.touchdowns import expected_team_tds
    assert expected_team_tds(0.0) == 0.0
    assert abs(expected_team_tds(40.0) - 2 * expected_team_tds(20.0)) < 1e-9
    assert expected_tds_affine(TD_OFFSET) == 0.0          # affine: a floor, not an origin
    assert expected_tds_affine(0.0) == 0.0                # and clamped, never negative
    assert abs(expected_tds_affine(TD_OFFSET + TD_DIVISOR) - 1.0) < 1e-9
    # The disagreement at a big team total is the reason for the choice.
    assert expected_tds_affine(31.0) > expected_team_tds(31.0)


# --- the guards ------------------------------------------------------------
def test_a_thin_board_is_unmeasurable_rather_than_hold_free():
    """Three prices listed says nothing about the book's margin. Returning
    None sends the caller back to its fallback; returning 1.0 would tell
    it the book takes no vig, which is a much more expensive lie."""
    thin = [0.30] * (MIN_PRICED - 1)
    assert hold_multiplier(thin, 1.0) is None
    assert hold_multiplier(thin + [0.30], 1.0) is not None


def test_blank_prices_do_not_count_toward_the_minimum():
    """A board of six entries where four have no price is a board of two."""
    assert hold_multiplier([0.3, 0.3, None, None, 0.0, 0.0], 1.0) is None


def test_a_multiplier_below_one_is_refused():
    """Prices summing to fewer scorers than the line supports means a book
    with no hold, which does not happen. Passing it through would inflate
    every fair price in the game instead of admitting the estimate broke."""
    assert hold_multiplier([0.05] * 8, 10.0) is None
    assert hold_multiplier([0.0] * 8, 5.0) is None


def test_no_expected_scorers_is_unmeasurable():
    assert hold_multiplier([0.3] * 8, 0.0) is None
    assert hold_multiplier([0.3] * 8, -1.0) is None


def test_hold_multiplier_is_the_overround():
    assert abs(hold_multiplier([0.5] * 10, 4.0) - 1.25) < 1e-9
    assert abs(game_prices([0.5] * 10, 4.0)["overround"] - 0.25) < 1e-9
    assert game_prices([0.5] * 10, 4.0)["listed"] == 10
    assert game_prices([0.3] * 2, 4.0)["hold_multiplier"] is None


# --- the price ------------------------------------------------------------
def test_devigging_lengthens_the_fair_price():
    """A +200 shot is 33.3% raw. On a board carrying 30% overround his
    fair price is 25.6% — +291. That gap is most of the question on a
    touchdown board, not a rounding detail."""
    raw = american_to_prob(200)
    fair = fair_probability(raw, 1.30)
    assert abs(raw - 1 / 3) < 0.01
    assert abs(fair - 0.2564) < 0.001
    assert american(fair) == 290


def test_an_unmeasured_hold_leaves_the_price_alone():
    assert fair_probability(0.4, None) == 0.4
    assert fair_probability(0.4, 0.0) == 0.4


def test_american_round_trips_both_sides_of_even():
    assert american(0.25) == 300
    assert american(0.60) == -150
    assert american(0.50) == 100
    assert american(0.0) is None and american(1.0) is None
    for odds in (-260, -150, 120, 300, 700):
        assert american(american_to_prob(odds)) == odds


# --- the board ------------------------------------------------------------
def _board(n, prob, key="g"):
    return [{"g": key, "p": prob} for _ in range(n)]


def test_board_hold_measures_each_game_separately():
    cands = _board(10, 0.50, "KC-BUF") + _board(10, 0.30, "SF-LA")
    holds = board_hold(cands,
                       game_of=lambda c: c["g"],
                       implied_of=lambda c: c["p"],
                       scorers_of=lambda k: 4.0)
    assert abs(holds["KC-BUF"] - 1.25) < 1e-9
    assert abs(holds["SF-LA"] - 0.75) < 1e-9 if "SF-LA" in holds else True
    # 3.0 / 4.0 is below 1, so that game is refused outright rather than
    # having everyone's fair price inflated.
    assert "SF-LA" not in holds


def test_board_hold_drops_a_game_it_cannot_price():
    cands = _board(10, 0.50, "KC-BUF") + _board(10, 0.50, "SF-LA")
    holds = board_hold(cands,
                       game_of=lambda c: c["g"],
                       implied_of=lambda c: c["p"],
                       scorers_of=lambda k: 4.0 if k == "KC-BUF" else None)
    assert set(holds) == {"KC-BUF"}


def test_board_hold_ignores_candidates_with_no_game():
    cands = _board(8, 0.50, "KC-BUF") + [{"g": None, "p": 0.9}]
    holds = board_hold(cands,
                       game_of=lambda c: c["g"],
                       implied_of=lambda c: c["p"],
                       scorers_of=lambda k: 3.0)
    assert set(holds) == {"KC-BUF"}
    assert abs(holds["KC-BUF"] - 4.0 / 3.0) < 1e-9      # the stray did not count


# --- sharing the margin out ------------------------------------------------
def test_the_power_exponent_makes_the_fair_prices_add_up():
    """k is defined by what it produces: fair prices summing to the
    scorers the game line supports. Check the definition, not the
    solver's arithmetic."""
    probs = [0.50] * 10
    k = power_exponent(probs, 4.0)
    assert k and abs(sum(p ** k for p in probs) - 4.0) < 1e-6
    assert k > 1.0                       # a real board needs shrinking


def test_the_power_exponent_refuses_the_same_boards_the_multiplier_does():
    assert power_exponent([0.5] * (MIN_PRICED - 1), 1.0) is None
    assert power_exponent([0.5] * 10, 0.0) is None
    assert power_exponent([0.05] * 8, 10.0) is None       # no margin to share
    # And at the boundary it says so rather than pricing a whole game off
    # K_MAX, which would be the solver reporting failure as an answer.
    assert power_exponent([0.99] * 400, 1.0) is None
    assert K_MIN < (power_exponent([0.5] * 10, 4.0) or 0) < K_MAX


def test_power_takes_more_off_the_dart_and_less_off_the_bell_cow():
    """The favourite-longshot bias, which is the whole reason for the
    method: books load margin onto the long prices. Splitting a board's
    overround evenly over-corrects the short price and under-corrects the
    dart -- deleting the reliable picks while flattering the lottery
    tickets, which is the worst pairing available."""
    prices = [-125, 110, 110, 150, 200, 200, 250, 250, 300, 350, 350, 400,
              450, 450, 500, 550, 600, 600, 700, 750, 800, 900]
    raw = [american_to_prob(p) for p in prices]
    scorers = 4.60
    mult = hold_multiplier(raw, scorers)
    k = power_exponent(raw, scorers)
    prop, power = Devig.proportional(mult), Devig.power(k, mult - 1.0)
    short, dart = american_to_prob(-125), american_to_prob(900)
    assert power.fair(short) > prop.fair(short)      # bell-cow keeps more
    assert power.fair(dart) < prop.fair(dart)        # dart keeps less
    # They cross in the middle of the board rather than one dominating.
    mid = american_to_prob(250)
    assert abs(power.fair(mid) - prop.fair(mid)) < 0.01


def test_both_methods_still_lengthen_every_price():
    """Whatever the allocation, no player may come out of a de-vig with a
    BETTER price than the book posted — that would be manufacturing edge
    out of the correction itself."""
    prices = [-125, 110, 150, 200, 250, 300, 400, 550, 700, 900]
    raw = [american_to_prob(p) for p in prices]     # sums to 2.88
    k = power_exponent(raw, 2.2)
    mult = hold_multiplier(raw, 2.2)
    assert k and mult
    for d in (Devig.power(k, mult - 1.0), Devig.proportional(mult)):
        for r in raw:
            assert d.fair(r) < r, (d.kind, r)


def test_the_board_defaults_to_power_and_says_so():
    assert DEFAULT_METHOD == POWER
    cands = [{"g": "KC-BUF", "p": american_to_prob(o)}
             for o in (-125, 110, 150, 200, 300, 450, 600, 900)]
    got = board_devig(cands, game_of=lambda c: c["g"],
                      implied_of=lambda c: c["p"], scorers_of=lambda k: 2.0)
    assert got["KC-BUF"].kind == POWER
    # And the method is a choice a caller can make, not a hard-coded one.
    forced = board_devig(cands, game_of=lambda c: c["g"],
                         implied_of=lambda c: c["p"],
                         scorers_of=lambda k: 2.0, method=PROPORTIONAL)
    assert forced["KC-BUF"].kind == PROPORTIONAL


def test_an_unsolvable_board_falls_back_to_even_rather_than_to_nothing():
    """If the exponent cannot be placed, the overround it would have
    shared out is still real. Spreading it evenly is imperfect; not
    de-vigging at all is the one option known to be wrong."""
    from engine import devig as mod
    real = mod.power_exponent
    try:
        mod.power_exponent = lambda *a, **k: None
        got = mod.board_devig(
            [{"g": "x", "p": 0.5} for _ in range(10)],
            game_of=lambda c: c["g"], implied_of=lambda c: c["p"],
            scorers_of=lambda k: 4.0)
    finally:
        mod.power_exponent = real
    assert got["x"].kind == PROPORTIONAL
    assert abs(got["x"].param - 1.25) < 1e-9


def test_a_bare_multiplier_still_means_what_it_used_to():
    """Callers that only ever knew about one hold number keep working,
    and a loose float is never guessed at."""
    assert as_devig(1.30).kind == PROPORTIONAL
    assert abs(as_devig(1.30).fair(0.26) - 0.20) < 1e-9
    assert as_devig(None) is None
    assert as_devig(0.0) is None
    assert as_devig("nonsense") is None
    d = Devig.power(1.2, 0.2)
    assert as_devig(d) is d


def test_a_devig_leaves_an_impossible_probability_alone():
    for d in (Devig.proportional(1.3), Devig.power(1.2, 0.2)):
        assert d.fair(0.0) == 0.0
        assert d.fair(1.0) == 1.0


def test_sharing_the_margin_evenly_would_delete_the_short_half_of_the_board():
    """The concrete reason POWER is the default rather than a preference.

    A player only survives the credibility veto AND the EV floor together
    while his own share of the vig stays under about 5 probability points
    — because a model may disagree with fair by at most
    MAX_CREDIBLE_EDGE (0.10), the shrink halves that to 0.05, and the vig
    is what the halved edge has to cover.

    Splitting a board's overround evenly puts 8.9 points on the bell-cow
    and 1.6 on the dart, so the bell-cow can never qualify however good
    he is. Sharing it by price puts 4.4 on one and 2.7 on the other, and
    the board stays whole. The two treatments differ by whether half the
    touchdown board exists."""
    prices = [-125, 110, 110, 150, 200, 200, 250, 250, 300, 350, 350, 400,
              450, 450, 500, 550, 600, 600, 700, 750, 800, 900]
    raw = [american_to_prob(p) for p in prices]
    scorers = 4.60
    mult, k = hold_multiplier(raw, scorers), power_exponent(raw, scorers)
    prop, power = Devig.proportional(mult), Devig.power(k, mult - 1.0)
    ceiling = 0.05                                   # MAX_CREDIBLE_EDGE / 2

    def gradeable(d):
        return [p for p, r in zip(prices, raw) if r - d.fair(r) < ceiling]

    assert gradeable(power) == prices                # every price survives
    lost = [p for p in prices if p not in gradeable(prop)]
    assert lost, "proportional is supposed to lose the short end here"
    assert max(lost) <= 200                          # and it is the short end
    assert -125 in lost                              # the bell-cow first


# --- the direction --------------------------------------------------------
#: 0.285 raw sits inside MAX_CREDIBLE_EDGE at both holds, so these tests
#: measure the hold's effect rather than tripping the separate
#: implausible-disagreement veto — which a wider hold does trip sooner,
#: and which is its own protection.
def _pick(hold=None, under=None, odds=300, model_prob=0.285):
    return build_pick(
        player="A", team="KC", opponent="BUF", market=ANYTIME_TD,
        label="Anytime TD", book="dk", odds=odds, model_prob=model_prob,
        under_odds=under, opportunities=3.0, opp_target=3.0,
        primary_reason="r", reasons=[], caveats=[], sport="nfl",
        hold_override=hold)


def test_measuring_the_hold_moves_ev_down_not_up():
    """The correction has to be protective or it is not worth having.
    `build_pick` shrinks the model toward the market, so a WIDER hold
    lowers the de-vigged implied probability, which drags the shrunk
    model probability down with it and cuts EV. Anyone wiring this in
    expecting more picks has the sign backwards."""
    assumed, measured = _pick(), _pick(hold=1.30)
    assert measured.implied_prob < assumed.implied_prob
    assert measured.model_prob < assumed.model_prob
    assert measured.ev_per_unit < assumed.ev_per_unit


def test_the_displayed_edge_moves_the_OTHER_way_and_that_is_the_trap():
    """`edge` is model minus the DE-VIGGED price, and the model is pinned
    halfway between them — so edge is always half the raw disagreement,
    and lowering the fair price mechanically WIDENS it. A wider hold
    therefore raises edge and confidence while cutting EV.

    Pinned because it is the whole reason the grade needs its own gate:
    the two numbers on the card genuinely move in opposite directions,
    and only one of them is what gets paid."""
    assumed, measured = _pick(), _pick(hold=1.30)
    assert measured.edge > assumed.edge
    assert measured.ev_per_unit < assumed.ev_per_unit


def test_the_standing_assumption_is_the_fallback_not_the_answer():
    """ONE_SIDED_HOLD's own comment says a longshot prop's real hold is
    usually wider than its 6%. A game we could measure must not fall back
    to it, and a game we could not must still price."""
    assert ONE_SIDED_HOLD == 1.06
    assert _pick(hold=None).implied_prob == _pick().implied_prob
    assert _pick(hold=1.30).implied_prob < _pick(hold=1.06).implied_prob


def test_a_two_way_price_ignores_the_measured_hold():
    """When both sides are quoted the de-vig is exact. A board-wide
    estimate must not overwrite a number we can compute properly."""
    exact, forced = _pick(under=-400), _pick(under=-400, hold=1.30)
    assert exact.implied_prob == forced.implied_prob


def test_the_card_reports_the_vig_it_actually_priced_against():
    """A pick priced off a measured 30% must not keep printing the
    assumed 6% in its caveat — the caveat is the disclosure, and a false
    one is worse than none."""
    vig = [c for c in _pick(hold=1.30).caveats if "vig" in c]
    assert vig and "30.0%" in vig[0]
    assert "6%" not in vig[0]
    assumed = [c for c in _pick().caveats if "vig" in c]
    assert assumed and "6%" in assumed[0]


def test_calibrated_prob_takes_the_same_hold_as_build_pick():
    """The display path and the pick path have to agree, or the same
    player reads differently on two parts of one page."""
    prob, implied = calibrated_prob("nfl", ANYTIME_TD, 0.285, 300,
                                    None, hold_override=1.30)
    pick = _pick(hold=1.30)
    assert abs(implied - pick.implied_prob) < 1e-9
    assert abs(prob - pick.model_prob) < 1e-9


# --- grading the bet, not the disagreement --------------------------------
def _scan(hold, odds, want):
    """First priced pick at ``odds`` satisfying ``want``, or None.

    Searched rather than hard-coded because `calibrated` applies whatever
    curve the box has fitted, and a probability chosen against this
    container's store would mean something else on the droplet — which is
    the suite's own doctrine (run_tests: "THE SUITE MUST NOT READ THE BOX
    IT IS RUNNING ON").
    """
    for i in range(20, 900):
        p = build_pick(
            player="A", team="KC", opponent="BUF", market=ANYTIME_TD,
            label="Anytime TD", book="dk", odds=odds, model_prob=i / 1000,
            under_odds=None, opportunities=3.0, opp_target=3.0,
            primary_reason="r", reasons=[], caveats=[], sport="nfl",
            hold_override=hold)
        if want(p):
            return p
    return None


def test_a_price_that_does_not_pay_cannot_carry_a_grade():
    """The defect the measured hold uncovered: a mid-priced shot the model
    likes by several points against the FAIR price, graded "Play" at high
    confidence while losing money at the price on offer.

    It stayed hidden for as long as the hold was assumed at 6%, because
    EV turns negative at edge = implied x (hold - 1) — 0.014 on a 24%
    shot, just under the 0.015 Lean bar. The two lines coincided by
    accident. A real overround pushes EV negative well past the Lean and
    Play bars and opens the whole band underneath them."""
    from engine.longshots import _grade
    losing = _scan(1.30, 285, lambda p: p.ev_per_unit < 0 and p.edge >= 0.03
                   and p.confidence >= 6.0)
    assert losing, "no negative-EV pick in the graded band — check the scan"
    # On edge and confidence alone the old grader called this a Play.
    assert _grade(losing.confidence, losing.edge) != "Pass"
    # Grading the bet instead of the disagreement refuses it.
    assert losing.grade == "Pass"
    assert losing.stake_units == 0.0


def test_no_graded_pick_anywhere_on_the_board_loses_money():
    """The band above is not the only place it can happen, so sweep the
    priced grid rather than pinning one point: across both holds, five
    prices and the full range of model probabilities, a graded pick must
    never carry negative EV."""
    for hold in (None, 1.06, 1.30, 1.35):
        for odds in (120, 200, 285, 450, 700):
            for i in range(50, 700, 5):
                p = build_pick(
                    player="A", team="KC", opponent="BUF", market=ANYTIME_TD,
                    label="Anytime TD", book="dk", odds=odds,
                    model_prob=i / 1000, under_odds=None, opportunities=3.0,
                    opp_target=3.0, primary_reason="r", reasons=[],
                    caveats=[], sport="nfl", hold_override=hold)
                assert p.grade == "Pass" or p.ev_per_unit > 0, \
                    (hold, odds, i / 1000, p.grade, p.ev_per_unit)


def test_the_ev_gate_does_not_touch_a_pick_that_does_pay():
    """A guard that also removed the good picks would be a worse bug than
    the one it fixes."""
    good = _scan(1.06, 300, lambda p: p.grade != "Pass")
    assert good, "the EV gate left nothing gradeable at all"
    assert good.ev_per_unit > 0
    assert good.stake_units > 0


def test_the_grader_matches_the_game_lines_grader_s_doctrine():
    """`betting._grade` already grades on "net edge — what's left after
    the vig, not before it", having found this same thing on the
    game-lines side. The long-shot board was the last one grading the
    disagreement instead of the bet, and it must not drift back."""
    from engine.longshots import _grade
    assert _grade(9.0, 0.06, ev=-0.01) == "Pass"
    assert _grade(9.0, 0.06, ev=0.0) == "Pass"          # break-even is not a bet
    assert _grade(9.0, 0.06, ev=0.05) == "Strong Play"
    # Omitted EV keeps the old behaviour, so no caller is silently changed
    # by the new parameter — only the one that passes it.
    assert _grade(9.0, 0.06) == "Strong Play"


# --- both lists, one book -------------------------------------------------
def _td_candidates(hold=None, share=0.11, odds=250):
    """Two identical mid-priced scorers in one game."""
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=-7.0, total=52.0)
    opp = Team(abbr="BUF", name="Bills",
               defense=DefenseProfile(team="BUF", vs_rb_rush=1.2))
    out = []
    for name in ("A", "B"):
        p = Prop(player=name, team="KC", opponent="BUF", position="WR",
                 market=ANYTIME_TD,
                 logs=[GameLog(week=i + 1, opponent="X", value=float(v))
                       for i, v in enumerate([1, 1, 0, 1, 0, 1])],
                 career_avg=1.0, vs_opponent_avg=None,
                 lines=[SportsbookLine("DK", 0.5, odds, None)])
        out.append({"prop": p, "game": g, "opponent": opp,
                    "opportunity_share": share, "odds": odds, "book": "DK",
                    "under_odds": None, "hold": hold})
    return out


#: The de-vig a real 22-player board produced (engine/devig's table).
BOARD = Devig.power(1.1378, 0.188)


def _graded_candidates(hold):
    """Candidates that actually produce a graded pick on THIS box.

    Searched, not tuned: which usage share clears the bar depends on the
    calibration curve the box has fitted, and once a real overround is
    priced in the qualifying window is narrow — a player survives the
    credibility veto and the EV floor together only while his own share
    of the vig stays under about 5 probability points.
    """
    from engine.touchdowns import build_td_longshots
    for odds in (150, 200, 250, 300, 350, 400, 450):
        for i in range(4, 60):
            cands = _td_candidates(hold, share=i / 100, odds=odds)
            if build_td_longshots(cands, limit=6, per_game=2):
                return cands
    return None


def test_the_value_picks_and_the_watchlist_price_against_the_same_hold():
    """Feeding one list and not the other is this codebase's most repeated
    bug — it has happened with xFP and again with the hold. The two lists
    answer different questions ("what is mispriced" vs "who is most
    likely") but they must answer them about the same book."""
    from engine.touchdowns import build_td_longshots, td_watchlist
    cands = _graded_candidates(BOARD)
    assert cands, "no board configuration produced a graded pick to compare"
    picks = build_td_longshots(cands, limit=6, per_game=2)
    watch = td_watchlist(cands)
    assert picks and watch
    by_player = {r["player"]: r for r in watch}
    matched = 0
    for pick in picks:
        row = by_player.get(pick.player)
        if row:
            assert abs(row["implied_prob"] - round(pick.implied_prob, 4)) < 1e-4
            assert abs(row["model_prob"] - round(pick.model_prob, 4)) < 1e-4
            matched += 1
    assert matched, "the two lists shared no player, so nothing was compared"


def test_the_watchlist_alone_would_have_missed_the_hold():
    """Guards the half-wired case directly: if only the picks path took
    the override, the watchlist's numbers would not move at all."""
    from engine.touchdowns import td_watchlist
    plain = {r["player"]: r["implied_prob"] for r in td_watchlist(_td_candidates())}
    held = {r["player"]: r["implied_prob"]
            for r in td_watchlist(_td_candidates(BOARD))}
    assert plain and held
    assert all(held[k] < plain[k] for k in plain)


# --- the pipeline ---------------------------------------------------------
def test_the_pipeline_keys_a_game_the_same_way_from_either_side():
    from engine.pipeline import _game_key
    a = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-7.0, total=52.0)
    b = Game(home="BUF", away="KC", weather=Weather(dome=True), spread=+7.0, total=52.0)
    assert _game_key(a) == _game_key(b)
    assert _game_key(None) is None


def _slate_candidates(game, prices_by_book):
    """Candidates whose props carry a full multi-book line set."""
    names = [f"P{i}" for i in range(len(next(iter(prices_by_book.values()))))]
    out = []
    for i, name in enumerate(names):
        lines = [SportsbookLine(book, 0.5, prices[i], None)
                 for book, prices in prices_by_book.items()]
        p = Prop(player=name, team="KC", opponent="BUF", position="WR",
                 market=ANYTIME_TD, logs=[], career_avg=1.0,
                 vs_opponent_avg=None, lines=lines)
        out.append({"prop": p, "game": game,
                    "odds": max(pr[i] for pr in prices_by_book.values())})
    return out


DK = [-125, 110, 110, 150, 200, 200, 250, 250, 300, 350, 350, 400,
      450, 450, 500, 550, 600, 600, 700, 750, 800, 900]
FD = [-115, 105, 120, 160, 190, 215, 240, 265, 290, 340, 365, 390,
      470, 440, 520, 540, 620, 590, 680, 780, 830, 880]


def test_the_pipeline_measures_the_hold_off_the_board_it_is_pricing():
    """NOTHING HISTORICAL IS NEEDED. The board already holds every quoted
    scorer in the game and the schedule holds that game's total and
    spread, so the hold is measurable at build time — no journal, no
    settled season, no state file.

    A real 52-point board lands near a 20% overround, several times the
    6% the pricing path had been assuming."""
    from engine.pipeline import _td_board_fairs, _game_key
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=-7.0, total=52.0)
    fairs = _td_board_fairs(_slate_candidates(g, {"dk": DK}), slate=None)
    assert fairs
    q = fairs[(_game_key(g), "P0")]
    assert 0.1 < q.overround < 0.5
    assert q.overround > ONE_SIDED_HOLD - 1.0
    assert q.kind == DEFAULT_METHOD
    assert q.book == "dk"
    # A fair price, not a transform: it is the reference book's own
    # number de-vigged, so the best-of-books price cannot be de-vigged
    # a second time on top of the shopping.
    assert q.fair(0.99) == q.prob
    assert q.prob < american_to_prob(DK[0])


def test_shopping_across_books_must_not_erase_the_margin():
    """The bug this replaced. Both boards take each player's BEST price
    across books, and summing those sums a line no book offers: best
    price is the lowest implied probability, so the sum comes in low and
    the hold with it. Two books erased 13% of the real margin here, and
    it compounds with every book added — always in the direction that
    makes the book look fairer and the edge look bigger."""
    from engine.pipeline import _td_board_fairs, _game_key
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=-7.0, total=52.0)
    one = _td_board_fairs(_slate_candidates(g, {"dk": DK}), slate=None)
    two = _td_board_fairs(_slate_candidates(g, {"dk": DK, "fd": FD}), slate=None)
    key = (_game_key(g), "P0")
    # Adding a second book adds prices to shop, and must not move the
    # measured margin at all — it is measured inside one book.
    assert two[key].overround == one[key].overround
    assert two[key].book in ("dk", "fd")
    # What the old best-of-books sum would have produced, for contrast.
    best = [min(american_to_prob(a), american_to_prob(b))
            for a, b in zip(DK, FD)]
    inside = [american_to_prob(o) for o in DK]
    assert hold_multiplier(best, 4.6) < hold_multiplier(inside, 4.6)


def test_the_reference_board_is_the_most_complete_one():
    """A truncated board under-states the sum and therefore the hold, so
    the book listing the most players sets the margin. Ties break to the
    greediest board: assuming a book is fairer than it is invents edge,
    assuming it is greedier only costs picks."""
    from engine.devig import reference_book
    full = {f"p{i}": 0.2 for i in range(20)}
    short = {f"p{i}": 0.9 for i in range(4)}
    assert reference_book({"thin": short, "full": full}) == "full"
    greedy = {f"p{i}": 0.25 for i in range(20)}
    assert reference_book({"fair": full, "greedy": greedy}) == "greedy"
    assert reference_book({}) == ""


def test_a_player_the_reference_book_never_listed_gets_no_fair_price():
    """Better a standing assumption than a fair price invented off a
    board that never quoted him."""
    from engine.devig import board_fair
    from engine.odds import american_to_prob as ap
    books = {"dk": {f"P{i}": ap(o) for i, o in enumerate(DK)},
             "fd": {"Z": ap(300)}}
    got = board_fair(books, 4.6)
    assert "P0" in got and "Z" not in got


def test_a_game_with_no_total_is_left_unpriced():
    """A schedule row without a total cannot say how many scorers to
    expect, so that game keeps the standing assumption instead of being
    handed a number invented from nothing."""
    from engine.pipeline import _td_board_fairs
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=0.0, total=0.0)
    assert _td_board_fairs(_slate_candidates(g, {"dk": DK}), slate=None) == {}


def test_a_thin_game_on_a_real_board_falls_back_rather_than_guessing():
    from engine.pipeline import _td_board_fairs, _game_key
    thick = Game(home="KC", away="BUF", weather=Weather(dome=True),
                 spread=-7.0, total=52.0)
    thin = Game(home="SF", away="LA", weather=Weather(dome=False),
                spread=-3.0, total=44.0)
    cands = _slate_candidates(thick, {"dk": DK})
    cands += _slate_candidates(thin, {"dk": [200, 200, 200]})
    fairs = _td_board_fairs(cands, slate=None)
    assert any(k[0] == _game_key(thick) for k in fairs)
    assert not any(k[0] == _game_key(thin) for k in fairs)


def test_every_candidate_gets_the_hold_before_either_list_is_built():
    """`_long_shots` must stamp the fair price onto the candidate dicts,
    since that dict is the only thing both builders see. Checked
    structurally rather than by matching a comment: the assignment has to
    precede both calls in the source's execution order."""
    import ast
    import inspect
    from engine import pipeline
    fn = next(n for n in ast.walk(ast.parse(inspect.getsource(pipeline)))
              if isinstance(n, ast.FunctionDef) and n.name == "_long_shots")
    stamp = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Subscript)
             and isinstance(n.slice, ast.Constant) and n.slice.value == "hold"]
    builders = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("build_td_longshots", "td_watchlist")]
    assert stamp, "_long_shots never sets a hold on its candidates"
    assert builders, "_long_shots no longer builds either list by name"
    assert max(stamp) < min(builders)


# --- college football -----------------------------------------------------
def test_college_measures_its_hold_the_same_way():
    """One code path, both sports. CFB prices a game at a time and NFL a
    slate, but a second copy of the arithmetic would be a second place to
    get the allocation wrong."""
    from engine.cfb.tds import game_fairs
    quotes = {f"p{i}": [{"book": "dk", "yes_odds": o}]
              for i, o in enumerate(DK)}
    got = game_fairs(quotes, spread_home=-14.0, total=58.5)
    assert got
    q = next(iter(got.values()))
    assert q.kind == DEFAULT_METHOD and q.book == "dk"
    assert q.overround > 0


def test_college_refuses_a_game_with_no_line_or_a_thin_menu():
    """Group of Five menus are routinely four players deep, and that is
    exactly when an invented hold would do the most damage."""
    from engine.cfb.tds import game_fairs
    quotes = {f"p{i}": [{"book": "dk", "yes_odds": o}]
              for i, o in enumerate(DK)}
    assert game_fairs(quotes, spread_home=None, total=58.5) == {}
    assert game_fairs(quotes, spread_home=-14.0, total=None) == {}
    thin = {f"p{i}": [{"book": "dk", "yes_odds": 200}] for i in range(3)}
    assert game_fairs(thin, spread_home=-14.0, total=58.5) == {}


def test_college_prices_both_of_its_lists_off_the_same_measurement():
    """The CFB board builds its watch and its picks in one loop, so the
    measurement has to happen before the loop body — not inside either
    branch, which is how the two lists start disagreeing about the same
    player."""
    import ast
    import inspect
    from engine.cfb import tds
    fn = next(n for n in ast.walk(ast.parse(inspect.getsource(tds)))
              if isinstance(n, ast.FunctionDef)
              and n.name == "build_cfb_td_longshots")
    measured = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "game_fairs"]
    used = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.keyword) and n.arg == "hold_override"]
    assert measured, "the CFB board never measures its own hold"
    assert len(used) >= 2, "only one of the two CFB lists takes the hold"
    assert max(measured) < min(used)


def test_college_keeps_the_measured_scoring_baselines():
    """Both FBS constants in engine/cfb/tds were 8-12% high against the
    logs — 28.8 points and 3.4 offensive touchdowns against a measured
    26.70 and 3.03 — and the conversion the de-vig depends on is its own
    fitted number rather than their ratio, because it maps a MARKET total
    and they describe realised ones."""
    from engine.cfb import tds
    assert abs(tds.CFB_AVG_TEAM_POINTS - 26.70) < 0.01
    assert abs(tds.CFB_AVG_TEAM_OFF_TDS - 3.03) < 0.01
    assert abs(tds.CFB_TD_PER_POINT - 0.1145) < 0.0001
    # Not the ratio of the two averages: the market's mean implied total
    # runs half a point below the realised mean, and the conversion has
    # to absorb that or it is biased where it is used.
    assert tds.CFB_TD_PER_POINT != tds.CFB_AVG_TEAM_OFF_TDS / tds.CFB_AVG_TEAM_POINTS


def test_college_does_not_get_its_own_scorers_constant():
    """Measured, not assumed. Over 2,710 CFB games the shared pair scored
    0.650 held-out MAE against the CFB-specific fit's 0.657 — a paired
    t of -1.46, indistinguishable — while the CFB handbook's own
    D = 0.88/0.92 + 0.20 scored 0.838 at t = -5.62.

    Its blowout rule buys nothing either: splitting the fit by spread
    moved held-out error by 0.0008 scorers, and the raw ratio is flat
    across spread buckets with the WIDEST spreads lowest, which is the
    opposite of the claim it rests on."""
    from engine import devig
    handbook = lambda tds_, spread: tds_ * (0.92 if spread >= 21 else 0.88) + 0.20
    for total_tds, realised in ((5.0, 3.93), (7.0, 5.22), (9.0, 6.55),
                                (11.5, 7.67)):
        ours = devig.expected_distinct_scorers(total_tds / 2, total_tds / 2)
        for spread in (7, 28):
            theirs = handbook(total_tds, spread)
            # A margin, not a bare comparison: nearer by a rounding error
            # would be no reason to prefer one form over the other.
            assert abs(ours - realised) + 0.15 < abs(theirs - realised), \
                (total_tds, spread, ours, theirs, realised)
    # And there is no CFB-specific constant to drift from the NFL one.
    assert not hasattr(devig, "CFB_SCORERS_SLOPE")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
