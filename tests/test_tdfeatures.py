"""Judging a candidate feature on top of the model, not beside it.

`engine.scriptfit` closed the team-level question — the implied total is
the whole between-game signal — so every remaining gain has to come from
within a team, and the shipped within-team feature set is spent (AUC
0.7210, against 0.7225 for an unconstrained logistic over everything the
model already knows). `engine.tdfeatures` is how a NEW input earns its
place.

Two things are pinned here, and both were live bugs first:

  * the harness is NFL ONLY, because the probability it judges against
    comes from `tdbacktest`, which replays the NFL model. Grading it on
    college logs produced a confident table showing the college
    calibration failing badly; the real college chain was fine.
  * a candidate is scored on top of the model's own logit, never on its
    own. A feature that merely restates the model looks strong alone and
    adds nothing, which is exactly what has to be detected.

Run directly: `python3 tests/test_tdfeatures.py`
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tdbacktest as B                             # noqa: E402
from engine import tdfeatures as F                             # noqa: E402


def _rows(n=6000, seed=7, useful=False):
    """Graded player-weeks whose truth we control.

    `useful=True` adds a feature the model genuinely does not know, so
    the harness has to find it; `useful=False` adds pure noise, which it
    has to reject."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        season = 2021 + i % 4
        truth = rng.uniform(0.03, 0.55)
        extra = rng.gauss(0.0, 1.0)
        # The model sees `truth` with some slack; the candidate carries
        # information about the outcome only when `useful`.
        prob = min(max(truth * rng.uniform(0.85, 1.15), 0.01), 0.95)
        real = truth + (0.10 * extra if useful else 0.0)
        rows.append({"season": season, "week": f"{i % 18 + 1:03d}",
                     "player": f"P{i}", "team": f"T{i % 8}",
                     "prob": prob, "extra": extra,
                     "scored": 1 if rng.random() < min(max(real, 0.01), 0.99)
                     else 0,
                     "prior_weeks": [], "short": ("P", str(i), f"T{i % 8}")})
    return rows


def _extra(row, ctx):
    return row["extra"]


# --- the sport guard ------------------------------------------------------
def test_the_replay_refuses_a_sport_whose_model_it_does_not_run():
    """THE FALSE ALARM THIS PREVENTS. `tdbacktest` replays
    `engine.touchdowns`, the NFL model. Pointed at college logs on
    2026-08-30 it reported the college calibration missing by nearly 2x
    in the band longshots live in — 8% claimed against 15.7% landed,
    AFTER correction — and every number was the NFL model being graded on
    college data. On the chain college actually ships the same bands come
    out at 1.25 and 1.05 and the stored fit is sound.

    Nothing was wrong except the question, and a question that wrong
    should not be answerable by accident."""
    try:
        B.run(None, "cfb")
    except ValueError as exc:
        assert "cfbtdfit" in str(exc), exc
        assert "allow_any_sport" in str(exc), exc
    else:                                             # pragma: no cover
        raise AssertionError("grading the NFL model on college logs "
                             "must not be the quiet default")


def test_the_deliberate_cross_chain_comparison_is_still_possible():
    """Refusing it outright would be the other failure — comparing two
    chains on one population is a legitimate thing to want. It just is
    not a measurement OF that sport's board, and it has to be asked for
    by name."""
    import inspect
    src = inspect.getsource(B.run)
    assert "allow_any_sport" in src
    assert "and not allow_any_sport" in src


# --- judging a candidate --------------------------------------------------
def test_a_feature_the_model_already_knows_adds_nothing():
    """The whole design. A candidate is fitted ON TOP of the model's own
    logit, so restating the model scores zero here even though it would
    look strong measured alone."""
    rows = _rows(useful=False)
    for r in rows:
        r["extra"] = F.logit(r["prob"])       # a perfect restatement
    got = F.evaluate(rows, _extra, {})
    assert not got.get("thin"), got
    assert abs(got["auc_cand"] - got["auc_base"]) < 0.005, got


def test_pure_noise_is_rejected():
    got = F.evaluate(_rows(useful=False), _extra, {})
    assert not got.get("thin"), got
    assert got["auc_cand"] - got["auc_base"] < 0.01, got


def test_a_feature_the_model_is_missing_is_found():
    """And the harness has to be able to find something, or a table of
    four zeroes says nothing about the features."""
    got = F.evaluate(_rows(useful=True), _extra, {})
    assert not got.get("thin"), got
    assert got["auc_cand"] - got["auc_base"] > 0.02, got
    assert got["ll_cand"] < got["ll_base"], got


def test_a_candidate_is_never_scored_on_a_season_it_trained_on():
    """Every form here contains the baseline, so in sample each can only
    improve on it and the winner would be whichever fitted luckiest."""
    seen = []
    real_fit = F.fit_logistic

    def spy(xs, ys):
        seen.append(len(xs))
        return real_fit(xs, ys)

    F.fit_logistic = spy
    try:
        F.evaluate(_rows(), _extra, {})
    finally:
        F.fit_logistic = real_fit
    assert seen, "nothing was fitted at all"
    assert all(n < 6000 for n in seen), \
        "a fold trained on the whole sample, so nothing was held out"


def test_rows_the_feature_cannot_score_are_dropped_not_zeroed():
    """A missing value is not a zero. Filling one in would assert that a
    player has no red-zone role rather than that we cannot see it — the
    same distinction `cfbtdfit.Sample.rz_share` documents."""
    rows = _rows()
    for r in rows[:2000]:
        r["extra"] = None
    got = F.evaluate(rows, _extra, {})
    assert got["rows"] == 4000, got
    assert abs(got["coverage"] - 4000 / 6000) < 1e-9, got


def test_a_thin_candidate_says_so_instead_of_reporting_a_number():
    got = F.evaluate(_rows(n=500), _extra, {})
    assert got["thin"] and got["rows"] == 500, got


# --- the scores themselves ------------------------------------------------
def test_auc_shares_ties_because_most_of_the_board_is_zero():
    """Several candidates are zero for most players. Ranking ties
    arbitrarily would hand a feature credit for an ordering it never
    expressed."""
    pairs = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
    assert F.auc(pairs) == 0.5
    assert F.auc([(0.9, 1), (0.1, 0)]) == 1.0
    assert F.auc([(0.1, 1), (0.9, 0)]) == 0.0


def test_log_loss_punishes_a_confident_miss():
    assert F.log_loss([(0.99, 0)]) > F.log_loss([(0.6, 0)]) > \
        F.log_loss([(0.4, 0)])


def test_the_logistic_recovers_a_coefficient_it_should_know():
    xs = [[1.0, x] for x in (-3, -2, -1, 0, 1, 2, 3) * 60]
    ys = [1 if x[1] > 0 else 0 for x in xs]
    beta = F.fit_logistic(xs, ys)
    assert beta is not None and beta[1] > 1.0, beta


def test_the_report_names_what_it_measured():
    lines = F.report.__doc__ or ""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "tdfeatures.py")).read()
    # The measured table lives in the module, not in a commit message
    # nobody will find again.
    assert "0.7212 -> 0.7217" in src, \
        "the vacancy result has to stay written down — it is the one " \
        "that looked real"
    assert "confound" in src
    for label, _fn in F.CANDIDATES:
        assert label in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
