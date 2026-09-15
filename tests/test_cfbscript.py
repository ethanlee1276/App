"""Game script and the college starter-pull problem.

The old multiplier was monotone in the spread: the bigger the favourite,
the more touchdown equity it handed his lead back, up to a +12% clamp.
The CFB handbook calls the opposite "the single most common way college
football prop bettors lose bets they handicapped correctly", and 4,123
lead-back games agree — the share peaks near a two-touchdown favourite
and falls away after, because past that margin the starters come out.

These tests pin the SHAPE and the two things easiest to get wrong about
it: that the curve bends rather than climbing, and that the NFL version
was measured separately and deliberately not changed.

Run directly: `python3 tests/test_cfbscript.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cfb.tds import (
    script_multiplier, RB_SCRIPT, WR_SCRIPT, SCRIPT_LEAD_CAP,
    RB_SCRIPT_CLAMP, WR_SCRIPT_CLAMP,
)


def _mult(lead, pos):
    """`spread_home` is negative when home is favoured."""
    return script_multiplier(-float(lead), True, pos)[0]


# --- the shape ------------------------------------------------------------
def test_a_lead_back_peaks_at_a_two_touchdown_favourite_and_falls_after():
    """The whole correction. Measured share of his team's touchdowns by
    margin: 0.250 at 0-7, 0.234 at 7-14, 0.236 at 14-21, 0.251 at 21-28,
    then 0.201 at 28+. A curve that only climbs cannot say that."""
    at = {L: _mult(L, "RB") for L in (0, 7, 14, 21, 28, 35)}
    assert at[14] > at[0]                      # still a favourable script
    assert at[14] > at[28] > at[35]            # but it turns over
    assert at[35] < at[0]                      # and ends below a pick'em
    peak = max(at, key=lambda L: at[L])
    assert 7 <= peak <= 21, peak


def test_the_old_monotone_form_is_gone():
    """`1 + 0.005 x lead` said a 28-point favourite's back was worth +12%.
    The logs put him at -20% against a 0-7 favourite's back, so the old
    number was wrong by about a third of his equity."""
    old = min(1.12, max(0.88, 1.0 + 0.005 * 28))
    assert old == 1.12
    assert _mult(28, "RB") < 1.05


def test_the_underdog_end_moved_furthest_and_nobody_was_watching_it():
    """A back on a 14-point-plus underdog scored 0.10-0.18 of his team's
    touchdowns against the old model's 0.88-0.93 — roughly twice what the
    data supports. That end never showed up in the handbook's warning and
    was the larger error."""
    assert _mult(-28, "RB") < 0.70
    assert _mult(-14, "RB") < 0.90
    assert _mult(-28, "RB") < _mult(-14, "RB") < _mult(0, "RB")


def test_pass_catchers_move_the_other_way_and_by_more_than_before():
    """Trailing teams throw. The direction was already right; the size
    was about six times too small — measured 1.32 at a 28-point underdog
    against the old 1.05."""
    assert _mult(-28, "WR") > 1.20
    assert _mult(28, "WR") < 0.90
    assert _mult(-28, "WR") > _mult(0, "WR") > _mult(28, "WR")
    assert _mult(-28, "TE") == _mult(-28, "WR")


def test_a_back_and_a_receiver_disagree_about_a_blowout():
    """They have to, or the multiplier is not modelling anything: a
    favourite runs it and an underdog throws it."""
    assert _mult(21, "RB") > _mult(21, "WR")
    assert _mult(-21, "WR") > _mult(-21, "RB")


def test_a_quarterback_is_left_out_of_it():
    """Rushing quarterback touchdowns follow designed goal-line packages,
    which the role share already carries."""
    assert _mult(21, "QB") == 1.0
    assert script_multiplier(-21.0, True, "QB")[1] == []


# --- the guards -----------------------------------------------------------
def test_the_curve_is_held_at_the_edge_of_the_data_not_extrapolated():
    """College spreads reach 45 and a quadratic taken that far past its
    data goes somewhere silly — the raw RB curve is under 0.46 at -45."""
    for pos in ("RB", "WR"):
        assert _mult(-45, pos) == _mult(-SCRIPT_LEAD_CAP, pos)
        assert _mult(45, pos) == _mult(SCRIPT_LEAD_CAP, pos)


def test_every_value_stays_inside_its_stated_clamp():
    """An explicit floor and ceiling so a re-fit cannot quietly widen the
    effect without someone changing a number that says so."""
    for lead in range(-60, 61):
        assert RB_SCRIPT_CLAMP[0] <= _mult(lead, "RB") <= RB_SCRIPT_CLAMP[1]
        assert WR_SCRIPT_CLAMP[0] <= _mult(lead, "WR") <= WR_SCRIPT_CLAMP[1]


def test_a_pick_em_changes_nothing():
    """Normalised at zero, so the base share means what it says."""
    assert _mult(0, "RB") == 1.0
    assert _mult(0, "WR") == 1.0


def test_no_line_means_no_opinion():
    assert script_multiplier(None, True, "RB") == (1.0, [])


def test_the_home_and_away_sides_are_mirror_images():
    """`spread_home` is one number and both teams read it — getting the
    sign wrong for one side would hand the underdog the favourite's
    script."""
    for spread in (-24.0, -7.0, 3.5, 17.0):
        assert script_multiplier(spread, True, "RB")[0] == \
            script_multiplier(-spread, False, "RB")[0]


# --- what the card says ---------------------------------------------------
def test_a_negative_number_on_a_big_favourite_explains_itself():
    """"-9% for a 30-point favourite" reads as a bug without the reason
    beside it, and this board is shown to people."""
    _, why = script_multiplier(-30.0, True, "WR")
    assert why and "stops throwing" in why[0]
    _, why = script_multiplier(-30.0, True, "RB")
    if why:                                    # only when the shift is real
        assert "starters come out" in why[0]


def test_a_trailing_team_says_why_its_receiver_gained():
    _, why = script_multiplier(24.0, True, "WR")
    assert why and "trailing teams throw" in why[0]


def test_a_close_game_says_nothing():
    """A 2% wobble is not a reason, and a card full of them is noise."""
    assert script_multiplier(-2.0, True, "RB")[1] == []


# --- the NFL was checked and left alone -----------------------------------
def test_the_nfl_multiplier_was_not_harmonised_with_this_one():
    """The obvious next move after refitting college is to make the NFL
    match. Measured leave-one-season-out over 2021-25, the form already
    there wins — RB1 7.75 against the quadratic's 8.26, WR1 21.76 against
    24.00 — because NFL spreads live inside about 14 points, where a
    straight line and this curve are the same line. College runs to 45,
    and that is where the curve bends."""
    import inspect
    from engine import touchdowns
    src = inspect.getsource(touchdowns.script_td_multiplier)
    assert "0.010 * lead" in src and "0.004 * lead" in src
    assert "Do not." in src, "the reason it stays linear is not written down"


def test_the_two_sports_disagree_at_a_college_sized_spread():
    """And they should: the same 28-point margin is an ordinary Saturday
    and an NFL outlier that essentially never happens."""
    from engine.models import Game, Weather
    from engine.touchdowns import script_td_multiplier
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=-28.0, total=52.0)
    nfl, _ = script_td_multiplier(g, "KC", "RB")
    assert nfl > 1.10                          # NFL: still climbing
    assert _mult(28, "RB") < 1.05              # college: turned over


# --- the near-miss --------------------------------------------------------
def test_the_receiver_curve_survives_the_measurement_that_looked_damning():
    """2026-08-30. The receiver curve was nearly deleted on a real number
    about the wrong players.

    Scoring the whole WR+TE GROUP's share of its team's touchdowns by
    weighted squared error, leave-one-season-out, the shipped curve came
    out WORSE THAN NO SCRIPT TERM AT ALL in three of four held-out
    seasons (0.08845 against 0.08820), and a two-sided linear form beat
    both. Re-run on the population the curve is applied to — the lead
    receiver, the one a book actually quotes — under the objective it was
    fitted for, it wins by a distance:

        summed held-out chi-square   no script   SHIPPED   two-sided
        CFB lead receiver               56.4       32.6       39.1
        CFB lead back                  100.2       74.1       76.7
        NFL lead receiver                26.7       25.8       28.8
        NFL lead back                    41.9       39.3       44.7

    Both are true. A heavy favourite's WR1 loses share TO HIS OWN
    BACKUPS — the group keeps the touchdowns, the starter stops getting
    them — so the group number is blind to exactly the effect the curve
    encodes.

    What this test defends is the SIGN on the favoured side, which is the
    thing the group measurement would have flattened. If a future refit
    wants to change it, the bar is the lead-receiver population above,
    not the group.
    """
    # A heavy favourite's top receiver: measurably DOWN, not flat.
    assert _mult(21, "WR") < 0.95, \
        "the favoured side of the receiver curve is the part that was " \
        "nearly zeroed out on a group-level measurement"
    assert _mult(28, "WR") < _mult(14, "WR") < _mult(0, "WR")
    # And a buried underdog's receiver is up, which both readings agree on.
    assert _mult(-21, "WR") > 1.05


def test_the_two_curves_disagree_about_who_the_starters_coming_out_hurts():
    """The reconciliation above only makes sense if the back and the
    receiver come off the same effect from opposite ends, so pin it.

    Past a two-touchdown lead the back's equity turns over (starters
    come out, backups get the goal-line work) while the receiver's keeps
    falling — a favourite that is already throwing less does not start
    throwing more to its WR1 at +28."""
    assert _mult(28, "RB") < _mult(14, "RB")      # turned over
    assert _mult(28, "WR") < _mult(14, "WR")      # never turned
    # And they never point the same way at a normal college line.
    for lead in (7, 14, 21):
        assert _mult(lead, "RB") > 1.0 > _mult(lead, "WR")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")

