"""The lineup sim is SEEDED, so "faster" has to mean bit-identical.

`simulate_lineup`'s own docstring says why the seed is there: "a page whose
numbers jitter every refresh reads as noise even when the model is stable,
and nobody can tell a real move from the sampler." That makes speed work on
this function a different kind of job from speed work elsewhere — the output
is not merely supposed to be close, it is supposed to be the same numbers.

So this file pins the sameness rather than the speed. The digest below was
taken from the sim BEFORE the trial loop was reworked (hoisting the per-leg
`.1f` keys and the canonical pair keys out of it, unrolling the per-trial
rate-table rebuild, and wrapping the batting order by hand instead of by
modulo), and it did not move. If it moves now, something changed the draws
or the tallies, and the board moved with it.

WHAT TO DO IF THIS FAILS. Two very different causes, and the other tests in
this file tell them apart. If only the digest fails, the RNG sequence
shifted — a draw added, removed or reordered. If the behaviour tests below
fail too, the tallying changed. A Python release that altered
`random.gauss` would show up here as well, and that is also worth knowing:
it would move every published number on the board.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import gamesim as G                              # noqa: E402
from engine.mlb.models import HITS, TOTAL_BASES, HOME_RUNS       # noqa: E402


def _lineup(n=9):
    """Nine hitters on a descending-quality curve, built the engine's way."""
    out = []
    for i in range(n):
        r = G.rates_from_means(0.98 - 0.04 * i, 1.55 - 0.07 * i,
                               0.17 - 0.012 * i, pa=4.6 - 0.1 * i)
        out.append(G.BatterRates(
            out=r.out, bb=r.bb, single=r.single, double=r.double,
            triple=r.triple, hr=r.hr, name=f"Hitter {i + 1}", spot=i + 1,
            consistent=r.consistent))
    return out


def _legs(rates, k=6):
    out = []
    for b in rates[:k]:
        out.append((b.name, HITS, 0.5))
        out.append((b.name, TOTAL_BASES, 1.5))
        out.append((b.name, HOME_RUNS, 0.5))
    return out


def _digest(sim) -> str:
    import hashlib
    import json
    blob = {
        "trials": sim.trials,
        "names": list(sim.names),
        "pa_mean": {k: repr(v) for k, v in sorted(sim.pa_mean.items())},
        "mean": {k: {m: repr(x) for m, x in sorted(v.items())}
                 for k, v in sorted(sim.mean.items())},
        "se": {k: {m: repr(x) for m, x in sorted(v.items())}
               for k, v in sorted(sim.se.items())},
        "over": {k: {m: dict(sorted(d.items())) for m, d in sorted(v.items())}
                 for k, v in sorted(sim.over.items())},
        "both": {repr(k): v for k, v in sorted(sim.both.items(), key=repr)},
    }
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True).encode()).hexdigest()[:32]


#: Taken from the sim as it stood at commit 66db1bf — that is, from the code
#: BEFORE the trial loop was reworked, run against this file's own lineup and
#: legs. 20,000 trials, seed 7. The rework then reproduced it exactly, which
#: is the only reason it shipped.
GOLDEN = "f04c2d50771a21568751634a3b13f011"


def test_the_numbers_did_not_move():
    rates = _lineup()
    sim = G.simulate_lineup(rates, _legs(rates), trials=20000)
    got = _digest(sim)
    assert got == GOLDEN, (
        f"the seeded sim now produces {got}, not {GOLDEN} — every number on "
        f"the MLB board moved. See this file's docstring.")


def test_the_same_seed_twice_is_the_same_run():
    """The property the digest above depends on, stated on its own so a
    failure here is not mistaken for a golden-value drift."""
    rates = _lineup()
    legs = _legs(rates)
    a = G.simulate_lineup(rates, legs, trials=2000)
    b = G.simulate_lineup(rates, legs, trials=2000)
    assert _digest(a) == _digest(b)


