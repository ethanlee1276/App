"""A card that contradicted itself, and the duplicate that let it.

Ethan found a pick on the live board siding UNDER 58.5 on a player the
same card projected for 71.6, with the reason reading "projects 71.6038
under the 58.5 line". Two halves of one sentence disagreeing, at full
float precision, beside a projection field rounded to a tenth.

Neither half was dishonest on its own. `pick_side` chooses from the
empirical distribution rather than the mean, and §8 is explicit that
averages lie on right-skewed stats: three quiet games and one 180-yard
afternoon put the mean above the median, so the under can be the better
side while the mean sits above the line. Only the text claimed otherwise.

`engine/mlb/betting.py` had already been corrected — on 2026-08-22 it
grew the second branch and the explanation. `engine/betting.py`, which
serves NFL and CFB, kept the single branch for six more days, over
exactly the stretch when the NFL calibrations were themselves fitting
one-sided. So a whole board of unders went out with an impossible
sentence under each one.

Two copies that drifted, which is the shape this repo keeps finding. Now
one copy, and these tests are about that copy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.betting import under_reason


# --- the sentence has to be true ---------------------------------------------
def test_a_mean_below_the_line_reads_as_a_plain_projection():
    got = under_reason(41.2, 58.5, 1)
    assert "projects 41.2 under the 58.5 line" in got


def test_a_mean_above_the_line_never_claims_it_is_below():
    """Ethan's card, exactly. The old text put "projects 71.6038 under
    the 58.5 line" on screen."""
    got = under_reason(71.6038, 58.5, 1)
    assert "under the 58.5 line" not in got
    assert "the mean is 71.6" in got
    assert "clears 58.5 less often than the price implies" in got


def test_a_mean_exactly_on_the_line_takes_the_plain_branch():
    assert "projects 58.5 under" in under_reason(58.5, 58.5, 1)


def test_the_skew_branch_explains_itself_rather_than_asserting():
    """A reader who sees a projection above the line they are being told
    to bet under needs the reason, not a restatement."""
    got = under_reason(71.6, 58.5, 1)
    assert "big games inflate it" in got


# --- precision matches the card the sentence sits on -------------------------
def test_nfl_precision_agrees_with_its_stored_projection():
    """`engine/betting.py` stores round(proj.mean, 1). Two numbers on one
    card describing one quantity must agree."""
    import inspect
    from engine import betting
    src = inspect.getsource(betting.evaluate_prop)
    assert "projection=round(proj.mean, 1)" in src
    assert "under_reason(proj.mean, best.line, 1)" in src


def test_mlb_precision_agrees_with_its_stored_projection():
    import inspect
    from engine.mlb import betting as mlb_betting
    src = inspect.getsource(mlb_betting.evaluate_mlb_prop)
    assert "projection=round(proj.mean, 2)" in src
    assert "under_reason(proj.mean, best.line, 2)" in src


def test_no_caller_prints_the_mean_at_full_float_precision():
    """`:g` is what put 71.6038 on a card whose projection field said
    71.6."""
    got = under_reason(71.60384717, 58.5, 1)
    assert "71.6038" not in got
    assert "71.6" in got


def test_the_line_keeps_its_own_formatting():
    """Lines are halves and wholes; 58.5 must not become 58.50 and 60
    must not become 60.0."""
    assert "the 58.5 line" in under_reason(41.0, 58.5, 1)
    assert "the 60 line" in under_reason(41.0, 60.0, 1)


# --- one copy, so it cannot drift again --------------------------------------
def test_there_is_exactly_one_copy_of_this_sentence():
    """The bug was not the wording, it was having two of it."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    hits = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or ".git" in path.parts:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "Model sides UNDER" in line:
                hits.append(f"{path.relative_to(root)}:{i}")
    assert len(hits) == 2, (
        f"expected both branches in engine/betting.py alone, found: {hits}")
    assert all(h.startswith("engine/betting.py:") for h in hits), hits


def test_the_mlb_engine_uses_the_shared_helper():
    import inspect
    from engine.mlb import betting as mlb_betting
    src = inspect.getsource(mlb_betting)
    assert "under_reason" in src
    assert "his actual game log" not in src, \
        "the shared copy is sport-agnostic and carries no pronoun"


# --- the cause a blocked pick is given ---------------------------------------
def test_an_unreliable_calibration_is_not_also_blamed_on_the_tier_bar():
    """A pick blocked because its market cannot be priced was ALSO told
    its edge missed the tier bar — naming the wrong cause, and quoting an
    edge the same card had just said was unpriceable. engine/mlb guarded
    this; engine/betting.py did not."""
    import inspect
    from engine import betting
    from engine.mlb import betting as mlb_betting
    for mod, fn in ((betting, "evaluate_prop"),
                    (mlb_betting, "evaluate_mlb_prop")):
        src = inspect.getsource(getattr(mod, fn))
        assert "if credible and calibration_ok and has_market" in src, \
            f"{mod.__name__} can blame the tier bar for a calibration block"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
