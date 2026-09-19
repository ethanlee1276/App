"""The college haircut was a guess. This is the measurement.

Ethan, 2026-09-19, after the college board published 0 bets from 54
priced markets: *"do 1"* — measure the haircut rather than tune it.

`cfb.model.HAIRCUT` shrinks every raw edge before the bet bar sees it:
50% marquee, 35% standard, 25% low. Each of those is a CLAIM that the
model's disagreement with the close is that much real. None was ever
measured, and they have been the binding constraint on the college
board all season.

WHAT SURVIVAL IS:

    claimed  = mean(p_model - p_market)   what the model said it had
    landed   = win rate - mean(p_market)  what the close was short by
    survival = landed / claimed

MEASURED, CFB, 2,729 quoted games: claimed +12.53%, landed -0.06%,
survival -0%, 95% on landed [-1.75%, +1.56%]. Every band spans zero,
including the 1,680 games where the model claimed sixteen points. The
model's disagreement with the close carries no information at all.

THE TRAP THIS FILE EXISTS TO KEEP OUT. A measurement that reads
"survival is 0%" invites the edit "so set HAIRCUT to 1.0" — and that
would be fitting a constant to a number whose interval spans zero. It
also would not matter: `gamebets` already shrinks the claim toward the
market upstream (`engine_raw_prob` is the pre-shrink one), so the tier
haircut operates on an edge that is already ~0. The tests below pin
the ARITHMETIC and the HONESTY — that a band whose interval spans zero
says so — and deliberately pin no threshold, because there is no
measured threshold to pin.

Run directly:
`python3 tests/test_what_the_models_claimed_edge_actually_lands.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import haircut as H                              # noqa: E402


def _row(home_ml, away_ml, raw_home, home_won):
    return {"season": 2025, "home": "UGA", "away": "BAMA",
            "home_ml": home_ml, "away_ml": away_ml,
            "raw_home": raw_home, "home_won": home_won}


# --- the arithmetic ----------------------------------------------------
def test_survival_is_landed_over_claimed():
    """A model that claimed ten points and delivered five survived 50%."""
    # market 50%, model says 60%, and the side wins 55% of the time.
    sample = [(0.10, 0.50, True)] * 55 + [(0.10, 0.50, False)] * 45
    claimed, landed, surv = H._survival(sample)
    assert abs(claimed - 0.10) < 1e-9, claimed
    assert abs(landed - 0.05) < 1e-9, landed
    assert abs(surv - 0.5) < 1e-9, surv


def test_a_claim_that_lands_nothing_survives_nothing():
    """THE MEASURED SHAPE. The side wins exactly as often as the market
    said, so the model's extra ten points were worth zero."""
    sample = [(0.10, 0.50, True)] * 50 + [(0.10, 0.50, False)] * 50
    _c, landed, surv = H._survival(sample)
    assert abs(landed) < 1e-9, landed
    assert abs(surv) < 1e-9, surv


def test_a_claim_that_loses_money_survives_negatively():
    """Not merely noise — actively wrong. No haircut short of refusing
    the bet is enough, and the report must be able to say so."""
    sample = [(0.10, 0.50, True)] * 40 + [(0.10, 0.50, False)] * 60
    _c, landed, surv = H._survival(sample)
    assert landed < 0 and surv < 0, (landed, surv)


def test_no_claim_means_no_ratio_rather_than_a_division_by_zero():
    assert H._survival([])[2] is None
    assert H._survival([(0.0, 0.5, True)] * 10)[2] is None


# --- the side the model liked ------------------------------------------
def test_the_side_taken_is_the_models_not_the_favourites():
    """`gamerank.measure_raw_bar` next door takes the market's
    favourite, because it asks about the market's number. This asks
    about the MODEL's disagreement, so it takes whichever side the model
    rates furthest above the close — the side `evaluate_play` prices."""
    # Market has home a big favourite (-300 / +250); the model likes the
    # DOG, so the dog is the row.
    got = H.claims([_row(-300, 250, 0.60, False)], "cfb")
    assert len(got) == 1
    claim, mkt, won = got[0]
    assert claim > 0, got
    assert mkt < 0.5, "it priced the favourite's side"
    assert won is True, "the away side won and the row did not say so"


