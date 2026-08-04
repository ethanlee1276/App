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
    receipts caught running hot."""
    form = SimpleNamespace(mean=0.4)
    rate = _rare_event_rate(_hr_prop(career=0.0, hr_games=4), form)
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
