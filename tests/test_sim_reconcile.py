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
from engine.mlb import gamesim as G                           # noqa: E402
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
    laptop run will.

    Run at more trials than the nightly default, deliberately. The claim
    here is about the WIRING, and at 20,000 trials this assertion was
    partly about the random number generator instead: these synthetic logs
    give all nine hitters 0.21 home runs a game, and the gate takes the
    max over 27 comparisons (nine hitters, three markets), so the rarest
    market's sampler noise lands a ~2-sigma draw on top of the tolerance
    more often than it has any business doing. Measured on this slate —
    the fitted table's TRUE bias at 400,000 trials is -0.13% mean and
    -2.3% worst, while the 20,000-trial verdict swung between 0.023 and
    0.061 across five seeds and tripped the 0.06 tolerance on one of them.
    At 50,000 the same five seeds top out at 0.039."""
    orig = None
    import engine.mlb.sources.statslogs as SL
    orig = SL.build_live_slate
    SL.build_live_slate = lambda date: _full_slate()
    try:
        code = SR.run("2026-08-03", trials=50000)
    finally:
        SL.build_live_slate = orig
    assert code == 0


def test_a_pass_whose_worst_error_beats_the_tolerance_explains_itself():
    """`✅ OAK 9 hitters · worst rel error 0.092 (tol 0.06)` came off a real
    run and reads as a broken tool. It is not: the gate forgives whichever
    is larger, the flat tolerance or the sampler's own noise, and on a
    0.04-per-game home-run rate the second is much the larger. The number
    that makes the verdict legible has to be printed next to it."""
    import io
    import contextlib
    import engine.mlb.sources.statslogs as SL
    orig = SL.build_live_slate
    SL.build_live_slate = lambda date: _full_slate()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            SR.run("2026-08-03", trials=2000)      # deliberately far too few
    finally:
        SL.build_live_slate = orig
    out = buf.getvalue()
    assert "sampler" in out, out
    # And the noise band is a real number the caller can act on.
    assert "±0." in out or "--trials=" in out, out


def test_a_failure_on_a_thin_market_says_so_instead_of_blaming_a_model():
    """The gate takes the max over every hitter and market on the slate —
    hundreds of comparisons — so the largest is out near three sigma by
    construction, and on a 0.045-per-game home run that is most of the
    tolerance before either model has said anything. Announcing "one of the
    two models is wrong" without that arithmetic sends someone hunting a
    bug in a projection engine that is fine."""
    import io
    import contextlib
    import engine.mlb.sources.statslogs as SL

    orig_slate, orig_rec = SL.build_live_slate, G.reconcile
    SL.build_live_slate = lambda date: _full_slate()
    # A failure on a genuinely rare market, which is the case that misleads.
    G.reconcile = lambda sim, targets, tol=0.06: {
        "ok": False, "worst_rel_error": 0.076, "noise_rel": 0.071, "tol": tol,
        "offenders": [{"player": "Hitter 1", "market": HOME_RUNS,
                       "projected": 0.045, "simulated": 0.041,
                       "rel_error": 0.076}]}
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = SR.run("2026-08-03", trials=20000)
    finally:
        SL.build_live_slate, G.reconcile = orig_slate, orig_rec
    out = buf.getvalue()
    assert code == 2                      # still a failure, not explained away
    assert "0.045 a game" in out, out
    assert "sampler error" in out, out
    assert "--trials=" in out, out


def test_the_noise_band_comes_back_with_the_verdict():
    """A gate that reports only the gap cannot be read. `noise_rel` is the
    sampler's own relative error where it is largest, so `worst_rel_error`
    under it is a statement about the trial count rather than the model."""
    rates, targets = [], {}
    for i, (nm, h, tb, hr) in enumerate(
            [(f"H{i}", 0.9, 1.5, 0.04) for i in range(9)], start=1):
        r = G.rates_from_means(h, tb, hr, G.expected_pa(i))
        r.name, r.spot = nm, i
        rates.append(r)
        targets[nm] = {HITS: h, TOTAL_BASES: tb, HOME_RUNS: hr}
    few = G.reconcile(G.simulate_lineup(rates, [], trials=2000), targets)
    many = G.reconcile(G.simulate_lineup(rates, [], trials=40000), targets)
    assert few["noise_rel"] > many["noise_rel"] > 0.0
    # Rare markets are where it bites: home runs at 0.04 a game move several
    # percent between seeds while total bases barely stir.
    assert few["noise_rel"] > few["tol"]


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
    # A lineup of impossible triples used to be "nothing to measure":
    # every hitter was flagged, dropped, and the slate fell under
    # MIN_HITTERS. That was the harness reading the RAW projection engine
    # while the board prices reconciled trios — so the same repair now
    # runs first and these become measurable instead of unmeasurable.
    # The flagging path above is still the truth for anything that
    # reaches the gate incoherent; it just no longer has customers.
    import engine.mlb.sources.statslogs as SL
    slate = _full_slate()
    for p in slate.props:
        if p.market == TOTAL_BASES:
            for log in p.logs:
                log.value = 0.5          # TB below hits everywhere
    lineups = SR._lineups(slate)
    assert lineups, "the slate should still produce a lineup"
    for cell in lineups.values():
        for nm, mk in cell["hitters"].items():
            if not all(m in mk for m in (HITS, TOTAL_BASES, HOME_RUNS)):
                continue
            spot = int(cell["spots"].get(nm) or 9)
            r = G.rates_from_means(mk[HITS], mk[TOTAL_BASES], mk[HOME_RUNS],
                                   G.expected_pa(spot))
            assert r.consistent, \
                f"{nm} reached the gate impossible: {mk}"


def test_the_gate_reads_the_same_reconciled_trio_the_board_prices():
    """The harness walked build_mlb_projection per market — the RAW
    engine — while run_mlb_slate prices in two phases and runs
    reconcile_triple over every (hits, TB, HR) trio first. So the gate
    was grading a model nobody runs: on a live slate ~100 hitters a night
    were reported "not valid baseball" and dropped, which pushed most
    lineups under MIN_HITTERS and left two thirds of the league with no
    verdict at all."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "sim_reconcile.py"), encoding="utf-8").read()
    assert "reconcile_triple" in src
    assert src.index("reconcile_triple") < src.index("def run(")


