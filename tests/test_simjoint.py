"""Task #60 — tonight's actual joint, for tonight's actual legs.

The Parlay Zone prices a pair through a Gaussian copula that needs one
number: the latent correlation. For two bats in one lineup that number has
always been +0.186 — measured, honestly, on 27,613 real games, and the
same for every pair. The leadoff hitter and the number two bat back to
back, so one reaching is literally what gives the other his extra turn;
the leadoff hitter and the number eight share far less. A league average
prices both identically, and the ticket a bettor is offered is one
specific pair.

`engine/mlb/gamesim.py` deals both legs out of the same simulated innings,
so it OBSERVES the dependence instead of assuming it. That was the only
new information the sim was ever built to produce, and these tests defend
the three rules under which it is allowed to be used:

  * the GATE is absolute. A sim whose marginals disagree with the pricing
    engine has no standing to describe their joint, so a lineup that fails
    reconcile contributes nothing and its pairs keep the prior. That gate
    is why this task waited — it failed on a dozen live lineups for weeks.
  * the translation is SOLVED, not assumed. The sim reports P(both win);
    the copula speaks latent correlation. They are different numbers at
    these marginals and quoting one as the other would be a silent error.
  * absent, gated out, or wildly disagreeing, NOTHING changes. Every path
    out of this module falls back to exactly what shipped before it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import simjoint                              # noqa: E402
from engine.mlb import gamesim as G                          # noqa: E402
from engine.mlb.models import (MLBProp, MLBGame, MLBGameLog,  # noqa: E402
                               HITS, HOME_RUNS, TOTAL_BASES)
from engine.mlb.data_loader import MLBSlate                  # noqa: E402
from engine.parlays import relate, joint_two, MEASURED       # noqa: E402

import contextlib


@contextlib.contextmanager
def _sim_seated():
    """Run a test with the sim's seat restored.

    The 2026-08-18 reconciliation benched simjoint (WORSE THAN THE PRIOR,
    19 SE on 40,181 pairs) and ENABLED ships False — test_simrecon pins
    that. The pricing mechanism must still WORK, because a winning appeal
    reseats it with one flag flip; these tests exercise that mechanism."""
    was = simjoint.ENABLED
    simjoint.ENABLED = True
    try:
        yield
    finally:
        simjoint.ENABLED = was


#: Nine hitters with real-shaped logs, the smallest slate a joint can come
#: out of. Values chosen so every projected trio is valid baseball.
LOGS = {HITS: [1, 0, 2, 1, 0, 1, 2, 0, 1, 1],
        TOTAL_BASES: [2, 0, 5, 2, 0, 1, 5, 0, 2, 1],
        HOME_RUNS: [0, 0, 1, 0, 0, 0, 1, 0, 0, 0]}


def _prop(player, market, spot, team="NYY"):
    logs = [MLBGameLog(game=i, opponent="BOS",
                       value=float(v), home=True)
            for i, v in enumerate(LOGS[market])]
    return MLBProp(player=player, team=team, opponent="BOS", position="RF",
                   market=market, logs=logs,
                   career_avg=sum(LOGS[market]) / len(LOGS[market]),
                   career_games=140, vs_pitcher_avg=None, lines=[],
                   lineup_spot=spot)


def _slate(n=9, team="NYY"):
    props = []
    for i in range(n):
        for m in (HITS, TOTAL_BASES, HOME_RUNS):
            props.append(_prop(f"Hitter {i + 1}", m, i + 1, team))
    game = MLBGame(home=team, away="BOS", park=team)
    return MLBSlate(date="2026-08-05", games=[game], props=props)


def _legs(names, market=HITS, line=0.5, side="OVER", team="NYY"):
    return [{"player": n, "market": market, "line": line, "side": side,
             "team": team, "game_number": 1} for n in names]


# --- it produces a joint at all --------------------------------------------
def test_two_bats_in_one_lineup_get_a_simulated_correlation():
    j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"]), trials=6000)
    assert j["rho"], j["lineups"]
    rho = list(j["rho"].values())[0]
    assert -1.0 < rho < 1.0
    # Same-lineup bats are positively dependent; that is the floor the whole
    # Parlay Zone rests on.
    assert rho > 0, rho


def test_the_whole_order_is_simulated_not_just_the_two_legs():
    """The dependence runs through lineup turnover, so simulating two bats
    alone would measure a different game from the one being bet."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "mlb", "simjoint.py"),
        encoding="utf-8").read()
    assert "pad_to_nine" in src
    j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"]), trials=6000)
    assert "2" not in j["lineups"].get("NYY", ""), j["lineups"]


# --- the translation is solved, not assumed --------------------------------
def test_the_solved_rho_reproduces_the_joint_it_came_from():
    """P(both win) and latent correlation are different numbers at these
    marginals. Quoting one as the other would be a silent error, so the
    translation is a bisection on the copula the Zone actually prices with."""
    for p1, p2, target_rho in ((0.55, 0.40, 0.20), (0.30, 0.30, 0.05),
                               (0.70, 0.65, 0.35)):
        joint = joint_two(p1, p2, target_rho)
        got = simjoint.solve_rho(p1, p2, joint)
        assert got is not None
        assert abs(got - target_rho) < 0.01, (target_rho, got)


