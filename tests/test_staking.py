"""Staking invariants — the rules that keep "bet 0.00 units" impossible.

The bug these lock down: grades were scored against the DE-VIGGED fair
probability while Kelly was scored against the price actually charged.
At standard −110/−110 juice break-even sits ~2.4 points above fair, so a
"Lean" at +1.2 points over fair was a 1.2-point LOSS at the window —
recommended on the board, then sized by Kelly at 0.00 units, then
journaled as a bet that could never win or lose a unit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.betting import (MARKET_SHRINK, MAX_CREDIBLE_EDGE, MIN_STAKE_UNITS,
                            _grade, _kelly_stake, favourite_surcharge, net_edge)
from engine.odds import american_to_prob, devig_two_way, expected_value

PRICES = (-200, -140, -120, -115, -110, -105, 100, 120, 150, 250, 400)
PROBS = [x / 200.0 for x in range(20, 190)]      # 0.10 … 0.945


def test_net_edge_is_measured_against_the_real_price():
    # At −110/−110 the fair number is 50% but you must clear 52.38%.
    fair_over, _ = devig_two_way(-110, -110)
    assert abs(fair_over - 0.5) < 1e-9
    assert abs(american_to_prob(-110) - 0.5238) < 1e-4
    # A model at 51.5% beats "fair" by 1.5 pts but LOSES to the price.
    assert 0.515 - fair_over > 0.01
    assert net_edge(0.515, -110) < 0
    assert expected_value(0.515, -110) < 0


def test_no_graded_bet_is_ever_unsizeable():
    """Every bet the board grades must be one Kelly will stake."""
    offenders = [(p, o) for o in PRICES for p in PROBS
                 for conf in (4.5, 6.5, 8.0, 10.0)
                 if _grade(conf, net_edge(p, o), o) != "Pass"
                 and _kelly_stake(p, o) <= 0]
    assert not offenders, f"graded but unsizeable: {offenders[:5]}"


def test_no_graded_bet_is_ever_negative_ev():
    offenders = [(p, o) for o in PRICES for p in PROBS
                 for conf in (4.5, 6.5, 8.0, 10.0)
                 if _grade(conf, net_edge(p, o), o) != "Pass"
                 and expected_value(p, o) <= 0]
    assert not offenders, f"graded but −EV: {offenders[:5]}"


def test_positive_kelly_never_rounds_away_to_zero():
    """A real edge must never render as 0.00u — the floor exists so the
    display and the journal agree that this is a bet."""
    for o in PRICES:
        be = american_to_prob(o)
        for bump in (0.0005, 0.001, 0.003, 0.01):
            p = be + bump
            if p >= 1.0:
                continue
            s = _kelly_stake(p, o)
            assert s >= MIN_STAKE_UNITS, (o, p, s)
    # Below break-even Kelly still says zero, loudly and correctly.
    for o in PRICES:
        assert _kelly_stake(american_to_prob(o) - 0.01, o) == 0.0


def test_stake_scales_with_edge_and_stays_capped():
    # On the 1u = 1% scale a solid edge REACHES the cap (that is the fix —
    # the old ruler kept everything at pocket change), so the ordering is
    # strict below the cap and flat at it.
    small = _kelly_stake(0.53, -110)
    mid = _kelly_stake(0.56, -110)
    big = _kelly_stake(0.75, -110)
    assert MIN_STAKE_UNITS <= small < mid <= big <= 1.0
    assert big == 1.0, "a strong edge at an ordinary price stakes the cap"


def test_grade_ladder_requires_real_net_edge():
    # Thresholds are net of the vig now: at −110 these are the model
    # probabilities each tier demands. There is NO Lean tier — a lean is a
    # bet that failed the filter published anyway (docs/NFL_MODEL.md §10),
    # so what used to grade Lean is a Pass.
    assert _grade(10.0, net_edge(0.520, -110), -110) == "Pass"   # below the price
    assert _grade(10.0, net_edge(0.528, -110), -110) == "Pass"   # old "Lean" band
    assert _grade(10.0, net_edge(0.535, -110), -110) == "Play"
    assert _grade(10.0, net_edge(0.546, -110), -110) == "Strong Play"
    # Confidence still gates independently of price edge.
    assert _grade(3.0, net_edge(0.600, -110), -110) == "Pass"


def test_favourite_surcharge_targets_the_measured_failure():
    """The journal showed favourites hitting 45.7% against a 66.9%
    break-even (p=0.001) while underdogs held up. The surcharge must
    therefore bite on chalk and leave everything else alone."""
    # Underdogs and near-even prices: untouched.
    for o in (250, 150, 120, 100, -105, -110, -120):
        assert favourite_surcharge(o) == 0.0 or favourite_surcharge(o) < 0.001, o
    # Requirement climbs monotonically as the price shortens.
    sur = [favourite_surcharge(o) for o in (-140, -170, -200, -235, -300)]
    assert sur == sorted(sur) and sur[0] > 0 and sur[-1] > sur[0]


def test_heavy_chalk_is_unreachable_even_at_a_maximum_edge():
    """−235 and shorter is the band that produced a −40% ROI. Even the
    largest edge the model is allowed to claim must not grade there."""
    def best_possible_net(o, u):
        fair, _ = devig_two_way(o, u)
        best_hit = fair + MARKET_SHRINK * MAX_CREDIBLE_EDGE
        return best_hit - american_to_prob(o)
    for o, u in ((-235, 195), (-300, 250), (-400, 320)):
        net = best_possible_net(o, u)
        assert _grade(10.0, net, o) == "Pass", (o, net)
    # Moderate favourites stay reachable — this is a surcharge, not a ban.
    # (−200 used to squeak in through the deleted "Lean" rung; without it,
    # the reachable band ends around −170 — stricter, and intended.)
    for o, u in ((-140, 120), (-170, 145)):
        assert _grade(10.0, best_possible_net(o, u), o) != "Pass", o
    assert _grade(10.0, best_possible_net(-200, 170), -200) == "Pass"


def test_confidence_does_not_penalise_underdogs():
    """A +650 shot and a −110 shot with the SAME edge and the SAME data
    quality must score the same confidence. The old scorer paid up to 2.5
    points for a high win probability, handicapping every plus-money bet
    before any evidence was weighed — and favourites are the band this
    journal measured as unprofitable."""
    from engine.betting import _confidence_score

    class _Form:
        sample_games = 20

    class _Proj:
        form = _Form()
        mean, std = 1.0, 0.3

    proj = _Proj()
    dog = _confidence_score(0.0341, 0.161, proj)
    fav = _confidence_score(0.0341, 0.535, proj)
    assert dog == fav, (dog, fav)
    # And a real edge on a longshot must be able to clear the board's bar.
    assert dog >= 6.0, dog
    # Bigger edge still scores higher; the ordering that matters survives.
    assert _confidence_score(0.045, 0.161, proj) > dog


# --- one scale, priced for trust (engine/staking.py) ------------------------
# The report that started this was read straight off the board: "we put .1
# unit on home runs but then .1 units on regular -100 props." Two rulers —
# the parlay spec's 1u = 1% and the prop paths' private ``* 20`` — plus no
# price awareness at all, so a solid -110 play displayed next to a +475
# dime at nearly the same size, and the ROI denominator inherited it.

def test_a_solid_ordinary_prop_finally_stakes_a_real_unit():
    """Quarter Kelly at p=.57 / -110 is ~2.4% of bankroll — the grade cap
    (1u for an A) binds, and the board shows a unit, not pocket change."""
    from engine.quality import STAKE_CAP_U
    assert _kelly_stake(0.57, -110, 0.25, STAKE_CAP_U["A"]) == 1.0
    assert _kelly_stake(0.60, -110, 0.5, STAKE_CAP_U["A+"]) == 2.0


def test_a_longshot_is_a_dime_whatever_kelly_thinks():
    """Kelly at long odds LIKES a big claimed edge (21% at +475 is a fat
    fraction) — but that is exactly where our probabilities are least
    trustworthy, per the home-run receipts (said 14%, hit 11%). The price
    cap outranks the conviction."""
    from engine import staking as S
    from engine.quality import STAKE_CAP_U
    assert _kelly_stake(0.24, 350, 0.25, STAKE_CAP_U["A"]) == 0.1
    assert _kelly_stake(0.21, 475, 0.5, STAKE_CAP_U["A+"]) == 0.1
    assert S.price_cap_units(200) == S.LONGSHOT_CAP_U
    assert S.price_cap_units(150) == S.DOG_CAP_U
    assert S.price_cap_units(119) == float("inf")


def test_the_separation_ethan_asked_for_holds():
    """"1 unit on the regular props and .1 on the homer props" — the
    exact request, as arithmetic."""
    from engine.quality import STAKE_CAP_U
    regular = _kelly_stake(0.57, -105, 0.25, STAKE_CAP_U["A"])
    homer = _kelly_stake(0.24, 350, 0.25, STAKE_CAP_U["A"])
    assert regular == 1.0 and homer == 0.1


def test_every_sport_converts_through_the_shared_scale():
    """The ``* 20`` ruler must be gone from every stake path — it is how
    two sports could disagree about what a unit means."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in ("engine/betting.py", "engine/longshots.py",
                 "engine/ufc/model.py", "engine/nba/pipeline.py",
                 "cfb_build.py"):
        src = open(os.path.join(root, path), encoding="utf-8").read()
        assert "* 20" not in src, f"{path} still converts on its own ruler"
        assert "staking" in src, f"{path} does not use the shared scale"


