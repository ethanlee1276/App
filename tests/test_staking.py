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


def test_stake_does_not_scale_with_edge_any_more():
    """The inversion of the old test, and the point of the change.

    This used to assert `small < mid <= big` — more claimed edge, more
    money. Our own record says that ordering put the most money on the
    worst bets (largest stake quartile: 34.5% hit, -33.9%; grade A+
    -18.3% against A's -7.9%), so the ordering is gone on purpose. Three
    very different claimed edges at one price now stake the same.
    """
    small = _kelly_stake(0.53, -110)
    mid = _kelly_stake(0.56, -110)
    big = _kelly_stake(0.75, -110)
    assert small == mid == big == 1.0
    # What DOES separate two bets is the price they are taken at.
    assert _kelly_stake(0.56, -110) > _kelly_stake(0.56, 250)


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

def test_a_standard_prop_stakes_the_base_unit():
    """Ethan, 2026-08-12: "we should have our base line unit at 1 or
    something." A standard -110 prop is exactly one unit — at 1u = 1% of
    a $1,000 bankroll, the $10 ticket he asked for."""
    from engine import staking as S
    assert S.units_for_price(-110) == S.BASE_UNITS == 1.0
    assert _kelly_stake(0.57, -110, 0.25) == 1.0
    # And the conviction no longer moves it. Same price, wildly different
    # claimed edges, identical stake — that IS the change.
    assert _kelly_stake(0.53, -110, 0.25) == _kelly_stake(0.75, -110, 0.5)


def test_the_price_sets_the_size_and_nothing_else_does():
    """"i dont think we should be judging how many units we put on a pick
    based on the grade we give it but we should base it on the line of the
    prop."

    Supported by our own record, which is why it is the rule and not a
    preference: grade A+ returned -18.3% against grade A's -7.9%, and the
    largest stake quartile was the worst of four. Sizing on conviction was
    putting the most money on the worst bets.
    """
    from engine import staking as S
    ladder = [S.units_for_price(o) for o in (-250, -150, -110, 100, 200, 400)]
    assert ladder == sorted(ladder, reverse=True), ladder
    # Equal variance per bet: stake x payout is flat between the ends.
    from engine.odds import american_to_decimal
    mid = [S.units_for_price(o) * american_to_decimal(o) for o in (-150, -110, 100, 200)]
    # Flat to within the rounding: stakes are quoted to the cent-of-a-unit,
    # so the product wobbles by about that much and no more.
    assert max(mid) - min(mid) < 0.03, mid
    # The ends are clamped, deliberately, and say so.
    assert S.units_for_price(-400) == S.MAX_PRICED_U
    assert S.units_for_price(900) == S.MIN_PRICED_U


def test_a_long_price_is_still_a_real_bet_just_a_smaller_one():
    """The old rule dropped every +200-or-longer pick to a flat 0.1u — a
    dime, whatever the price. The ladder de-rates smoothly instead, so a
    +200 is two thirds of a unit and a +475 is a third, rather than both
    being the same token."""
    from engine import staking as S
    assert 0.6 < S.units_for_price(200) < 0.7
    assert 0.3 < S.units_for_price(475) < 0.4
    assert S.units_for_price(200) > S.units_for_price(475)


def test_kelly_still_vetoes_even_though_it_no_longer_sizes():
    """The half of Kelly that was right is kept. A price that beats the
    edge is no bet at any size — dropping the sizing must not quietly
    turn the gate off too."""
    from engine import staking as S
    assert S.units_with_reason(0.0, -110)[0] == 0.0
    assert S.units_with_reason(-0.1, -110)[0] == 0.0
    assert "price beats the edge" in S.units_with_reason(0.0, -110)[1]
    assert _kelly_stake(0.40, -110, 0.25) == 0.0      # 40% at -110 is a loser


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
    # A strong read at a short price takes the ladder's ceiling; a live
    # dog at +250 takes the ladder's rung for +250 rather than the flat
    # dime the retired price band gave every underdog.
    assert ufc_stake(0.65, -150) == 1.15
    assert ufc_stake(0.45, 250) == 0.55
    assert ufc_stake(0.20, 250) == 0.0            # Kelly still vetoes


def test_the_longshot_engine_still_deals_dimes():
    """A measurement book keeps its own ticket, on purpose.

    The price ladder would give a +450 home-run ticket 0.35u. This book
    exists to find out whether the signal is real, not to carry six times
    the exposure it has ever carried, so it holds a flat nominal dime —
    see `longshots.LONGSHOT_TICKET_U`.
    """
    from engine.longshots import _stake, LONGSHOT_TICKET_U
    assert _stake(0.24, 350) == LONGSHOT_TICKET_U == 0.1
    assert _stake(0.30, 450) == 0.1
    assert _stake(0.10, 800) == 0.0                    # no edge → no bet


