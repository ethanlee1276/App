"""The home-run engine, brought back to reality.

The receipts that ordered this fix: home-run overs said 14% and hit 11%
over 1,714 graded bets (q=0.003), the calibration fit ran to its 0.40
boundary and self-closed the market, and the sim-reconcile gate found
~40 players a night whose hits/total-bases/HR projections were not
possible baseball. Three defects, three fixes: a league prior when a
player has no career rate (shrinking toward his own window was not
shrinking), environment claims applied at half strength on the tail
market the long-shot board selection-biases hardest, and a coherence
pass that forces every batter's trio into the box the sim's inverter
defines.
"""

import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import gamesim as G
from engine.mlb import projection as P
from engine.mlb.models import MLBProp, MLBGame, MLBGameLog, HOME_RUNS
from engine.mlb.projection import (LEAGUE_HR_RATE, RARE_EVENT_ENV_CLAMP,
                                   RARE_EVENT_PRIOR_GAMES, _rare_event_rate,
                                   build_mlb_projection, reconcile_triple)
from engine.mlb.projection import MLB_WINDOW_WEIGHTS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the coherence box -------------------------------------------------------
def test_every_repaired_triple_is_baseball_the_sim_can_invert():
    """The box is the sim inverter's, verbatim: hr ≤ hits and
    hits + 3·hr ≤ tb ≤ 3·hits + hr. After the repair, rates_from_means
    must call EVERY trio consistent — including the adversarial shapes
    the gate saw on real slates."""
    cases = [(1.0, 1.0, 0.33),      # tb can't carry the homers claimed
             (0.5, 0.4, 0.20),      # tb below hits outright
             (0.9, 2.0, 1.10),      # more homers than hits
             (1.2, 4.5, 0.10),      # more bases than the hits can carry
             (1.1, 1.8, 0.12)]      # already valid
    rng = random.Random(7)
    cases += [(rng.uniform(0, 2.5), rng.uniform(0, 6.0), rng.uniform(0, 1.2))
              for _ in range(500)]
    for h, t, hr in cases:
        hr2, t2, _ = reconcile_triple(h, t, hr)
        r = G.rates_from_means(h, t2, hr2, pa=4.3)
        assert r.consistent, (h, t, hr, "→", h, t2, hr2)


def test_repairs_only_move_the_directions_the_receipts_allow():
    """HR only ever comes DOWN (it is the market that ran hot); hits is
    never touched; tb moves only the minimum the arithmetic demands."""
    rng = random.Random(11)
    for _ in range(300):
        h, t, hr = (rng.uniform(0, 2.5), rng.uniform(0, 6.0),
                    rng.uniform(0, 1.2))
        hr2, t2, note = reconcile_triple(h, t, hr)
        assert hr2 <= hr + 1e-12
        assert t2 >= min(t, h) - 1e-12          # never below the hits floor
        if not note:
            assert (hr2, t2) == (hr, t)


def test_valid_baseball_is_untouched():
    hr, tb, note = reconcile_triple(1.1, 1.8, 0.12)
    assert (hr, tb, note) == (0.12, 1.8, "")


# --- the prior of last resort ------------------------------------------------
def _hr_prop(career, hr_games, n=10):
    logs = [MLBGameLog(game=n - j, opponent="",
                       value=(1.0 if j < hr_games else 0.0))
            for j in range(n)]
    return MLBProp(player="X", team="HOME", opponent="AWAY", position="RF",
                   market=HOME_RUNS, logs=logs, career_avg=career,
                   vs_pitcher_avg=None, lines=[], lineup_spot=3)


def test_a_player_with_no_career_rate_shrinks_to_the_league_not_himself():
    """prior = observed/n was a no-op disguised as shrinkage: a 4-homer
    fortnight stayed a 0.4/game projection for exactly the rookies the
    receipts caught running hot.

    "No career rate" means None — genuinely not on file. This test used
    to pass 0.0 for that, which is how the falsy check got written and
    shipped: a MEASURED .000 career is not a missing one, and treating
    it as missing handed the league average to every hitter who has
    never homered.
    """
    form = SimpleNamespace(mean=0.4)
    rate = _rare_event_rate(_hr_prop(career=None, hr_games=4), form)
    k = RARE_EVENT_PRIOR_GAMES
    assert abs(rate - (k * LEAGUE_HR_RATE + 4) / (k + 10)) < 1e-9
    assert rate < 0.21                          # nowhere near the raw 0.4
    with_career = _rare_event_rate(_hr_prop(career=0.05, hr_games=4), form)
    assert abs(with_career - (k * 0.05 + 4) / (k + 10)) < 1e-9


# --- half-strength environment on the tail market ----------------------------
def test_homer_environment_is_damped_and_clamped():
    """Coors' 1.22 HR factor claims at sqrt strength (~1.10): each tail
    effect is worst-measured exactly where the long-shot board selects
    hardest, and the boundary temperature was the bill for full strength."""
    prop = _hr_prop(career=0.10, hr_games=1)
    neutral = build_mlb_projection(
        prop, MLBGame(home="HOME", away="AWAY", park="generic"),
        form_weights=MLB_WINDOW_WEIGHTS, player_mult=1.0)
    juiced = build_mlb_projection(
        prop, MLBGame(home="HOME", away="AWAY", park="coors"),
        form_weights=MLB_WINDOW_WEIGHTS, player_mult=1.0)
    ratio = juiced.mean / neutral.mean
    assert abs(ratio - 1.22 ** 0.5) < 0.02      # half strength, not full
    assert ratio <= RARE_EVENT_ENV_CLAMP[1] + 1e-9
    src = open(os.path.join(ROOT, "engine", "mlb", "projection.py"),
               encoding="utf-8").read()
    i = src.index("if prop.market in RARE_EVENT_MARKETS:\n        # Half")
    assert "RARE_EVENT_ENV_DAMP" in src[i:i + 600], \
        "the dampening left the rare-event branch"


