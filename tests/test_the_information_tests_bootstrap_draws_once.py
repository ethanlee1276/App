"""The information test's bootstraps give exactly what they gave, from one
run of resamples (stakecheck._resamples, _auc_groups, _auc_counts,
_boot_info, _boot_auc, _boot_auc_diff; engine/edgehistory.measure).

Profiled on a 20,000-bet journal, the record export spent 29 of its 38
seconds in the record page's information test: four bootstraps (the model's,
the market's and the edge's AUC, and the paired model-minus-market), 2,000
resamples each, every resample a fresh list of draws and a fresh sort. The
export runs every ten minutes on a game day. What these hold:

  * the resamples are `rng.randrange(n)`'s own draws, in order, for any n;
  * a resample's AUC read off its counts is the old `_auc` of the expanded
    resample, to the bit, ties and all;
  * `_boot_auc`, `_boot_auc_diff` and the one-run `_boot_info` give exactly
    the intervals the old per-bootstrap loops gave (copied here as the
    reference), small samples, heavy ties, one-sided ones and a NaN
    included;
  * `edgehistory.measure` takes its four intervals from one run.

Run directly: `python3 tests/test_the_information_tests_bootstrap_draws_once.py`
"""
import inspect
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stakecheck as S                                             # noqa: E402

SEED = 20260809


def _old_boot_auc(scores, labels, reps=2000, seed=SEED):
    """The bootstrap as it stood before 2026-11-07, verbatim."""
    rng = random.Random(seed)
    n = len(scores)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        a = S._auc([scores[i] for i in idx], [labels[i] for i in idx])
        if a is not None:
            out.append(a)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def _old_boot_auc_diff(a_scores, b_scores, labels, reps=2000, seed=SEED):
    rng = random.Random(seed)
    n = len(labels)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        ys = [labels[i] for i in idx]
        aa = S._auc([a_scores[i] for i in idx], ys)
        bb = S._auc([b_scores[i] for i in idx], ys)
        if aa is not None and bb is not None:
            out.append(aa - bb)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def _sample(n, seed, ties=True):
    rnd = random.Random(seed)
    y = [1 if rnd.random() < 0.52 else 0 for _ in range(n)]
    model = [round(rnd.uniform(0.3, 0.8), 2 if ties else 6) for _ in range(n)]
    market = [rnd.choice([0.4, 0.4545, 0.5, 0.5238, 0.5652, 0.6]) for _ in range(n)]
    edge = [m - k for m, k in zip(model, market)]
    return y, model, market, edge


def test_the_resamples_are_randranges_own_draws():
    for n in (1, 2, 3, 7, 8, 64, 1000, 1023, 1024, 1025):
        rng = random.Random(SEED)
        want = [[rng.randrange(n) for _ in range(n)] for _ in range(5)]
        got = [draws for _counts, draws in S._resamples(n, 5, SEED, keep_order=True)]
        assert got == want, n
        for (counts, _d), w in zip(S._resamples(n, 5, SEED), want):
            assert counts == [w.count(i) for i in range(n)], n


def test_a_resamples_auc_from_its_counts_is_the_old_auc_to_the_bit():
    for n, seed in ((40, 1), (301, 2), (1200, 3)):
        y, model, market, edge = _sample(n, seed)
        for scores in (model, market, edge):
            groups = S._auc_groups(scores)
            for counts, draws in S._resamples(n, 25, seed, keep_order=True):
                old = S._auc([scores[i] for i in draws], [y[i] for i in draws])
                assert S._auc_counts(groups, y, counts, n) == old


def test_the_intervals_are_exactly_the_old_ones():
    for n, seed, reps in ((40, 11, 400), (257, 12, 300), (900, 13, 200)):
        for ties in (True, False):
            y, model, market, edge = _sample(n, seed, ties)
            for scores in (model, market, edge):
                assert S._boot_auc(scores, y, reps=reps) == _old_boot_auc(scores, y, reps=reps)
            assert S._boot_auc_diff(model, market, y, reps=reps) == \
                _old_boot_auc_diff(model, market, y, reps=reps)
            singles, diffs = S._boot_info([model, market, edge], y, pairs=((0, 1),), reps=reps)
            assert singles == [_old_boot_auc(sc, y, reps=reps) for sc in (model, market, edge)]
            assert diffs == [_old_boot_auc_diff(model, market, y, reps=reps)]


def test_the_edges_of_the_old_behaviour_hold():
    one_sided = [1] * 30
    assert S._boot_auc([0.5] * 30, one_sided, reps=100) == (None, None) \
        == _old_boot_auc([0.5] * 30, one_sided, reps=100)
    tiny_y, tiny = [1, 0, 1], [0.6, 0.4, 0.6]
    assert S._boot_auc(tiny, tiny_y, reps=200) == _old_boot_auc(tiny, tiny_y, reps=200)
    nan_scores = [0.5, float("nan"), 0.6, 0.4, 0.55, 0.45] * 8
    nan_y = [1, 0, 1, 0, 0, 1] * 8
    assert S._auc_groups(nan_scores) is None
    assert S._boot_auc(nan_scores, nan_y, reps=150) == _old_boot_auc(nan_scores, nan_y, reps=150)
    assert S._boot_auc([], [], reps=10) == (None, None)


def test_the_record_pages_test_takes_its_four_intervals_from_one_run():
    from engine import edgehistory
    src = inspect.getsource(edgehistory.measure)
    assert "_boot_info(" in src and "_boot_auc(" not in src and "_boot_auc_diff(" not in src
    rnd = random.Random(5)
    rows = [{"status": rnd.choice(["won", "lost"]), "hit_prob": round(rnd.uniform(0.35, 0.75), 3),
             "odds": rnd.choice([-150, -120, -110, 100, 120, 150])} for _ in range(300)]
    m = edgehistory.measure(rows)
    from engine.odds import american_to_prob
    y = [1 if r["status"] == "won" else 0 for r in rows]
    model = [float(r["hit_prob"]) for r in rows]
    market = [american_to_prob(int(r["odds"])) for r in rows]
    edge = [a - b for a, b in zip(model, market)]
    assert (m["auc_model_lo"], m["auc_model_hi"]) == _old_boot_auc(model, y)
    assert (m["auc_market_lo"], m["auc_market_hi"]) == _old_boot_auc(market, y)
    assert (m["auc_edge_lo"], m["auc_edge_hi"]) == _old_boot_auc(edge, y)
    assert (m["diff_lo"], m["diff_hi"]) == _old_boot_auc_diff(model, market, y)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
