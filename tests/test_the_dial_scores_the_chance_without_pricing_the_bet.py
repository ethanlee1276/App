"""The recency dial's walk computes only the chance it scores
(engine/logwalk.walk_pairs; engine/betting.prop_p_over, choose_side,
shop_one; engine/formfit.fit).

The dial scores each of its 21 settings on its own walk over a market's
whole history, and the walk priced every game's whole bet — the line shop,
the grade, the loss-pattern veto, the stake — to keep one number of it: the
model's raw chance on the over, which the dial's Brier score reads. On the
box the NFL's dial still carried its 25 August fit on 8 November; one big
market outgrew a run. What these hold:

  * the fast walk's pairs are the full walk's, in the same order, to the
    bit: every football market shape (a normal tail, whole-number catches,
    Poisson interceptions with the opponent rated), both sides, pushes left
    out, the clamp at the ends, the calibration on and off;
  * the dial fitted through it is the dial fitted through the full walk,
    curve and all, so a grid the box saved part-way still resumes;
  * it never prices a bet (no `evaluate_prop`), projects each game once,
    and shops the one proxy quote once per line; baseball and basketball
    still walk their own engines;
  * the evaluator's pieces it shares are the evaluator's: `pick_side` ends
    in `choose_side`, a one-quote shop is `pick_side`'s shop, and
    `evaluate_prop` prices its chance through `prop_p_over`.

Run directly: `python3 tests/test_the_dial_scores_the_chance_without_pricing_the_bet.py`
"""
import inspect
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import betting as BT                                      # noqa: E402
from engine import calibrate as cal                                   # noqa: E402
from engine import formfit as ff                                      # noqa: E402
from engine import logwalk                                            # noqa: E402
from engine.logwalk import Entries                                    # noqa: E402
from engine.models import SportsbookLine                              # noqa: E402
from engine.statmath import prob_over                                 # noqa: E402

TEAMS = ("BUF", "MIA", "NE", "NYJ")