# --- the pipeline order ------------------------------------------------------
def test_the_pipeline_reconciles_every_trio_before_it_prices():
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    body = src[src.index("def run_mlb_slate("):]
    assert "reconcile_triple" in body
    assert body.index("reconcile_triple") < body.index(
        "evaluate_mlb_prop(prop, proj"), \
        "projections are priced before the trio is made possible baseball"


def test_no_built_board_ships_an_impossible_trio():
    """The standing audit: any full hits/total-bases/HR trio the pipeline
    emits must sit inside the sim's box. (The sample slate carries no
    full trio today — this guards the day it, or a real slate fixture,
    does.)"""
    from engine.mlb.pipeline import run_mlb_slate
    out = run_mlb_slate(os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    by: dict = {}
    for r in out["recommendations"]:
        if r["market"] in ("hits", "total_bases", "home_runs"):
            by.setdefault(r["player"], {})[r["market"]] = r["projection"]
    for player, mk in by.items():
        if len(mk) != 3:
            continue
        h, t, hr = mk["hits"], mk["total_bases"], mk["home_runs"]
        assert hr <= h + 1e-6, player
        assert h + 3 * hr <= t + 1e-6, player
        assert t <= 3 * h + hr + 1e-6, player


def test_a_measured_zero_career_is_not_an_unknown_career():
    """`if career_avg else LEAGUE_HR_RATE` is falsy, and 0.0 is falsy —
    so a hitter with a genuine .000 career had it overwritten by the
    league average. Measured: he projected 0.056 HR/game while the SAME
    hitter carrying a career 0.01 projected 0.004, i.e. thirteen times
    more likely to homer for never having homered.

    The zero-career population is most of a roster and all of a
    walk-forward's early sample, which is why calibrate.py pinned this
    market at the edge of its search range (T=0.4, a 22-point optimistic
    lean over 293k player-games) while hr_diagnose — which filters to
    "players with home-run history", the one population where this
    cannot fire — reported the model healthy at 1.1x. Two tools
    disagreeing about the same engine was the tell."""
    from engine.mlb.projection import _rare_event_rate, MIN_RARE_EVENT_RATE

    class _F:
        mean = 0.0

    def rate(career, vals):
        logs = [MLBGameLog(game=i, opponent="X", value=v)
                for i, v in enumerate(vals)]
        p = MLBProp(player="P", team="A", opponent="B", position="2B",
                    market=HOME_RUNS, logs=logs, career_avg=career,
                    vs_pitcher_avg=None, lines=[])
        return _rare_event_rate(p, _F)

    never = rate(0.0, [0] * 40)
    rarely = rate(0.01, [0] * 40)
    average = rate(0.10, [0, 0, 1, 0, 0, 0, 0, 0, 1, 0] * 4)
    slugger = rate(0.20, ([0, 1, 0, 0, 1, 0] * 6) + [1, 1])
    # Monotone in the career rate — the inversion is what made it absurd.
    assert never <= rarely <= average <= slugger
    assert never < 0.02, "a .000 career must not inherit the league rate"
    # …but never literally zero: the bottom of an order still runs into one.
    assert never >= MIN_RARE_EVENT_RATE
    assert slugger > 0.2


def test_the_ceiling_is_real_baseball_not_merely_possible_baseball():
    """tb <= 3*hits + hr is what ARITHMETIC allows — every non-HR hit a
    triple. Real hitters run ~1.35 bases per non-HR hit and a
    doubles-heavy slugger ~1.6. Trios near the arithmetic ceiling are
    what the sim gate kept failing on: a live 0.847-hit projection
    carrying 2.387 total bases implies 2.44 bases per non-HR hit, the
    inverter builds a triple-heavy table for it, and the hitter simulated
    16% hot while his eight team-mates sat inside 1%."""
    from engine.mlb.projection import MAX_BASES_PER_NONHR_HIT as C

    def bases_per_hit(h, tb, hr):
        nhr, ntb, _ = reconcile_triple(h, tb, hr)
        return (ntb - 4 * nhr) / max(h - nhr, 1e-9), ntb

    # The two real offenders come back inside the ceiling.
    for h, tb, hr in ((0.847, 2.387, 0.205), (1.368, 3.853, 0.223)):
        bph, ntb = bases_per_hit(h, tb, hr)
        assert bph <= C + 1e-6, (h, tb, hr, bph)
        assert ntb < tb, "the ceiling should have moved it"
    # An ordinary hitter is untouched.
    _bph, ntb = bases_per_hit(0.90, 1.40, 0.10)
    assert abs(ntb - 1.40) < 1e-9
    # The ceiling never falls below the floor, whatever the trio.
    import random
    rng = random.Random(5)
    for _ in range(2000):
        h = rng.uniform(0.05, 2.0)
        hr = rng.uniform(0.0, min(h, 0.6))
        nhr, ntb, _ = reconcile_triple(h, rng.uniform(0.0, 5.0), hr)
        assert ntb >= h - 1e-9, "total bases below the hits projection"
        assert nhr <= h + 1e-9, "more homers than hits"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