def test_a_different_seed_is_a_different_run():
    """Guards the opposite mistake: a sim that ignored its draws entirely
    would satisfy every other test in this file."""
    rates = _lineup()
    legs = _legs(rates)
    a = G.simulate_lineup(rates, legs, trials=2000, seed=7)
    b = G.simulate_lineup(rates, legs, trials=2000, seed=8)
    assert _digest(a) != _digest(b)


# --- what the flat-count rewrite had to preserve ----------------------------
def test_the_same_leg_asked_for_twice_is_counted_twice():
    """THE SUBTLE ONE. The loop used to key straight into
    `over[name][market][".1f"]` and `both[pair]`, so a board carrying the
    same (player, market, line) twice ADDED the two counts together. Counting
    into flat per-leg lists and folding them up afterwards only reproduces
    that if the fold accumulates rather than assigns."""
    rates = _lineup()
    one = [(rates[0].name, HITS, 0.5)]
    twice = [(rates[0].name, HITS, 0.5), (rates[0].name, HITS, 0.5)]
    a = G.simulate_lineup(rates, one, trials=3000)
    b = G.simulate_lineup(rates, twice, trials=3000)
    ka = a.over[rates[0].name][HITS]["0.5"]
    kb = b.over[rates[0].name][HITS]["0.5"]
    assert ka > 0, "the single leg never cleared, so this proves nothing"
    assert kb == 2 * ka, f"duplicate leg gave {kb}, not {2 * ka}"


def test_a_market_the_sim_does_not_tally_scores_zero():
    """`got.get(market, 0)` was the old spelling. A market the sim has no
    counter for must compare as 0 — never crash, and never clear a line."""
    rates = _lineup()
    sim = G.simulate_lineup(
        rates, [(rates[0].name, "stolen_bases", 0.5)], trials=500)
    assert sim.over[rates[0].name].get("stolen_bases") in (None, {})
    assert sim.both == {}


def test_pair_keys_are_canonical_and_order_free():
    """Pairs are precomputed now, so the canonical ordering has to come out
    of the precompute exactly as `_pair_key` produced it in the loop."""
    rates = _lineup()
    legs = _legs(rates, k=3)
    sim = G.simulate_lineup(rates, legs, trials=2000)
    assert sim.both, "no joint counts at all"
    for (ka, kb) in sim.both:
        assert ka <= kb, f"pair key not canonical: {(ka, kb)}"
    for a in legs:
        for b in legs:
            if a is b:
                continue
            assert G._pair_key(a, b) == G._pair_key(b, a)


def test_the_order_keeps_batting_across_innings():
    """`spot % n` became a hand-wrapped counter. The thing that would break
    if it were reset per inning: the leadoff man would bat every inning and
    the bottom of the order would barely bat at all."""
    rates = _lineup()
    sim = G.simulate_lineup(rates, [], trials=4000, env_sd=0.0)
    pas = [sim.pa_mean[b.name] for b in rates]
    assert min(pas) > 0, "somebody never batted"
    # Nine hitters, ~38 PA a game: the spread top-to-bottom is under one PA.
    assert max(pas) - min(pas) < 1.0, f"lopsided plate appearances: {pas}"
    # And it is a DECLINING order, not a flat one.
    assert pas[0] > pas[-1]


def test_no_legs_still_produces_the_marginals():
    """`calibrate` runs the sim with `legs=[]` six times per lineup, so the
    empty-legs path is most of the sim's actual work."""
    rates = _lineup()
    sim = G.simulate_lineup(rates, [], trials=1000)
    assert sim.over == {b.name: {} for b in rates}
    assert sim.both == {}
    for b in rates:
        assert sim.mean[b.name][TOTAL_BASES] > 0
        assert sim.se[b.name][HOME_RUNS] >= 0


def test_an_empty_lineup_is_still_handled():
    sim = G.simulate_lineup([], [(("nobody"), HITS, 0.5)], trials=10)
    assert sim.trials == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
