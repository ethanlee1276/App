"""The touchdown book can say whether the market ranks scorers better than the model.

Ethan, 2026-09-08: "we have player props just barley any money money
lines are touchdown crap." The touchdown rows sit just under the 55%
floor for real scorers because the shown number is the model's read
shrunk halfway to the book, and the model's read for a -200 bell cow
with an ordinary share is a coin flip. The moneylines were moved onto
the market's number on 2026-09-07 because the market was MEASURED to
rank winners better (likely.GAME_RANK_MARKET); nobody has measured the
same for scorers, because the touchdown closes live only on the box
with `odds_history`. `tdbook.rank_report` is that measurement, proven
here on synthetic player-weeks — the suite never reads the box it runs
on — and run on the droplet with `python3 -m engine.tdbook --rank`.

Run directly: `python3 tests/test_tdbook_rank.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import tdbook as B                                  # noqa: E402
from engine.rankfit import auc                                  # noqa: E402


def _weeks(n=2400, seed=5, market_knows=True, market_noise=None):
    """(model, market, scored): the market's number is the true rate when
    it knows; the model's is that rate with noise on top.

    `market_noise` gives the market the SAME kind of noise the model
    has, which is the case the verdict has to refuse — two rankings a
    bootstrap cannot separate."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        truth = rng.uniform(0.05, 0.75)
        scored = rng.random() < truth
        if market_noise is not None:
            market = min(0.99, max(0.01, truth + rng.gauss(0, market_noise)))
        else:
            market = truth if market_knows else rng.uniform(0.05, 0.75)
        model = min(0.99, max(0.01, truth + rng.gauss(0, 0.25)))
        rows.append((model, market, scored))
    return rows


def test_the_market_that_knows_the_rate_ranks_better_and_the_report_says_so():
    rows = _weeks()
    lines = B.rank_report(rows, resamples=60)
    assert lines[0].startswith("  who scores, ranked · 2,400 joined player-weeks")
    model = auc([(m, s) for m, _k, s in rows])
    market = auc([(k, s) for _m, k, s in rows])
    assert market > model, (market, model)
    assert f"model   AUC {model:.4f}" in lines[1] and f"market  AUC {market:.4f}" in lines[2]
    lo, hi = [float(x) for x in lines[3].split("[")[1].rstrip("]").split(",")]
    assert 0 < lo <= market - model <= hi, (lo, hi, market - model)
    assert lines[4].strip().startswith("the market ranks scorers better"), lines[4]


def test_a_market_that_knows_nothing_leaves_the_rows_on_the_model():
    rows = _weeks(market_knows=False)
    lines = B.rank_report(rows, resamples=60)
    assert lines[4].strip().startswith("the model ranks scorers better"), lines[4]


def test_two_rankings_the_bootstrap_cannot_separate_are_not_a_verdict():
    """The answer that matters most, because it is the one a hopeful
    reader will misread: the market a shade ahead, on an interval that
    still contains zero, leaves the rows where they are. The verdict is
    read off the far end of the interval, not the near one."""
    rows = _weeks(market_noise=0.25)
    lines = B.rank_report(rows, resamples=400)
    lo, hi = [float(x) for x in lines[3].split("[")[1].rstrip("]").split(",")]
    assert lo < 0 < hi, (lo, hi)
    assert lines[4].strip().startswith("no measurable difference"), lines[4]
    assert "leave the rows on the model" in lines[4]


def test_the_interval_is_a_95_percent_interval_not_the_range_of_the_draws():
    """One resample in four hundred crossing zero is not a reason to
    withhold the verdict, and reading the bounds off the extremes rather
    than the percentiles would withhold it. This fixture is tuned to sit
    exactly there: the widest draw is negative, the 2.5th percentile is
    not, and the answer is that the market ranks better."""
    rows = _weeks(market_noise=0.22)
    lines = B.rank_report(rows, resamples=400)
    lo, hi = [float(x) for x in lines[3].split("[")[1].rstrip("]").split(",")]
    assert 0 < lo < 0.01, (lo, hi)          # clear of zero, but only just
    assert lines[4].strip().startswith("the market ranks scorers better"), lines[4]


def test_too_few_player_weeks_is_said_not_measured():
    lines = B.rank_report(_weeks(n=1999))
    assert len(lines) == 1 and "needs 2,000" in lines[0], lines
    assert B.MIN_RANK_ROWS == 2_000


def test_the_cli_and_the_docs_carry_the_command():
    src = open(os.path.join(ROOT, "engine", "tdbook.py"), encoding="utf-8").read()
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert '"--rank" in argv' in src and "rank_report(rows)" in src
    assert "python3 -m engine.tdbook --rank" in checks
    assert "rank_report" in B.__all__


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
