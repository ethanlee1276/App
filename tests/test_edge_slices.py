"""Is the claimed edge noise everywhere, or only on average?

Ethan, 2026-09-06: "lets do the edge test one next" — the line his
settle pass prints in every block, `claimed-edge AUC 0.463 [0.414,
0.512] -> edge_is_noise` on 562 settled bets.

That is one number over six sports and a dozen markets, and a pooled
coin flip has three different explanations with three different
answers: every slice is a coin flip, one slice carries the signal and
the rest dilute it, or two slices cancel. `engine.edgeslices` cuts it
and puts every tested slice into one Benjamini-Hochberg family, so
finding "the good one" in twenty pieces of a null is not available.

Run directly: `python3 tests/test_edge_slices.py`
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

from engine import edgeslices


def _bet(sport, market, hit_prob, odds, won):
    return {"sport": sport, "market": market, "hit_prob": hit_prob,
            "odds": odds, "status": "won" if won else "lost"}


def _noise(sport, market, n, seed):
    """Bets whose claimed edge says nothing about the outcome."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        p = rng.uniform(0.35, 0.75)
        out.append(_bet(sport, market, p, -110, rng.random() < 0.5))
    return out


def _signal(sport, market, n, seed):
    """Bets where more claimed edge really does win more often."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        p = rng.uniform(0.35, 0.75)
        edge = p - 0.524                      # implied at -110
        out.append(_bet(sport, market, p, -110,
                        rng.random() < 0.5 + 2.2 * edge))
    return out


def test_a_pure_coin_flip_survives_nothing():
    rows = (_noise("mlb", "hits", 200, 1) + _noise("nfl", "anytime_td", 200, 2)
            + _noise("cfb", "total", 200, 3))
    got = edgeslices.by_slice(rows)
    assert got["n"] == 600
    assert len(got["tested"]) == 6, [t["value"] for t in got["tested"]]
    assert got["survivors"] == []
    assert "noise in every slice" in edgeslices.reading(got)


def test_one_real_slice_is_found_among_the_coin_flips():
    rows = (_signal("mlb", "hits", 400, 11) + _noise("nfl", "anytime_td", 200, 12)
            + _noise("cfb", "total", 200, 13))
    got = edgeslices.by_slice(rows)
    found = {(s["key"], s["value"]) for s in got["survivors"]}
    assert ("sport", "mlb") in found and ("market", "hits") in found, got["tested"]
    assert ("sport", "nfl") not in found and ("sport", "cfb") not in found
    hit = [t for t in got["tested"] if t["value"] == "hits"][0]
    assert hit["auc_edge"] > 0.5 and hit["auc_edge_lo"] is not None
    assert "survive" in edgeslices.reading(got)


def test_a_thin_slice_is_not_tested_and_does_not_enlarge_the_family():
    """`losspatterns._bh`: shrinking m after peeking is how false
    discovery control dies — and inflating it with slices nobody asked
    about is how a real finding gets buried."""
    rows = _noise("mlb", "hits", 200, 21) + _noise("wnba", "pts", 10, 22)
    got = edgeslices.by_slice(rows)
    tested = {(t["key"], t["value"]) for t in got["tested"]}
    assert ("sport", "wnba") not in tested and ("market", "pts") not in tested
    assert {"sport": "wnba", "market": "pts"}.items() >= {}.items()
    thin = {(t["key"], t["value"]) for t in got["thin"]}
    assert ("sport", "wnba") in thin and ("market", "pts") in thin
    assert len(got["tested"]) == 2, "only the two slices that cleared MIN_N"


def test_the_family_is_every_slice_tested_across_both_cuts():
    rows = (_noise("mlb", "hits", 120, 31) + _noise("mlb", "total_bases", 120, 32)
            + _noise("nfl", "anytime_td", 120, 33))
    got = edgeslices.by_slice(rows)
    # 2 sports + 3 markets, all above MIN_N.
    assert len(got["tested"]) == 5
    assert all("q" in t and "survives" in t for t in got["tested"])
    # A BH q is never below its own p. The tolerance is `_bh`'s rounding
    # to four decimals, not slack in the claim.
    for t in got["tested"]:
        assert t["q"] >= t["p"] - 1e-4, (t["value"], t["p"], t["q"])


def test_the_p_value_is_the_null_variance_not_a_bootstrap():
    """AUC has a known variance when there is no signal, so a slice's
    p needs no resampling — and cannot inherit a bootstrap's quirks."""
    assert abs(edgeslices.p_two_sided(0.5, 100, 100) - 1.0) < 1e-9
    assert edgeslices.p_two_sided(0.75, 100, 100) < 0.001
    assert edgeslices.p_two_sided(0.25, 100, 100) < 0.001, "two-sided"
    assert edgeslices.p_two_sided(0.6, 400, 400) < edgeslices.p_two_sided(0.6, 40, 40)
    assert edgeslices.p_two_sided(0.6, 0, 10) is None