def test_ufc_lands_on_the_same_scale():
    from engine.ufc.model import stake_units as ufc_stake
    # Fifth Kelly under the spec's 2.5%-of-bankroll cap: a strong read
    # stakes real units now, and a live dog at +250 stakes the dime.
    assert ufc_stake(0.65, -150) == 2.5
    assert ufc_stake(0.45, 250) == 0.1


def test_the_longshot_engine_still_deals_dimes():
    from engine.longshots import _stake
    assert _stake(0.24, 350) == 0.1
    assert _stake(0.10, 800) == 0.0                    # no edge → no bet


def test_the_mult_downweights_and_zero_kills():
    from engine import staking as S
    a = S.to_units(0.02, -110, mult=1.0)
    b = S.to_units(0.02, -110, mult=0.5)
    assert b < a
    assert S.to_units(0.02, -110, mult=0.0) == 0.0
    assert S.to_units(0.0005, -110) == S.MIN_STAKE_UNITS


def test_history_is_not_restated():
    """The scale change reads honestly FORWARD; settled stakes are the
    receipts of bets as they were made. Nothing in staking touches the
    journal."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "staking.py"),
               encoding="utf-8").read()
    for banned in ("UPDATE", "INSERT", "sqlite", "ledger"):
        assert banned not in src, banned



# --- why a stake is the number it is ----------------------------------------
def test_every_stake_can_say_which_rule_set_it():
    """Ethan, 2026-08-12, on a board reading 0.25 / 0.25 / 0.25 / 0.15 /
    0.05: "It doesn't make any sense and feels random."

    It was not random — four rules can set a stake and the board showed
    none of them. When a cap binds, the stake stops carrying information
    about the edge (five different edges all print the cap), and without
    the reason beside it that is indistinguishable from noise."""
    from engine.staking import units_with_reason, kelly_fraction

    # A fat edge at a long price: the price band decides, not Kelly.
    u, why = units_with_reason(kelly_fraction(0.45, 250) * 0.25, 250, 2.0)
    assert u == 0.1 and "price band" in why, (u, why)

    # The same conviction at a short price: Kelly decides.
    u, why = units_with_reason(kelly_fraction(0.55, -110) * 0.25, -110, 2.0)
    assert "Kelly" in why and u > 0.1, (u, why)

    # A grade cap below what Kelly asked for.
    u, why = units_with_reason(kelly_fraction(0.75, -110) * 0.25, -110, 0.5)
    assert u == 0.5 and "grade" in why, (u, why)

    # A hairline edge lands on the floor, and says so rather than
    # implying Kelly asked for the minimum.
    u, why = units_with_reason(0.0002, -110, 2.0)
    assert u == 0.1 and "floor" in why.lower(), (u, why)

    # No bet is no bet.
    assert units_with_reason(0.0, -110)[0] == 0.0


def test_the_recommendation_carries_the_margin_over_the_real_price():
    """`edge` is measured against the de-vigged fair; Kelly sizes on the
    margin over the PRICE WE GET, which is smaller by the juice. Showing
    only the first advertises +4.3% on a bet with ~1.3 points of real
    margin — the gap that made the stakes look arbitrary."""
    from engine.betting import Recommendation
    f = Recommendation.__dataclass_fields__
    assert "net_edge" in f and "stake_basis" in f
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    assert "over the price you get" in app
    assert "r.stake_basis" in app


def test_the_slate_scaling_gets_the_last_word_in_the_reason():
    """The exposure cap is the last thing to touch a stake, so it must be
    the last thing in the explanation — otherwise the card credits Kelly
    for a number the slate cap chose."""
    src = open(os.path.join(ROOT, "engine", "correlation.py"),
               encoding="utf-8").read()
    assert 'r["stake_basis"] = (' in src
    assert "scaled" in src and "slate cap" in src


def test_the_stakes_preview_reads_the_board_and_names_the_policies():
    """Ethan, 2026-08-12: "We need too figure out the basics and how much
    we should be putting on each bet." A screenshot cannot answer that;
    the board can. `--stakes` prints the margin over the REAL price and
    what each Kelly fraction asks for, so the trade is visible."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--stakes" in argv' in src and "def show_stakes" in src
    fn = src[src.index("def show_stakes"):src.index("def show_standings")]
    # It must price off the margin over the OFFERED price, not the
    # headline edge — that distinction is the whole point.
    assert "net_edge" in fn and "kelly_fraction" in fn
    for policy in ("full", "half", "quarter"):
        assert policy in fn, policy
    # And it must not imply size fixes a losing edge.
    assert "Size multiplies whatever edge is really there" in fn
    assert "stakecheck.py" in fn

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
