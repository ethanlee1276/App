"""Two models price home runs. Only one of them bets.

The per-market sweep's Home Runs row reports ECE 0.278 — "the probabilities
are fiction in that market" by its own legend. hr_backtest.py, on the SAME
295,693 game logs, reports ECE 0.011 and a top-fifth that homers 3.3x as
often as the bottom.

Both are correct. They measure different models:

  * the sweep walks the GENERIC prop model over home runs. It never bets
    them — the row reports 0 bets — because Tier 3 is quarantined on the
    Long Shots board before the main pipeline sees it.
  * the Long Shots board runs engine/mlb/homeruns.py, which is the model
    actually taking money, and it is good.

That unlabelled row cost two rounds of chasing a model nobody uses. It is
now labelled in the table.

The dangerous part is downstream and is currently held together by one
early return. The calibration fitter learns from the GENERIC model's
errors, and those errors are large enough that mlb:home_runs fits to the
edge of the search grid. correction_for refuses to apply a boundary fit —
and that refusal is the ONLY thing stopping a correction derived from the
broken model being handed to the good one. The comment there records what
happened when it was applied: a raw 10.2%-vs-10.5% was dragged to 1.1%.

So the refusal is pinned here. Someone "fixing" the boundary case to make
the Home Runs row look better would silently destroy the one model in this
app that has been measured and found good.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as cal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cal_file(temperature):
    import json
    path = os.path.join(tempfile.mkdtemp(), "calibration.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"mlb:home_runs": {"temperature": temperature,
                                     "intercept": 0.0, "samples": 21271}}, fh)
    cal.reset_cache()
    return path


# --- the refusal that protects the good model -------------------------------
def test_a_fit_at_the_top_of_the_search_grid_is_never_applied():
    path = _cal_file(cal.GRID_MAX)
    try:
        assert cal.correction_for("mlb", "home_runs", path) == (1.0, 0.0)
    finally:
        cal.reset_cache()


def test_a_fit_at_the_bottom_of_the_grid_is_never_applied_either():
    path = _cal_file(cal.GRID_MIN)
    try:
        assert cal.correction_for("mlb", "home_runs", path) == (1.0, 0.0)
    finally:
        cal.reset_cache()


def test_an_ordinary_fit_IS_applied():
    """The control. Without it, "return 1.0 always" passes both tests
    above and no correction reaches any market."""
    path = _cal_file(0.7)
    try:
        t, _bias = cal.correction_for("mlb", "home_runs", path)
        assert t == 0.7
    finally:
        cal.reset_cache()


def test_the_refusal_is_explained_where_it_lives():
    """A future reader looking at the Home Runs row will want to 'fix'
    this. The reason it exists has to be at the code, not only in a test."""
    src = open(os.path.join(ROOT, "engine", "calibrate.py"),
               encoding="utf-8").read()
    i = src.index("def correction_for(")
    block = src[i:i + 1200]
    assert "boundary fit is the search failing" in block
    assert "10.2%" in block and "1.1%" in block, \
        "the measured damage is no longer recorded next to the guard"


# --- the sweep must say which model it is testing ---------------------------
def test_the_home_run_row_is_labelled_as_the_wrong_model():
    src = open(os.path.join(ROOT, "mlb_calibration.py"), encoding="utf-8").read()
    assert "generic model, NOT the Long Shots board" in src
    assert "hr_backtest.py" in src


def test_only_the_home_run_row_carries_the_label():
    src = open(os.path.join(ROOT, "mlb_calibration.py"), encoding="utf-8").read()
    i = src.index('note = (')
    assert 'd["market"] == "home_runs"' in src[i:i + 400]


# --- the two models really are different --------------------------------
def test_the_long_shot_board_does_not_use_the_generic_prop_model():
    """If these ever converge, the sweep's row would start describing the
    board's model and the label above becomes a lie."""
    pipe = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
                encoding="utf-8").read()
    assert 'r.get("tier", 2) == 3 or r.get("market") == "home_runs"' in pipe
    assert "from .homeruns import build_hr_longshots" in pipe


def test_the_hr_backtest_scores_the_board_s_model_not_the_generic_one():
    src = open(os.path.join(ROOT, "engine", "mlb", "hrbacktest.py"),
               encoding="utf-8").read()
    assert "from .homeruns import hr_probability" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
