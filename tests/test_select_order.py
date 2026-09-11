"""If not the claimed edge, then what — and is the replacement better?

Ethan, 2026-09-06, after `stakecheck --info` returned model 0.589,
market 0.589 and a claimed edge at 0.471 on 931 settled bets: "Rebuild
what it selects on" — keep staking, stop selecting on claimed edge, sort
and gate on the model's probability rank instead.

`engine.selectorder` is the backtest that has to run before that gate
moves. It orders the SAME settled pool three ways — by claimed edge, by
the model's probability, and by the market's implied probability as a
control — bets the top slice of each at the same prices, and counts the
money. The control is the load-bearing part: the information test put
the model and the market at the same AUC, so if the two slices are the
same bets then "sort by probability" is "sort by the shortest price",
which this repo has already paid to learn about once.

Run directly: `python3 tests/test_select_order.py`
"""

import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import selectorder


def _bet(hit_prob, odds, won, stake=1.0):
    return {"sport": "mlb", "market": "hits", "hit_prob": hit_prob,
            "odds": odds, "stake_units": stake,
            "status": "won" if won else "lost"}


def _price_near(p, rng):
    """A price whose implied probability is p plus a little vig and noise.

    Prices in the journal track the model loosely — that is the whole
    finding — so a synthetic pool where every row is -110 would make the
    market ordering a constant and the edge ordering a shifted copy of
    the probability ordering. Neither is the real shape.
    """
    imp = min(0.92, max(0.08, p + 0.02 + rng.uniform(-0.14, 0.14)))
    return int(round(-100 * imp / (1 - imp))) if imp >= 0.5 \
        else int(round(100 * (1 - imp) / imp))


def _pool_prob_ranks(n, seed, model_noise=0.12, backwards=1.0):
    """Bets shaped like what the information test actually measured.

    The market is efficient — its implied probability is the truth plus
    a couple of points of vig — and the model's number is the truth plus
    an error. The claimed edge is then almost entirely that error, and
    the error is INVERTED: a bet the model overstates is a bet that
    loses more often than the truth says. That is not an invention for
    the sake of a passing test. `stakecheck --info` put the claimed
    edge's AUC at 0.471 on 931 settled bets — below a coin flip, which
    means exactly this: bets we said were better won less often.

    Under that shape ordering by the raw probability still picks up the
    truth underneath the error, while ordering by the claimed edge picks
    the error alone and therefore picks losers.
    """
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        truth = rng.uniform(0.30, 0.80)
        err = rng.gauss(0, model_noise)
        claimed = min(0.95, max(0.05, truth + err))
        implied = min(0.93, max(0.07, truth + 0.025))
        odds = int(round(-100 * implied / (1 - implied))) if implied >= 0.5 \
            else int(round(100 * (1 - implied) / implied))
        lands = min(0.95, max(0.05, truth - backwards * err))
        out.append(_bet(claimed, odds, rng.random() < lands))
    return out


def _pool_edge_ranks(n, seed):
    """Bets where the claimed edge sorts the winners and the raw
    probability is unrelated to whether they landed."""
    from engine.odds import american_to_prob
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        p = rng.uniform(0.30, 0.80)
        odds = _price_near(p, rng)
        edge = p - american_to_prob(odds)
        out.append(_bet(p, odds, rng.random() < 0.5 + 3.0 * edge))
    return out


def test_a_pool_under_the_floor_is_refused_rather_than_reported():
    got = selectorder.compare(_pool_prob_ranks(40, 11))
    assert got["enough"] is False, got
    assert got["orderings"] == {}, got
    assert got["all"] is None, got
    assert str(selectorder.MIN_N) in selectorder.reading(got), got