def test_an_all_winners_slice_is_reported_rather_than_scored():
    rows = _noise("mlb", "hits", 200, 41)
    rows += [_bet("nba", "pts", 0.6, -110, True) for _ in range(80)]
    got = edgeslices.by_slice(rows)
    tested = {(t["key"], t["value"]) for t in got["tested"]}
    assert ("sport", "nba") not in tested
    note = [t for t in got["thin"] if t["value"] == "nba"][0]
    assert "all winners" in note.get("note", "")


def test_nothing_to_cut_says_so():
    got = edgeslices.by_slice(_noise("mlb", "hits", 20, 51))
    assert got["tested"] == [] and "nothing to cut" in edgeslices.reading(got)



def _price_from(prob, jitter, rng):
    """A book price sitting near the model's own number, so the EDGE is
    noise while the model's probability still ranks outcomes."""
    imp = min(0.92, max(0.08, prob + rng.uniform(-jitter, jitter)))
    return (int(round(-100 * imp / (1 - imp))) if imp >= 0.5
            else int(round(100 * (1 - imp) / imp)))


def test_a_slice_where_the_model_ranks_and_the_edge_does_not():
    """THE ACTUAL FINDING'S SHAPE, and the case constant odds cannot
    express: with every bet at -110 the claimed edge is just the model's
    probability shifted, so the two AUCs are the same number and a test
    built that way cannot tell them apart. Here the price tracks the
    model, which is what docs/THE_INFORMATION_TEST.md measured — model
    0.570, edge 0.479 — and the slice must read the same way."""
    rng = random.Random(7)
    rows = []
    for _ in range(500):
        prob = rng.uniform(0.30, 0.80)
        rows.append({"sport": "mlb", "market": "hits", "hit_prob": prob,
                     "odds": _price_from(prob, 0.04, rng),
                     "status": "won" if rng.random() < prob else "lost"})
    m = edgeslices._measure(rows)
    assert m["auc_model"] > 0.60, m["auc_model"]
    assert abs(m["auc_edge"] - 0.5) < 0.05, m["auc_edge"]
    assert m["auc_model"] - m["auc_edge"] > 0.09, m
    got = edgeslices.by_slice(rows)
    assert got["survivors"] == [], "a price-reader has nothing to select on"


def test_a_lucky_slice_does_not_survive_the_family():
    """WHAT THE FDR IS FOR. One slice lands at raw p = 0.019 — under any
    unadjusted 0.05 — and it must NOT be reported as a finding once the
    other slices tested alongside it are counted. Testing ten slices and
    keeping the best is how a coin flip becomes a strategy."""
    rng = random.Random(901)
    lucky = []
    for _ in range(200):
        prob = rng.uniform(0.35, 0.75)
        lucky.append({"sport": "lucky", "market": "luckymkt", "hit_prob": prob,
                      "odds": -110,
                      "status": "won" if rng.random() < 0.5 + 0.9 * (prob - 0.524)
                      else "lost"})
    solo = edgeslices._measure(lucky)
    assert 0.006 < solo["p"] < 0.045, solo["p"]      # would clear a raw 0.05
    rows = list(lucky)
    for k in range(4):
        rows += _noise(f"s{k}", f"m{k}", 200, 500 + k)
    got = edgeslices.by_slice(rows)
    assert len(got["tested"]) == 10, [t["value"] for t in got["tested"]]
    hit = [t for t in got["tested"] if t["value"] == "lucky"][0]
    assert hit["p"] < 0.05 and hit["survives"] is False, hit
    assert hit["q"] > 0.05, hit
    assert got["survivors"] == []

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