def test_an_impossible_joint_gets_no_answer_rather_than_a_wrong_one():
    assert simjoint.solve_rho(0.5, 0.5, 0.999) is None
    assert simjoint.solve_rho(0.5, 0.5, 0.0) is None
    assert simjoint.solve_rho(0.0, 0.5, 0.1) is None


# --- the gate is absolute --------------------------------------------------
def test_a_lineup_that_fails_the_gate_contributes_nothing():
    """THE precondition. A sim whose marginals disagree with the pricing
    engine has no standing to describe their joint — and this is the gate
    that kept task #60 shut for weeks while it failed on live lineups."""
    orig = G.reconcile
    G.reconcile = lambda sim, targets, tol=0.06: {
        "ok": False, "worst_rel_error": 0.19, "noise_rel": 0.02,
        "tol": tol, "offenders": [{"player": "Hitter 1", "market": HITS,
                                   "projected": 1.0, "simulated": 1.2,
                                   "rel_error": 0.19}]}
    try:
        j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"]),
                           trials=4000)
    finally:
        G.reconcile = orig
    assert j["rho"] == {}
    assert "gate failed" in j["lineups"]["NYY"], j["lineups"]


def test_a_short_lineup_is_not_evidence():
    j = simjoint.build(_slate(n=4), _legs(["Hitter 1", "Hitter 2"]),
                       trials=4000)
    assert j["rho"] == {}
    assert "projected hitters" in j["lineups"]["NYY"]


# --- what it declines to touch ---------------------------------------------
def test_markets_the_sim_does_not_deal_keep_the_prior():
    """Strikeouts, outs and every game line are outside what the sim
    tallies, so it has no opinion and must not pretend to one."""
    j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"],
                                       market="strikeouts"), trials=4000)
    assert j["rho"] == {} and j["lineups"] == {}


def test_unders_keep_the_prior():
    """The sim tallies "cleared the line". An UNDER is the complement of a
    leg it counted, and the joint of two complements is not the complement
    of the joint — so deriving it here would be wrong, not merely absent."""
    j = simjoint.build(_slate(), _legs(["Hitter 1", "Hitter 2"], side="UNDER"),
                       trials=4000)
    assert j["rho"] == {}


def test_two_legs_on_different_teams_are_not_one_lineup():
    legs = (_legs(["Hitter 1"], team="NYY")
            + _legs(["Hitter 2"], team="BOS"))
    j = simjoint.build(_slate(), legs, trials=4000)
    assert j["rho"] == {}


# --- and the fallback is the old behaviour, exactly ------------------------
def test_no_joints_means_the_measured_prior_verbatim():
    a, b = _legs(["Hitter 1", "Hitter 2"])
    for m in (a, b):
        m["market"] = HITS
    without = relate("mlb", a, b, None, None)
    assert abs(without.rho - MEASURED["lineup_stack"][0]) < 1e-9
    assert "27,613" in without.mechanism or "games put it at" in without.mechanism


def test_a_simulated_pair_replaces_the_prior_and_says_so():
    a, b = _legs(["Hitter 1", "Hitter 2"])
    j = simjoint.build(_slate(), [a, b], trials=8000)
    assert j["rho"], j["lineups"]
    with _sim_seated():
        with_sim = relate("mlb", a, b, None, j)
    assert with_sim.measured is True
    assert "tonight's own lineup" in with_sim.mechanism, with_sim.mechanism
    assert with_sim.rho == list(j["rho"].values())[0]


def test_a_wild_disagreement_with_the_prior_is_refused():
    """27,613 games against one night's model. A gap that large is a
    finding to chase, not a number to bet."""
    a, b = _legs(["Hitter 1", "Hitter 2"])
    key = simjoint.pair_key((a["player"], a["market"], a["line"]),
                            (b["player"], b["market"], b["line"]))
    prior = MEASURED["lineup_stack"][0]
    with _sim_seated():
        assert simjoint.rho_for({"rho": {key: prior + 0.9}}, a, b,
                                prior) is None
        assert simjoint.rho_for({"rho": {key: prior - 0.9}}, a, b,
                                prior) is None
        ok = simjoint.rho_for({"rho": {key: prior + 0.05}}, a, b, prior)
    assert ok and abs(ok[0] - (prior + 0.05)) < 1e-9


def test_the_lookup_does_not_care_which_leg_came_first():
    a, b = _legs(["Hitter 1", "Hitter 2"])
    j = simjoint.build(_slate(), [a, b], trials=6000)
    with _sim_seated():
        assert (relate("mlb", a, b, None, j).rho
                == relate("mlb", b, a, None, j).rho)


def test_the_mlb_pipeline_asks_for_them_and_cannot_be_killed_by_them():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    i = src.index("from .simjoint import build")
    assert "except Exception" in src[i:i + 400], "a joint must never kill a slate"
    assert 'attach(out, "mlb", joints=joints)' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