def test_every_ordering_bets_the_same_count_out_of_the_same_pool():
    """The comparison is only a selection comparison if the three rules
    are handed identical rows and bet identically many of them."""
    got = selectorder.compare(_pool_prob_ranks(400, 12), reps=200)
    sizes = {o: got["orderings"][o]["bets"] for o in selectorder.ORDERINGS}
    assert len(set(sizes.values())) == 1, sizes
    assert sizes["edge"] == 100, sizes            # a quarter of 400
    assert got["all"]["bets"] == 400, got["all"]


def test_a_row_with_no_probability_or_no_price_never_reaches_an_ordering():
    rows = _pool_prob_ranks(200, 13)
    rows.append(_bet(None, -110, True))
    rows.append(_bet(0.6, None, True))
    rows.append({"sport": "mlb", "market": "hits", "hit_prob": 0.6,
                 "odds": -110, "stake_units": 1.0, "status": "push"})
    assert len(selectorder.usable(rows)) == 200, len(selectorder.usable(rows))


def test_probability_ranking_that_wins_is_measured_as_winning():
    got = selectorder.compare(_pool_prob_ranks(1000, 14), reps=400)
    d = got["diff"]["prob-edge"]
    assert d["point"] > 0, d
    assert d["lo"] > 0, d
    assert "probability-ranking beat edge-ranking" in selectorder.reading(got)


def test_edge_ranking_that_wins_is_measured_as_winning():
    """The same instrument has to be able to return the other answer, or
    it is not measuring anything — it is agreeing with whoever built it."""
    got = selectorder.compare(_pool_edge_ranks(600, 15), reps=400)
    d = got["diff"]["prob-edge"]
    assert d["point"] < 0, d
    assert d["hi"] < 0, d
    assert "LOST to edge-ranking" in selectorder.reading(got)


def test_when_the_probability_slice_is_the_price_slice_the_reading_says_so():
    """THE FINDING THIS TOOL EXISTS TO CATCH. A pool where the price is a
    clean monotone function of the model's number — which is what an
    information test reading model 0.589 against market 0.589 describes —
    makes the two orderings pick the same bets. The reading has to name
    that before it reports any ROI difference, because a ROI difference
    between two identical slices is zero by construction and would read
    as 'no measured difference' rather than as 'these are the same rule'.
    """
    from engine.odds import american_to_prob
    rng = random.Random(16)
    rows = []
    for _ in range(400):
        p = rng.uniform(0.30, 0.80)
        imp = p - 0.03                             # the vig, and nothing else
        odds = int(round(-100 * imp / (1 - imp))) if imp >= 0.5 \
            else int(round(100 * (1 - imp) / imp))
        rows.append(_bet(p, odds, rng.random() < p))
    got = selectorder.compare(rows, reps=200)
    assert got["overlap"]["prob|market"] >= selectorder.PROXY_OVERLAP, got
    say = selectorder.reading(got)
    assert "IS ordering by price" in say, say
    assert "price bar" in say, say
    # And the control is doing its job: a market ordering this close to
    # the model's cannot also be far from it on the same rows.
    devig = [american_to_prob(r["odds"]) for r in rows]
    assert max(devig) > min(devig), "the control must vary or it sorts nothing"


def test_two_orderings_that_pick_different_bets_are_not_called_the_same():
    got = selectorder.compare(_pool_edge_ranks(400, 17), reps=200)
    assert got["overlap"]["prob|edge"] < selectorder.PROXY_OVERLAP, got
    assert "IS ordering by price" not in selectorder.reading(got)


def test_the_flat_score_ignores_the_size_the_bet_was_actually_placed_at():
    """Selection is what is being compared, so the default has to strip
    the staking rule out. `as_placed` answers the other question."""
    rows = _pool_prob_ranks(400, 18)
    for i, r in enumerate(rows):
        r["stake_units"] = 4.0 if i % 2 else 0.5
    flat = selectorder.compare(rows, reps=100, stakes="flat")
    placed = selectorder.compare(rows, reps=100, stakes="as_placed")
    assert flat["orderings"]["prob"]["staked"] == 100.0, flat
    assert placed["orderings"]["prob"]["staked"] != 100.0, placed
    assert flat["orderings"]["prob"]["bets"] == \
        placed["orderings"]["prob"]["bets"]


