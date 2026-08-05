"""Is the model leaning on a side — and can anything currently correct it?

Two things are pinned here, and the first is a trap rather than a bug.

**Projection versus actual on the bets we made is contaminated.** We bet
OVER when the projection sits above the line, so the overs we select are
disproportionately the ones where the projection's own noise ran high.
Actuals regress, a gap appears, and a perfectly unbiased model produces
it. Any test built on that comparison finds a bias every time, which is
the same as finding nothing.

What survives is the ASYMMETRY: both sides clear the same edge bar, so
both carry the same selection effect, and differencing them removes it.
The tests below check that an unbiased-but-selected book reports no
finding, and that a genuine lean planted on one side still does.

**And a real defect in journalfit**, found while writing this: the fit
paired each bet's own hit_prob with won/lost, so an over's claim and an
under's entered the same bucket as the same number. A directional lean
contributes opposite gaps on the two sides and cancels — the intercept,
the only parameter that can push a model off a side, was blind to the
thing it exists to correct.

Run directly: `python3 tests/test_sidebias.py`
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sidebias as sb                                         # noqa: E402
from engine.journalfit import as_over                         # noqa: E402


def bet(side="OVER", p=0.58, won=True, market="total_bases", sport="mlb"):
    return {"sport": sport, "market": market, "side": side, "hit_prob": p,
            "status": "won" if won else "lost", "projection": 1.8,
            "actual": 2.0, "line": 1.5, "odds": -110}


def side_book(side, n, p, realised, market="total_bases"):
    """`n` bets claiming `p`, of which `realised` fraction actually won."""
    wins = round(n * realised)
    return ([bet(side, p, True, market) for _ in range(wins)]
            + [bet(side, p, False, market) for _ in range(n - wins)])


# --- the restatement journalfit was missing ----------------------------------
def test_an_under_bet_is_restated_as_the_over_not_landing():
    def check(side, status, p_over, hit):
        got = as_over(0.58, side, status)
        assert abs(got[0] - p_over) < 1e-9 and got[1] == hit, (side, status, got)

    check("OVER", "won", 0.58, 1)
    check("OVER", "lost", 0.58, 0)
    # The two that were wrong: a winning UNDER is an over that MISSED.
    check("UNDER", "won", 0.42, 0)
    check("UNDER", "lost", 0.42, 1)


def test_the_restatement_guards_degenerate_claims():
    for bad in (None, 0.0, 1.0, -0.2, 1.4):
        assert as_over(bad, "OVER", "won") is None


def test_a_directional_lean_survives_the_restatement():
    """The whole point. Pooling raw hit_prob makes an over-leaning book look
    calibrated; restating to P(over) leaves the lean visible."""
    rows = []
    # Overs claim 60% and land 45%. Unders claim 60% and land 60%.
    for _ in range(60):
        rows.append(("OVER", 0.60, True))
    for _ in range(60):
        rows.append(("OVER", 0.60, False))
    # 120 overs at 50% realised against a 60% claim: leaning.
    for _ in range(60):
        rows.append(("UNDER", 0.60, True))
    for _ in range(40):
        rows.append(("UNDER", 0.60, False))

    naive = [(p, 1 if won else 0) for _, p, won in rows]
    restated = [as_over(p, s, "won" if won else "lost") for s, p, won in rows]

    # Pooled on raw hit_prob the book looks near its claim…
    naive_gap = sum(o for _, o in naive) / len(naive) - 0.60
    # …restated to P(over) it does not, because the unders now count as
    # evidence ABOUT the over and stop cancelling.
    over_claim = sum(p for p, _ in restated) / len(restated)
    over_real = sum(o for _, o in restated) / len(restated)
    assert abs(naive_gap) < abs(over_real - over_claim), \
        "restating did not expose the lean"


# --- the asymmetry test ------------------------------------------------------
def test_a_big_but_unproven_difference_is_not_called_no_lean():
    """The branch easiest to write badly, and the one this journal lands in.

    Overs missing their claim by twelve points more than unders, at z ≈ 1.8,
    is not "the two sides look alike" — it is a large difference the sample
    cannot yet confirm. The first draft printed "the two sides miss their
    claims by similar amounts", which would have thrown away the strongest
    hypothesis on the page.
    """
    rows = (side_book("OVER", 142, 0.58, 61 / 142)
            + side_book("UNDER", 85, 0.58, 47 / 85))
    o, u = sb._split(rows)
    a = sb.asymmetry(sb.calibration_gap(o), sb.calibration_gap(u))
    assert 1.0 < abs(a["z"]) < 2.0, a          # the fixture is in the branch
    assert abs(a["diff"]) > 0.10, "not actually a big difference"

    out = _run(rows)
    assert "SUGGESTIVE, NOT PROVEN" in out
    assert "similar amounts" not in out
    assert "leading hypothesis, not a finding" in out
    assert "to reach two sigma" in out


def test_a_genuinely_flat_pair_of_sides_says_no_lean():
    """The other side of that branch — it must still be able to say no."""
    rows = (side_book("OVER", 150, 0.58, 0.52)
            + side_book("UNDER", 150, 0.58, 0.53))
    out = _run(rows)
    assert "NO LEAN VISIBLE" in out
    assert "SUGGESTIVE" not in out


def test_a_selected_but_unbiased_book_reports_no_finding():
    """Both sides miss their claim by the same amount — the winner's curse
    applied evenly. That is not a side bias and must not read as one."""
    rows = (side_book("OVER", 120, 0.58, 0.50)
            + side_book("UNDER", 90, 0.58, 0.50))
    o, u = sb._split(rows)
    a = sb.asymmetry(sb.calibration_gap(o), sb.calibration_gap(u))
    assert abs(a["z"]) < 2, a
    assert abs(a["diff"]) < 0.02


def test_a_genuine_over_lean_is_found():
    rows = (side_book("OVER", 150, 0.58, 0.40)
            + side_book("UNDER", 150, 0.58, 0.58))
    o, u = sb._split(rows)
    a = sb.asymmetry(sb.calibration_gap(o), sb.calibration_gap(u))
    assert a["diff"] < 0, "the over side should be the one missing"
    assert a["z"] < -2, a


def test_the_gap_is_realised_minus_claimed():
    """Sign convention, stated once so the report cannot invert it: negative
    means the model claimed more than it delivered."""
    s = sb.calibration_gap(side_book("OVER", 100, 0.60, 0.45))
    assert abs(s["claimed"] - 0.60) < 1e-9
    assert abs(s["realised"] - 0.45) < 1e-9
    assert s["gap"] < 0


def test_the_error_is_poisson_binomial_not_a_pooled_rate():
    """Each bet carries its own claim, so the variance is the sum of
    p(1-p). A book of near-certain claims has a much smaller error than a
    book of coin flips at the same count, and a pooled rate would miss it."""
    tight = [bet("OVER", 0.95, i < 95) for i in range(100)]
    loose = [bet("OVER", 0.50, i < 50) for i in range(100)]
    assert sb.calibration_gap(tight)["se"] < sb.calibration_gap(loose)["se"]


# --- the report --------------------------------------------------------------
def _run(rows, **kw):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sb.report(rows, **kw)
    return " ".join(buf.getvalue().split())


def test_the_report_warns_that_the_levels_are_contaminated():
    """Someone reading only the per-side gaps would conclude both sides are
    broken. The selection effect has to be named where it is visible."""
    out = _run(side_book("OVER", 60, 0.58, 0.50)
               + side_book("UNDER", 60, 0.58, 0.50))
    assert "Read the DIFFERENCE, not the levels" in out
    assert "selection effect" in out


def test_a_thin_side_blocks_the_test_rather_than_guessing():
    out = _run(side_book("OVER", 200, 0.58, 0.40)
               + side_book("UNDER", 5, 0.58, 0.60))
    assert "Not enough on one side" in out
    assert "REAL." not in out


def test_a_found_lean_says_the_temperature_cannot_fix_it():
    out = _run(side_book("OVER", 150, 0.58, 0.40)
               + side_book("UNDER", 150, 0.58, 0.58))
    assert "REAL." in out
    assert "temperature cannot correct this" in out


def test_the_explainer_names_both_fitters_and_how_they_differ():
    assert "engine/backtest.py" in sb.EXPLAIN
    assert "engine/journalfit.py" in sb.EXPLAIN
    assert "intercept" in sb.EXPLAIN


def test_an_empty_journal_does_not_divide_by_zero():
    assert sb.report([]) == 0
    s = sb.calibration_gap([])
    assert s["n"] == 0 and s["z"] == 0.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