def test_reconciling_never_rounds_itself_back_out_of_the_box():
    """round(tb, 4) can land a hair BELOW the hits projection, which is
    exactly the 'total bases below hits' inconsistency reconcile_triple
    had just removed — a 1e-5 violation the sim's inverter checks to
    1e-9 and correctly calls impossible. Both call sites assign the
    returned floats untouched; this pins that they stay in the box."""
    import random
    from engine.mlb import gamesim as G
    from engine.mlb.projection import reconcile_triple
    rng = random.Random(9)
    checked = 0
    for _ in range(3000):
        hits = rng.uniform(0.05, 1.9)
        tb = hits * rng.uniform(0.4, 4.2)
        hr = rng.uniform(0.0, 0.6)
        pa = G.expected_pa(rng.randint(1, 9))
        hr2, tb2, note = reconcile_triple(hits, tb, hr)
        if not note:
            continue
        checked += 1
        assert G.rates_from_means(hits, tb2, hr2, pa).consistent, \
            f"reconciled trio still impossible: {hits} {tb2} {hr2}"
    assert checked > 500, "the sweep should exercise real repairs"
    # And the rounding that broke it is gone from both ASSIGNMENTS. Match
    # the assignment rather than the bare call: both files discuss the
    # removed rounding in comments, and grepping for the text alone fails
    # on the explanation of the fix.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in ("sim_reconcile.py", os.path.join("engine", "mlb", "pipeline.py")):
        src = open(os.path.join(root, path), encoding="utf-8").read()
        for bad in ("= round(tb_new, 4)", "= round(hr_new, 4)",
                    "= round(hr, 4), round(tb, 4)"):
            assert bad not in src, f"{path} still rounds the reconciled trio"


def test_a_short_order_is_padded_so_it_cycles_at_nine():
    """A real lineup always has nine batters. Simulating the eight we
    could project cycles the order 9/8 too fast and hands everyone ~12%
    more plate appearances than his spot assumes — measured on a live
    slate, an eight-man Dodgers order put its leadoff man at 5.24 PA
    against 4.65, and the whole lineup failed the gate for a reason that
    was ours rather than the model's. The filler never enters targets, so
    it shapes the turnover and is never graded."""
    from engine.mlb import gamesim as G
    eight = []
    for spot in range(1, 9):
        r = G.rates_from_means(0.90, 1.45, 0.11, G.expected_pa(spot))
        r.name, r.spot = f"bat{spot}", spot
        eight.append(r)
    padded = G.pad_to_nine(eight)
    assert len(padded) == 9
    assert sorted(b.spot for b in padded) == list(range(1, 10))
    assert sum(1 for b in padded if b.name.startswith("_filler")) == 1
    # The leadoff man's realised PA comes back toward what his spot assumes.
    def pa(rates):
        return G.simulate_lineup(rates, [], trials=20000).pa_mean["bat1"]
    short, full = pa(eight), pa(padded)
    assert short > full > G.expected_pa(1) - 0.5
    # Margin rather than a bare comparison (see test_sidebias.py).
    # Measured: 0.106 against 0.631.
    assert (abs(full - G.expected_pa(1))
            < abs(short - G.expected_pa(1)) * 0.9)
    # A full nine is returned untouched.
    assert len(G.pad_to_nine(padded)) == 9


def test_the_gate_pads_before_it_fits():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "sim_reconcile.py"), encoding="utf-8").read()
    assert "pad_to_nine" in src
    assert src.index("pad_to_nine") < src.index("G.calibrate(")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