def test_every_game_contributes_exactly_one_side():
    """One match is one independent row; taking both sides would double
    the sample and halve every interval for free."""
    rows = [_row(-150, 130, 0.70, True), _row(120, -140, 0.30, False)]
    assert len(H.claims(rows, "cfb")) == 2


def test_an_unreadable_price_is_dropped_rather_than_guessed():
    rows = [_row(None, 130, 0.70, True), _row(-150, 130, 0.70, True)]
    assert len(H.claims(rows, "cfb")) == 1


def test_the_claim_is_calibrated_the_way_the_pipeline_calibrates_it():
    """`cfb.pipeline.evaluate_play` applies `calibrate.calibrated` before
    taking the edge, so measuring the uncalibrated claim would be
    measuring a number the board never uses.

    (On the shipped store this is a no-op for moneylines — there is no
    `cfb:moneyline` entry — which is WHY the call has to be here rather
    than assumed away: the day one is fitted, this follows it.)"""
    import inspect
    src = inspect.getsource(H.claims)
    assert "calibrated(" in src, "the raw claim is measured, not the board's"


# --- and the report is honest about noise ------------------------------
def test_a_band_whose_interval_spans_zero_says_so():
    """The whole point. A survival figure resting on a landed edge that
    could be zero has not measured a haircut, and printing the number
    without the caveat is how it ends up pasted into a constant."""
    b = H.Band(lo=0.02, hi=0.04, n=200, claimed=0.03, landed=0.001,
               survival=0.03, ci=(-0.02, 0.02))
    assert b.meaningless
    b.ci = (0.01, 0.03)
    assert not b.meaningless


def test_a_band_with_no_interval_is_not_treated_as_significant():
    assert H.Band(lo=0, hi=1, n=5, ci=None).meaningless


def test_too_few_rows_declines_to_bootstrap_rather_than_inventing_one():
    import random
    assert H._ci([(0.1, 0.5, True)] * 29, random.Random(1)) is None
    assert H._ci([(0.1, 0.5, True)] * 30, random.Random(1)) is not None


def test_the_report_prints_the_shipped_haircuts_beside_the_measurement():
    """A measurement nobody can compare to the setting it judges is a
    number in a log. The report states each tier's haircut AS the
    survival it assumes, so the two are in the same units."""
    r = H.Haircut(sport="cfb", games=2729, liked=2729, claimed=0.1253,
                  landed=-0.0006, survival=-0.005, ci=(-0.0175, 0.0156),
                  bands=[H.Band(0.02, 0.04, 241, 0.0293, -0.0036, -0.12,
                                (-0.03, 0.03))])
    txt = "\n".join(H.lines(r))
    assert "survival" in txt and "haircut this implies" in txt, txt
    assert "SPANS ZERO" in txt, "an interval over zero is printed as a finding"
    assert "assumes survival 65%" in txt, "the 35% haircut is not stated"
    assert "assumes survival 50%" in txt, "the marquee haircut is not stated"


def test_a_sport_without_a_raw_claim_says_so_rather_than_returning_zeros():
    """Baseball and the hoops walks keep no raw model claim, and a
    report of 0.0% survival for them would be a measurement nobody
    made."""
    r = H.measure(None, "mlb")
    assert r.note and "raw claim" in r.note, r
    assert r.survival is None
    assert "raw claim" in "\n".join(H.lines(r))


def test_the_headline_ignores_claims_too_small_to_bet():
    """A ratio over claims the board would never act on drags the
    headline around without changing any decision — and the smallest
    band is where the denominator is tiny enough to make the quotient
    meaningless (it read +519% on the real data)."""
    assert H.HEADLINE_MIN_CLAIM >= 0.02, H.HEADLINE_MIN_CLAIM
    import inspect
    src = inspect.getsource(H.measure)
    assert "HEADLINE_MIN_CLAIM" in src, "the headline is over every claim"


def test_nothing_here_fetches_or_writes():
    """A measurement that mutates the store it measures is a measurement
    that cannot be repeated."""
    import re
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "haircut.py"),
        encoding="utf-8").read()
    src = re.sub(r"(?s)([\"']{3}).*?\1", " ", src)
    src = re.sub(r"(?m)#.*$", " ", src)
    for banned in ("requests", "urlopen", "INSERT", "UPDATE", "write_text",
                   "--save"):
        assert banned not in src, banned


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