def _entries(market, n_players=40, games=24, seed=11):
    """Players with whole-number games (so a whole-number proxy line can
    push), a few at the extremes (the clamp), and for interceptions the
    attempts, opponents and the defences' timeline the walk rates them on."""
    rnd = random.Random(seed)
    out = Entries()
    for p in range(n_players):
        if market == "receptions":
            mu = rnd.uniform(1.5, 8)
            vals = [max(0, round(rnd.gauss(mu, mu * 0.5))) for _ in range(games)]
        elif market == "pass_int":
            vals = [rnd.choice([0, 0, 0, 1, 1, 2]) for _ in range(games)]
        else:
            mu = rnd.uniform(15, 280)
            vals = [max(0, round(rnd.gauss(mu, mu * 0.45))) for _ in range(games)]
        if p % 13 == 0:
            vals = [0] * (games // 2) + [rnd.choice([0, 150])] * (games - games // 2)
        e = {"name": f"P{p}", "values": vals}
        if market == "pass_int":
            e["companion"] = [max(5, round(rnd.gauss(33, 6))) for _ in range(games)]
            e["opps"] = [rnd.choice(TEAMS) for _ in range(games)]
            e["seasons"] = [2024 + g // 17 for g in range(games)]
            e["dates"] = [f"{g % 17 + 1:03d}" for g in range(games)]
        out.append(e)
    out.aux = ({"allowed": [(2024 + g // 17, f"{g % 17 + 1:03d}", t, rnd.choice([0, 1, 2]))
                            for g in range(games) for t in TEAMS]}
               if market == "pass_int" else {})
    return out


CASES = (("nfl", "rec_yds"), ("nfl", "receptions"), ("nfl", "pass_yds"),
         ("nfl", "rush_yds"), ("nfl", "pass_int"), ("cfb", "pass_att"), ("cfb", "rush_att"))


def test_the_pairs_are_the_full_walks_to_the_bit():
    seen_under = seen_push = 0
    for sport, market in CASES:
        e = _entries(market)
        base = ff.base_for(sport)
        for r in (0.0, -1.0, -0.4, 0.7, 1.0):
            w = ff.family(base, r)
            with cal.disabled():
                slow = logwalk.walk(sport, e, market, form_weights=w)
                fast = logwalk.walk_pairs(sport, e, market, form_weights=w)
            assert fast == slow.pairs, (sport, market, r)
            seen_under += sum(1 for s in slow.settled if s.side == "UNDER")
            seen_push += sum(1 for s in slow.settled if s.over_hit is None)
        # The calibration switched on prices through the same entry point.
        w = ff.family(base, 0.3)
        assert logwalk.walk_pairs(sport, e, market, form_weights=w) == \
            logwalk.walk(sport, e, market, form_weights=w).pairs, (sport, market, "calibrated")
    assert seen_under and seen_push, "both sides and pushes were exercised"


def test_the_dial_fitted_through_it_is_the_full_walks_dial():
    e = _entries("rec_yds", n_players=30)
    fast = ff.fit(e, "rec_yds", sport="nfl")
    real = logwalk.walk_pairs
    logwalk.walk_pairs = lambda sport, en, market, min_history=None, form_weights=None, limit=30: \
        logwalk.walk(sport, en, market, min_history=min_history, form_weights=form_weights).pairs
    try:
        slow = ff.fit(e, "rec_yds", sport="nfl")
    finally:
        logwalk.walk_pairs = real
    assert (fast.r, fast.samples, fast.adopted, fast.curve) == (slow.r, slow.samples, slow.adopted, slow.curve)
    assert fast.brier_default == slow.brier_default and fast.brier_fitted == slow.brier_fitted
    # A grid saved part-way by the full walk resumes under the fast one: the
    # spec curve scores exactly as saved, so the saved settings are kept.
    ck = ff.GridCheckpoint("nfl", "rec_yds", path=Path(tempfile.mkdtemp()) / "partial.json")
    with cal.disabled():
        pairs = logwalk.walk("nfl", e, "rec_yds", form_weights=ff.family(ff.base_for("nfl"), 0.0)).pairs
    ck.put(0.0, ff._brier(pairs), len(pairs))
    ck.put(-1.0, slow.curve[-1.0], slow.samples)
    calls = []
    logwalk.walk_pairs = lambda *a, **k: calls.append(k["form_weights"]) or real(*a, **k)
    try:
        resumed = ff.fit(e, "rec_yds", sport="nfl", checkpoint=ck)
    finally:
        logwalk.walk_pairs = real
    assert len(calls) == len(ff.GRID) - 1, "the saved setting was kept, the spec curve scored again"
    assert resumed.curve == slow.curve and resumed.r == slow.r


def test_it_never_prices_a_bet_and_shops_once_a_line():
    e = _entries("rec_yds", n_players=10)
    n_games = sum(len(p["values"]) - 4 for p in e)
    counts = {"evaluate_prop": 0, "build_projection": 0, "shop_one": 0}
    real_eval, real_proj, real_shop = BT.evaluate_prop, logwalk.build_projection, BT.shop_one

    def counting(name, fn):
        def wrapped(*a, **k):
            counts[name] += 1
            return fn(*a, **k)
        return wrapped
    BT.evaluate_prop = logwalk.evaluate_prop = counting("evaluate_prop", real_eval)
    logwalk.build_projection = counting("build_projection", real_proj)
    BT.shop_one = counting("shop_one", real_shop)
    try:
        with cal.disabled():
            pairs = logwalk.walk_pairs("nfl", e, "rec_yds", form_weights=ff.family(ff.base_for("nfl"), 0.5))
    finally:
        BT.evaluate_prop = logwalk.evaluate_prop = real_eval
        logwalk.build_projection = real_proj
        BT.shop_one = real_shop
    lines = {logwalk._naive_line(p["values"][:i][::-1][:30][:8]) for p in e
             for i in range(4, len(p["values"]))}
    assert counts["evaluate_prop"] == 0, "no bet priced"
    assert counts["build_projection"] == n_games, "each game projected once"
    assert counts["shop_one"] == len(lines), "the proxy quote shopped once a line"
    assert pairs


def test_baseball_and_basketball_walk_their_own_engines():
    seen = []
    real = logwalk.walk

    class _Report:
        pairs = [(0.5, 1)]
    logwalk.walk = lambda sport, *a, **k: seen.append(sport) or _Report()
    try:
        for sport in ("mlb", "nba", "wnba"):
            assert logwalk.walk_pairs(sport, [], "hits", form_weights={"last1": 1.0}) == [(0.5, 1)]
    finally:
        logwalk.walk = real
    assert seen == ["mlb", "nba", "wnba"]


def test_the_evaluators_pieces_are_the_evaluators():
    # pick_side ends in choose_side, and a one-quote shop is pick_side's.
    src = inspect.getsource(BT.pick_side)
    assert src.count("return choose_side(over, None, p_over_at)") == 1
    assert src.count("return choose_side(over, under, p_over_at)") == 1
    assert "prop_p_over(prop, proj, line, sport)" in inspect.getsource(BT.evaluate_prop)
    for mean in (3.0, 30.0, 61.0, 140.0):
        p = (lambda x, m=mean: prob_over(x, m, 0.4 * m + 1))
        for quote in (SportsbookLine("proxy", 60.5, -110, -110), SportsbookLine("dk", 60.5, -125, 105),
                      SportsbookLine("fd", 1.5, 120, 0)):
            over, under = BT.shop_one([quote])
            assert BT.choose_side(over, under, p) == BT.pick_side([quote], p), (mean, quote)
    for field in ([], [SportsbookLine("dk", 60.5, -110, -110), SportsbookLine("fd", 60.5, -105, -115)]):
        try:
            BT.shop_one(field)
        except ValueError:
            continue
        raise AssertionError(f"a field of {len(field)} is pick_side's to shop")


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
