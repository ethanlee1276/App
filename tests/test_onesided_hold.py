"""One assumed hold, one definition, and the measurement reaching both.

`ONE_SIDED_HOLD` was declared twice — 1.06 in `engine.longshots`, 1.05 in
`engine.odds` — the same concept under the same name with two values.
The split ran the wrong way round: four modules import the longshots one
and reason about "6%" in prose (`devigfit`, `tdbook`, `cfb.tds`,
`pipeline`), while `odds.devig_two_way`, the function that actually
turns a one-sided quote into a fair price, quietly used 5%. The
documented rule and the enforced rule were different numbers.

THE DIRECTION IS OPPOSITE IN THE TWO PATHS, which is why one number
serving both is delicate:

    odds/betting   fair = implied / hold, edge = model - fair. A wider
                   hold LOWERS fair and RAISES edge — permissive.
    longshots      `calibrated_prob` shrinks the model TOWARD implied. A
                   wider hold drags the model down and publishes fewer
                   picks — conservative.

So standardising on 1.06 loosens the recommendation board very slightly
and leaves the long-shot board alone. That is a pricing change riding on
a consistency fix, so this file pins the size of it.

AND THE ASSUMPTION SHOULD STOP MATTERING. `holdwatch` measures the real
one-sided hold; the long-shot board used it and the recommendation board
had no way to. `devig_two_way` now takes it, and `evaluate_prop` passes
what `longshots.one_sided_hold` answers — so both boards price the same
prop off the same number.

Run directly: `python3 tests/test_onesided_hold.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import longshots, odds
from engine.models import SportsbookLine
from engine.odds import american_to_prob, best_over_line, devig_two_way


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- one definition -------------------------------------------------------
def test_the_two_modules_agree_because_there_is_only_one_value():
    assert odds.ONE_SIDED_HOLD == longshots.ONE_SIDED_HOLD


def test_longshots_re_exports_rather_than_redeclaring():
    """A second literal is a second thing to forget to change."""
    src = _src("engine", "longshots.py")
    assert "from .odds import ONE_SIDED_HOLD" in src
    assert "ONE_SIDED_HOLD = 1." not in src


def test_it_settled_on_the_documented_number():
    assert odds.ONE_SIDED_HOLD == 1.06


def test_the_modules_that_quote_six_percent_still_read_the_constant():
    """`devigfit` and `tdbook` import it rather than typing 1.06, so the
    prose and the arithmetic cannot drift apart again."""
    for mod in ("devigfit.py", "tdbook.py"):
        assert "ONE_SIDED_HOLD" in _src("engine", mod), mod


# --- the size of the pricing change ---------------------------------------
def test_the_move_is_small_and_in_the_permissive_direction():
    """Stated rather than buried: a wider hold lowers fair, which raises
    edge on this path."""
    implied = american_to_prob(400)
    old_fair = implied / 1.05
    new_fair = implied / 1.06
    assert new_fair < old_fair
    assert abs(new_fair - old_fair) < 0.003, new_fair - old_fair


def test_the_long_shot_board_is_unaffected():
    """It already used 1.06, so nothing on that path moved."""
    assert longshots.one_sided_hold("nfl", "anytime_td")[0] == 1.06


# --- the measurement reaches the de-vig -----------------------------------
def test_a_measured_hold_overrides_the_assumption():
    implied = american_to_prob(400)
    assert abs(devig_two_way(400, 0, hold=1.086)[0] - implied / 1.086) < 1e-9


def test_omitting_it_falls_back_to_the_shared_constant():
    implied = american_to_prob(400)
    assert abs(devig_two_way(400, 0)[0] - implied / odds.ONE_SIDED_HOLD) < 1e-9


def test_a_two_sided_market_ignores_the_hold_entirely():
    """Both prices are real there; nothing has to be assumed, and a hold
    applied anyway would corrupt a market that needs no correction."""
    assert devig_two_way(-110, -110, hold=2.0) == devig_two_way(-110, -110)


def test_a_falsy_hold_is_treated_as_absent_not_as_zero():
    """A division by a zero or None hold would raise or return infinity
    on a live board."""
    for bad in (None, 0, 0.0):
        assert devig_two_way(400, 0, hold=bad) == devig_two_way(400, 0)


def test_the_shop_passes_it_through():
    lines = [SportsbookLine("DK", 0.5, 400, 0)]
    wide = best_over_line(lines, 1.20).fair_prob
    assert wide < best_over_line(lines).fair_prob


# --- and the prop board actually asks for it ------------------------------
def test_the_prop_evaluator_prices_off_the_measured_hold():
    """The plumbing has to connect to something. Without this the new
    argument exists and nothing ever passes it."""
    src = _src("engine", "betting.py")
    assert "one_sided_hold(sport, prop.market)" in src
    assert "pick_side(prop.lines, p_over_at,\n                                                    hold=_hold)" in src


def test_both_boards_now_read_the_same_source_for_that_number():
    """`one_sided_hold` is `holdwatch`'s measurement or the shared
    fallback — one answer, asked by both pages."""
    import inspect
    src = inspect.getsource(longshots.one_sided_hold)
    assert "load_hold" in src and "ONE_SIDED_HOLD" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
