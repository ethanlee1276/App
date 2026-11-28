"""Brier and ECE, on their own, flatter a model that knows nothing.

The MLB hits backtest reported:

    Calibration Brier 0.2373   ECE 0.024
      p 0.4-0.6: predicted 55% → actual 56%  (n=217090)
      p 0.6-0.8: predicted 64% → actual 68%  (n=67819)

ECE 0.024 is inside "trustworthy" and it is a true statement. It is also
not the one that matters, for two reasons.

Brier reads like a score out of something. It is not. The bar is what you
would score by ignoring the model entirely and predicting the base rate
every time — p(1−p). On a 57% market that is 0.245, so 0.2373 is a margin
of 0.008, which is a very different claim from the one the raw number
appears to make.

And calibration hides sharpness completely. A model answering "about 50%"
to everything is PERFECTLY calibrated and perfectly useless. 73% of that
run's forecasts sat in the 0.4-0.6 bin. That matters directly for betting:
an unsharp model disagrees with a confident market by a lot, in both
directions, and every disagreement looks like an edge without being one —
which is exactly the symmetric 57%-over-the-ceiling board we started from.

Both controls are here. A measurement that cannot fail is not a
measurement, and this one has to separate a model that knows things from
one that hedges.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backtest import BacktestReport


def _report(pairs):
    """A report carrying these (prediction, outcome) pairs and the Brier
    they actually imply — so skill() is scored against a real number and
    not one we asserted."""
    r = BacktestReport()
    r.pairs = pairs
    r.n = len(pairs)
    r.brier = sum((p - o) ** 2 for p, o in pairs) / len(pairs)
    return r


def _hedger(n=4000, base=0.57, seed=1):
    """Predicts the base rate every time. Perfectly calibrated, zero skill."""
    rng = random.Random(seed)
    return [(base, 1 if rng.random() < base else 0) for _ in range(n)]


def _oracle(n=4000, seed=2):
    """Knows the answer. Sharp and skilful."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        o = 1 if rng.random() < 0.57 else 0
        out.append((0.95 if o else 0.05, o))
    return out


# --- the two controls -------------------------------------------------------
def test_a_model_that_always_guesses_the_base_rate_scores_zero_skill():
    sk = _report(_hedger()).skill()
    assert abs(sk["skill"]) < 0.02, \
        f"a pure hedger was credited with {sk['skill']:.1%} skill"
    assert sk["hedged"] == 1.0


def test_an_oracle_scores_high_skill_and_no_hedging():
    """Without this passing, the test above only proves skill() can return
    a number near zero."""
    sk = _report(_oracle()).skill()
    assert sk["skill"] > 0.8, f"an oracle only scored {sk['skill']:.1%}"
    assert sk["hedged"] == 0.0


def test_sharpness_separates_them_where_calibration_cannot():
    """The whole point. Both models are well calibrated and they are drawn
    from the same base rate, so no calibration statistic can tell them
    apart. Sharpness can, and it is the one that predicts whether
    disagreeing with the market means anything."""
    h, o = _report(_hedger()).skill(), _report(_oracle()).skill()
    assert abs(h["base_rate"] - o["base_rate"]) < 0.03, \
        "the two controls are not drawn from the same market"
    assert h["hedged"] - o["hedged"] > 0.9


def test_the_bar_is_the_always_guess_brier_not_a_round_number():
    sk = _report(_hedger(base=0.57)).skill()
    assert abs(sk["base_brier"] - 0.57 * 0.43) < 0.01


# --- refusing to answer -----------------------------------------------------
def test_a_thin_sample_returns_nothing_rather_than_a_verdict():
    assert _report([(0.5, 1)] * 50).skill() is None


def test_a_degenerate_market_returns_nothing():
    """Every outcome the same way makes p(1−p) zero — the skill score would
    divide by it."""
    r = _report([(0.9, 1)] * 500)
    assert r.skill() is None


def test_missing_pairs_do_not_crash_the_summary():
    r = BacktestReport()
    r.n = 10
    assert "Backtest over 10" in r.summary()
    assert "Skill" not in r.summary()


# --- the readout ------------------------------------------------------------
def test_the_summary_prints_both_numbers_when_it_can():
    out = _report(_oracle()).summary()
    assert "base rate" in out and "always-guess Brier" in out
    assert "Sharpness" in out


def test_a_hedging_model_is_called_out_in_words():
    """A number nobody reads is not a finding. Over half the forecasts
    sitting on the base rate deserves a sentence, not a percentage."""
    out = _report(_hedger()).summary()
    assert "hedging, not forecasting" in out


def test_a_sharp_model_is_not_accused_of_hedging():
    out = _report(_oracle()).summary()
    assert "hedging, not forecasting" not in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