def test_the_mult_downweights_and_zero_kills():
    from engine import staking as S
    a = S.to_units(0.02, -110, mult=1.0)
    b = S.to_units(0.02, -110, mult=0.5)
    assert b < a
    assert S.to_units(0.02, -110, mult=0.0) == 0.0
    # A downweight severe enough to round the ticket away still lands on
    # the floor rather than on nothing — the caller asked for less, not
    # for no bet.
    assert S.to_units(0.02, -110, mult=0.01) == S.MIN_STAKE_UNITS


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

    It was not random — several rules could set a stake and the board
    showed none of them. One rule sets it now, and the string still has
    to name which rung, because "1.25u" and "1.25u because that is as
    high as the ladder goes" are different facts about the same bet."""
    from engine.staking import units_with_reason, kelly_fraction

    u, why = units_with_reason(kelly_fraction(0.45, 250) * 0.25, 250)
    assert u == 0.55 and "+250" in why, (u, why)

    u, why = units_with_reason(kelly_fraction(0.55, -110) * 0.25, -110)
    assert u == 1.0 and "base unit" in why, (u, why)

    # The same price, five times the claimed edge, the same stake — and
    # the reason says the price set it, so nobody reads the number as a
    # statement of conviction.
    u2, why2 = units_with_reason(kelly_fraction(0.75, -110) * 0.25, -110)
    assert (u2, why2) == (u, why)

    u, why = units_with_reason(0.02, -400)
    assert u == 1.25 and "ceiling" in why, (u, why)
    u, why = units_with_reason(0.02, 900)
    assert u == 0.35 and "floor" in why, (u, why)

    # A caller-side downweight is named as one, so it can never be
    # mistaken for the ladder having a second opinion about the price.
    u, why = units_with_reason(0.02, -110, 0.5)
    assert u == 0.5 and "downweight" in why, (u, why)

    assert units_with_reason(0.0, -110)[0] == 0.0


def test_no_caller_passes_a_third_positional_argument():
    """The hazard created by retiring `cap_units`.

    It was the third positional parameter; `mult` is now. A stale
    four-argument call raises TypeError and gets found immediately, but a
    stale THREE-argument one silently reinterprets a grade cap as a
    multiplier — 0.5 becomes a halving, 2.0 becomes a doubling. This test
    caught exactly that in this file, where `units_with_reason(f, 250,
    2.0)` came back 1.1u instead of the 0.1u it asserted.
    """
    import re as _re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = []
    for dirpath, _dirs, files in os.walk(root):
        if any(x in dirpath for x in (".git", "__pycache__", "/tests")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            src = open(path, encoding="utf-8").read()
            for call in _re.finditer(
                    r"\b(to_units|units_with_reason)\(([^()]*(?:\([^()]*\)[^()]*)*)\)",
                    src, _re.S):
                args = call.group(2)
                depth, parts, cur = 0, [], ""
                for ch in args:
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        depth -= 1
                    if ch == "," and depth == 0:
                        parts.append(cur); cur = ""
                    else:
                        cur += ch
                parts.append(cur)
                parts = [x.strip() for x in parts if x.strip()]
                if len(parts) >= 3 and "=" not in parts[2]:
                    bad.append(f"{os.path.relpath(path, root)}: {call.group(0)[:60]}")
    assert not bad, "third argument must be keyword (mult=): " + "; ".join(bad)


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


# --- the drawdown brake honours the floor (2026-09-02) --------------------
def test_a_halved_stake_under_the_floor_comes_off_the_board():
    """`stakecheck.py` on the droplet, 2026-09-02: 42 settled bets under
    the documented minimum, 30 of them AFTER the fix that was supposed to
    end sub-floor stakes, every one an MLB row. The cause was the
    drawdown rule halving a floored 0.1u into 0.05u — the exact rounding
    artefact with a ticket that `correlation.apply_exposure_caps`
    refuses to write one step earlier in the same pipeline."""
    from engine.staking import apply_drawdown, MIN_STAKE_UNITS
    rows = [{"recommended": True, "stake_units": 0.10, "grade": "B+"},
            {"recommended": True, "stake_units": 1.00, "grade": "A"},
            {"recommended": True, "stake_units": 0.19, "grade": "A+"}]
    scaled, dropped = apply_drawdown(rows, 0.5)
    assert (scaled, dropped) == (2, 1), (scaled, dropped)
    assert rows[0]["recommended"] is False and rows[0]["stake_units"] == 0.0
    assert rows[0]["grade"] == "Pass"
    assert "under the" in rows[0]["warnings"][0]
    assert rows[1]["stake_units"] == 0.50 and rows[1]["recommended"] is True
    assert rows[2]["stake_units"] == 0.10 >= MIN_STAKE_UNITS


def test_no_drawdown_means_nothing_moves():
    from engine.staking import apply_drawdown
    rows = [{"recommended": True, "stake_units": 0.10, "grade": "B+"}]
    assert apply_drawdown(rows, 1.0) == (0, 0)
    assert rows[0]["stake_units"] == 0.10 and rows[0]["recommended"] is True


def test_a_row_that_was_never_a_bet_is_left_alone():
    from engine.staking import apply_drawdown
    rows = [{"recommended": False, "stake_units": 0.0, "grade": "Pass"},
            {"recommended": True, "stake_units": 0.0, "grade": "Pass"}]
    assert apply_drawdown(rows, 0.5) == (0, 0)
    assert all(r["grade"] == "Pass" for r in rows)


def test_every_build_scales_through_the_one_rule():
    """Three copies of the halving loop is how one of them keeps the bug
    after the other two are fixed."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("nfl_build.py", "mlb_build.py", "nba_build.py"):
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            src = fh.read()
        assert "apply_drawdown as _dd_apply" in src, name
        assert '* dd, 2)' not in src, f"{name} still has its own halving loop"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")