def test_a_zeroed_stake_is_no_bet_when_the_real_sizes_are_used():
    """`probation.unstake` zeroes a size rather than deleting the row. At
    the placed sizes those rows staked nothing and won nothing, and
    counting them as bets would dilute every hit rate here."""
    rows = _pool_prob_ranks(400, 19)
    for r in rows[:200]:
        r["stake_units"] = 0.0
    placed = selectorder.compare(rows, reps=100, stakes="as_placed")
    flat = selectorder.compare(rows, reps=100, stakes="flat")
    assert placed["all"]["bets"] == 200, placed["all"]
    assert flat["all"]["bets"] == 400, flat["all"]


def test_ties_break_the_same_way_for_every_ordering():
    """A pool of identical prices and probabilities has no ordering at
    all. Every rule must then bet the same rows, or the tiebreak itself
    would show up as a selection difference nobody chose."""
    rows = [_bet(0.55, -110, i % 3 == 0) for i in range(200)]
    got = selectorder.compare(rows, reps=50)
    rois = {got["orderings"][o]["roi"] for o in selectorder.ORDERINGS}
    assert len(rois) == 1, got["orderings"]
    for k in ("prob|edge", "prob|market", "edge|market"):
        assert got["overlap"][k] == 1.0, got["overlap"]
    assert got["diff"]["prob-edge"]["point"] == 0.0, got["diff"]


def test_a_cut_that_loses_to_betting_everything_is_told_it_loses():
    """SORT AND GATE ARE TWO DECISIONS. Ethan's instruction was both, and
    a cut can destroy money on a pool the same sort orders perfectly.

    The pool below has a model that is exactly right and a book that
    charges its hold where the money goes: a point of vig at the long
    end and twenty-two at the short one. That is the shape behind
    `likely.HEAVIEST_PRICE` — "at -250 a bet needs 71.4% to break even" —
    and under it the top slice by probability is the most heavily taxed
    quarter of the board, so cutting to it loses to betting the lot even
    though every row in it is more likely to land than the rows below.
    """
    rng = random.Random(22)
    rows = []
    lo, hi = 0.25, 0.70
    for _ in range(2000):
        truth = rng.uniform(lo, hi)
        vig = 0.01 + 0.21 * ((truth - lo) / (hi - lo)) ** 3
        implied = min(0.94, truth + vig)
        odds = int(round(-100 * implied / (1 - implied))) if implied >= 0.5 \
            else int(round(100 * (1 - implied) / implied))
        rows.append(_bet(truth, odds, rng.random() < truth))
    got = selectorder.compare(rows, reps=300)
    assert got["orderings"]["prob"]["hit"] > got["all"]["hit"], got
    d = got["diff"]["prob-all"]
    assert d["hi"] < 0, d
    say = selectorder.cut_reading(got)
    assert "the CUT itself loses money" in say, say


def test_the_do_not_cut_arm_bets_every_row_whatever_the_share_says():
    got = selectorder.compare(_pool_prob_ranks(400, 22), reps=100,
                              top_share=0.10)
    assert got["all"]["bets"] == 400, got["all"]
    assert got["orderings"]["prob"]["bets"] == 40, got["orderings"]


def test_the_report_prints_and_writes_nothing():
    import io
    import contextlib
    import stakecheck
    rows = _pool_prob_ranks(300, 20)
    for r in rows:
        r.setdefault("date", "2026-09-01")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stakecheck.select_report(rows)
    out = buf.getvalue()
    assert "WHICH ORDERING" in out, out
    assert "read-only; nothing was written" in out, out
    # The caveat is not optional furniture: every number in the table is
    # conditional on the edge gate having already run.
    assert "bets the edge gate refused" in out, out
    # Both halves of the instruction get a sentence, not just the sort.
    assert "the cut" in out, out


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
