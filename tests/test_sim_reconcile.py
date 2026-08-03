"""The live-slate gate harness for the per-game Monte Carlo (task #60).

The sim's acceptance test is that it reproduces the closed-form projections
on REAL data. The harness is what runs that test as one command — so the
harness itself needs pinning: that it only reconciles hitters whose three
markets all projected, that a thin slate reports "nothing to measure"
rather than passing vacuously, and that its exit codes mean what the
docstring says, because a gate whose green cannot be told from its grey is
not a gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sim_reconcile as SR                                    # noqa: E402
from engine.mlb.models import (HITS, HOME_RUNS, TOTAL_BASES,  # noqa: E402
                               MLBGame, MLBGameLog, MLBProp)
from engine.mlb.data_loader import MLBSlate                   # noqa: E402


def _game():
    return MLBGame(home="NYY", away="BOS", park="yankee")


def _prop(player, market, spot, values):
    logs = [MLBGameLog(game=i, opponent="BOS", value=v)
            for i, v in enumerate(values)]
    return MLBProp(player=player, team="NYY", opponent="BOS", position="RF",
                   market=market, logs=logs,
                   career_avg=sum(values) / len(values),
                   vs_pitcher_avg=None, lines=[], lineup_spot=spot)


def _full_slate(n_hitters=9):
    """Nine hitters, each with all three markets projected from real-shaped
    logs — the smallest slate the gate can genuinely run on."""
    props = []
    for i in range(n_hitters):
        nm, spot = f"Hitter {i + 1}", i + 1
        props.append(_prop(nm, HITS, spot, [1, 0, 2, 1, 0, 1, 2, 0, 1, 1]))
        props.append(_prop(nm, TOTAL_BASES, spot,
                           [2, 0, 5, 2, 0, 1, 5, 0, 2, 1]))
        props.append(_prop(nm, HOME_RUNS, spot,
                           [0, 0, 1, 0, 0, 0, 1, 0, 0, 0]))
    return MLBSlate(date="2026-08-03", games=[_game()], props=props)


def test_only_hitters_with_all_three_markets_enter_the_gate():
    """The inversion solves one outcome table from three means. Two means
    is not a table, and reconciling against it would grade the sim on a
    question it was never asked."""
    slate = _full_slate()
    slate.props.append(_prop("Partial Pete", HITS, 9, [1, 1, 0]))
    cells = SR._lineups(slate)
    hitters = cells[("NYY", 1)]["hitters"]
    assert len(hitters["Hitter 1"]) == 3
    assert len(hitters["Partial Pete"]) == 1     # seen, but not gateable


def test_a_hitter_without_a_lineup_spot_stays_out():
    """No spot means no plate-appearance estimate, and inventing one hands
    the bench the leadoff hitter's playing time."""
    slate = _full_slate()
    slate.props.append(_prop("Bench Bob", HITS, 0, [1, 0, 1]))
    cells = SR._lineups(slate)
    assert "Bench Bob" not in cells[("NYY", 1)]["hitters"]


def test_the_gate_passes_end_to_end_on_a_full_synthetic_slate(monkey=None):
    """run() wired whole: slate → projections → inversion → calibrate →
    simulate → reconcile → exit 0. The projections here come from
    build_mlb_projection itself, so this exercises the exact pipeline the
    laptop run will."""
    orig = None
    import engine.mlb.sources.statslogs as SL
    orig = SL.build_live_slate
    SL.build_live_slate = lambda date: _full_slate()
    try:
        code = SR.run("2026-08-03")
    finally:
        SL.build_live_slate = orig
    assert code == 0


def test_a_thin_slate_is_nothing_to_measure_not_a_pass():
    """Five projected hitters is a third of a batting order. Exit 1 — the
    grey outcome — never a vacuous green."""
    import engine.mlb.sources.statslogs as SL
    orig = SL.build_live_slate
    SL.build_live_slate = lambda date: _full_slate(n_hitters=3)
    try:
        code = SR.run("2026-08-03")
    finally:
        SL.build_live_slate = orig
    assert code == 1


def test_a_dead_feed_is_grey_too():
    import engine.mlb.sources.statslogs as SL
    orig = SL.build_live_slate

    def _boom(date):
        raise RuntimeError("egress blocked")
    SL.build_live_slate = _boom
    try:
        code = SR.run("2026-08-03")
    finally:
        SL.build_live_slate = orig
    assert code == 1


def test_the_min_hitters_bar_is_most_of_a_batting_order():
    assert 6 <= SR.MIN_HITTERS <= 9


def test_an_impossible_projected_triple_is_a_projection_finding_not_a_gate_fail():
    """The first fixture here contained games like "2 hits, 4 TB, 1 HR" —
    zero bases left for the non-HR hit. The gate failed at 11% and the
    failure was CORRECT: no outcome table can reproduce an impossible
    triple, so calibration fit total bases and left hits 8% short. But the
    blame belongs on the projection that emitted the triple, not on the
    sim — so rates_from_means now flags it and the harness excludes it,
    reporting it as its own finding. Park and Statcast multipliers scale
    markets independently, so real slates CAN produce these."""
    from engine.mlb import gamesim as G
    bad = G.rates_from_means(hits=0.9, total_bases=1.0, home_runs=0.2, pa=4.4)
    assert bad.consistent is False
    good = G.rates_from_means(hits=0.9, total_bases=1.6, home_runs=0.2, pa=4.4)
    assert good.consistent is True
    # More homers than hits is the other impossible shape.
    assert G.rates_from_means(0.1, 1.0, 0.3, 4.4).consistent is False
    # And a lineup full of impossible triples is "nothing to measure",
    # never a vacuous pass and never a sim failure.
    import engine.mlb.sources.statslogs as SL
    slate = _full_slate()
    for p in slate.props:
        if p.market == TOTAL_BASES:
            for log in p.logs:
                log.value = 0.5          # TB below hits everywhere
    orig = SL.build_live_slate
    SL.build_live_slate = lambda date: slate
    try:
        code = SR.run("2026-08-03")
    finally:
        SL.build_live_slate = orig
    assert code == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
