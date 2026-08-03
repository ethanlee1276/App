"""The transparency pillar, and the two ways it can quietly stop being one.

The competitive study in docs/COMPETITIVE_RECIPE.md names this as the moat
competitors structurally cannot copy — a tool that sells picks cannot afford
to publish that most picks don't beat the close. A moat made of a promise is
not a moat, so these tests pin the promise to code:

  * both proper scoring rules are published, not just the gentler one;
  * the reliability diagram is a diagram — a curve against the diagonal —
    and not the bucket table wearing a chart's name;
  * the bad number ships too. Every branch that reports a score reports it
    whether or not we won, and there is no code path that hides a loss.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
DOC = open(os.path.join(ROOT, "docs", "COMPETITIVE_RECIPE.md"), encoding="utf-8").read()


def _fn(src: str, name: str) -> str:
    """One top-level function's body, by brace-free bracketing on the next
    top-level `function` keyword. Cheaper than parsing JS and sufficient
    here, where every function in this file is declared at column zero."""
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j > 0 else len(src)]


def _flat(text: str) -> str:
    """Whitespace collapsed. Prose in a template literal wraps to fit the
    column, so a sentence worth asserting on routinely spans a line break —
    matching literally would fail on formatting rather than on meaning."""
    return " ".join(text.split())


# --- the numbers -------------------------------------------------------------
def test_both_proper_scoring_rules_reach_the_payload():
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    for key in ("brier_model", "brier_market", "brier_edge",
                "logloss_model", "logloss_market", "logloss_edge", "ece"):
        assert f'"{key}"' in block, key
    assert hasattr(ledger, "LOGLOSS_CLAMP")


def test_log_loss_is_clamped_finite():
    """Unbounded at the ends: a 0% forecast on something that happened costs
    infinity, and one row would swallow the whole score."""
    from engine import ledger
    assert 0 < ledger.LOGLOSS_CLAMP < 0.01
    worst = ledger._log_loss_one(0.0, 1.0)
    assert worst == ledger._log_loss_one(ledger.LOGLOSS_CLAMP, 1.0)
    import math
    assert math.isfinite(worst)


def test_the_market_is_scored_on_the_same_bets_under_both_rules():
    """A score with nothing to beat is a number, not a claim. Brier already
    compared against the de-vigged close; log loss has to as well or it is
    decoration."""
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    assert "ll_market += _log_loss_one(fair" in block
    assert "se_market += (fair - won) ** 2" in block


def test_ece_is_population_weighted():
    from engine import ledger
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    block = src[src.index("def calibration("):src.index("HEALTH_MIN_BETS")]
    line = [l for l in block.splitlines() if 'b["actual"] - b["predicted"]' in l]
    assert line and 'b["n"] *' in line[0], line


# --- the picture -------------------------------------------------------------
def test_the_reliability_diagram_draws_the_diagonal():
    """The whole point of the chart. Predicted on x, realized on y, and the
    line y=x to measure the distance from. Without it this is a scatter plot
    of two numbers nobody can compare."""
    body = _fn(APP, "reliabilityDiagram")
    assert 'x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"' in body
    assert "stroke-dasharray" in body
    assert "perfect" in body


def test_the_axes_are_labelled_in_english():
    body = _fn(APP, "reliabilityDiagram")
    assert "model said (%)" in body
    assert "actually hit (%)" in body


def test_dot_area_tracks_sample_size_not_dot_radius():
    """Radius scaling triples the apparent weight of a bucket that is three
    times bigger, which is the opposite of what a reader should take from
    it. Area is linear in n only if the radius goes as sqrt(n)."""
    body = _fn(APP, "reliabilityDiagram")
    assert "Math.sqrt(b.n / maxN)" in body


def test_the_whiskers_are_the_same_band_as_the_rows():
    """A dot whose interval crosses the diagonal has not missed — it has not
    spoken yet. Using a different band here than the rows above would have
    the same bucket read as a miss in one place and noise in the other."""
    body = _fn(APP, "reliabilityDiagram")
    assert "b.actual - b.ci" in body and "b.actual + b.ci" in body


def test_a_one_bucket_diagram_is_not_drawn():
    """Two points make a shape; one point makes a dot next to a line, which
    invites a reading the sample cannot support."""
    body = _fn(APP, "reliabilityDiagram")
    assert "pts.length < 2" in body


def test_the_diagram_is_rendered_on_the_record_page():
    body = _fn(APP, "recCalibrationSection")
    assert "reliabilityDiagram(cal.buckets)" in body
    # And the era-scoped chart gets one too — the current model is the one
    # anybody is actually deciding about.
    assert "reliabilityDiagram(era.buckets)" in body


# --- the promise -------------------------------------------------------------
def test_the_losing_number_ships_too():
    """The line that makes this a moat rather than marketing."""
    body = _flat(_fn(APP, "calScoreBlock"))
    assert "tout with a website" in body
    assert "either way" in body


def test_both_outcomes_have_a_rendered_branch():
    """No path returns empty when we lose. The score block builds one card
    per rule from the same template regardless of sign, and only a NULL
    edge — meaning no comparison exists at all — suppresses it."""
    rule = _fn(APP, "scoreRule")
    assert "if (edge == null) return" in rule
    assert re.search(r"edge\s*>\s*0", rule), "sign only picks a colour"
    # The one early return is the missing-data case, not the losing case.
    assert rule.count("return \"\"") == 1


def test_the_two_rules_disagreeing_is_explained_rather_than_hidden():
    """Both are strictly proper, so disagreement is a finding: the gap
    against the market lives in the confident calls. Silently showing two
    contradictory verdicts is worse than showing one."""
    body = _flat(_fn(APP, "calScoreBlock"))
    assert "(cal.brier_edge > 0) !== (cal.logloss_edge > 0)" in body
    assert "not a contradiction" in body


# --- the roadmap -------------------------------------------------------------
def test_the_recipe_carries_the_source_study_unedited():
    """A living roadmap that quietly rewrites its own source is a diary, not
    a record. The study is appended verbatim below our ledger."""
    assert "# Source study, preserved unedited" in DOC
    assert "Claw Arbs" in DOC and "Swish" in DOC


def test_the_guardrails_are_decisions_not_backlog():
    """These are the items that must never drift into 'not built yet'."""
    for phrase in ("No automated bet placement",
                   "No credential sharing",
                   "No IP, device or identity spoofing",
                   "No user betting data published"):
        assert phrase in DOC, phrase


def test_the_recipe_records_what_was_not_built():
    """The half of the file that makes it usable next month."""
    assert "## Not built today" in DOC
    assert "## What to distrust in the study" in DOC


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
