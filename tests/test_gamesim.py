"""The per-game Monte Carlo, and the one rule it is not allowed to trade.

This module exists for the JOINT — the chance two props in the same game
both land — because a per-prop distribution structurally cannot produce one.
Everything here defends two claims:

  * it does not invent a second opinion. The rates are inverted out of the
    projections the pricing engine already produces, so the simulated
    marginals must reproduce them. A sim that disagrees puts two numbers for
    one question on the same page, which is a defect and not a feature.
  * the dependence it reports is ANCHORED to a measurement rather than to
    its own parameters. A simulation will happily produce whatever
    correlation you configure; the shared-latent width was solved against
    engine/parlays.py MEASURED["lineup_stack"], fitted on 27,613 real games.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import gamesim as G                      # noqa: E402
from engine.mlb.models import HITS, HOME_RUNS, TOTAL_BASES   # noqa: E402

#: A realistic nine-man lineup, in the shape build_mlb_projection emits:
#: (name, hits, total bases, home runs) per game.
LINEUP = [("Leadoff", 1.05, 1.72, 0.14), ("Two", 0.98, 1.60, 0.12),
          ("Three", 1.02, 1.95, 0.22), ("Cleanup", 0.95, 1.90, 0.26),
          ("Five", 0.88, 1.55, 0.17), ("Six", 0.82, 1.34, 0.12),
          ("Seven", 0.75, 1.18, 0.09), ("Eight", 0.70, 1.05, 0.07),
          ("Nine", 0.62, 0.92, 0.05)]


def _rates():
    out = []
    for i, (nm, h, tb, hr) in enumerate(LINEUP, start=1):
        r = G.rates_from_means(h, tb, hr, G.expected_pa(i))
        r.name, r.spot = nm, i
        out.append(r)
    return out


def _targets():
    return {nm: {HITS: h, TOTAL_BASES: tb, HOME_RUNS: hr}
            for nm, h, tb, hr in LINEUP}


# --- the inversion ----------------------------------------------------------
def test_the_rate_table_is_a_probability_distribution():
    for r in _rates():
        parts = (r.out, r.bb, r.single, r.double, r.triple, r.hr)
        assert all(p >= 0.0 for p in parts), parts
        assert abs(sum(parts) - 1.0) < 1e-9, sum(parts)


def test_the_inversion_reproduces_the_three_means_per_plate_appearance():
    """Exact arithmetic, before any simulation is involved."""
    pa = 4.3
    r = G.rates_from_means(1.02, 1.95, 0.22, pa)
    assert abs((r.single + r.double + r.triple + r.hr) * pa - 1.02) < 1e-9
    assert abs(r.hr * pa - 0.22) < 1e-9
    bases = (r.single + 2 * r.double + 3 * r.triple + 4 * r.hr) * pa
    assert abs(bases - 1.95) < 1e-9


def test_an_impossible_projection_still_yields_a_valid_table():
    """Total bases below hits implies negative doubles. The arithmetic must
    clamp to something a sim can actually draw from rather than emit a
    negative probability that silently corrupts every trial after it."""
    r = G.rates_from_means(hits=1.5, total_bases=0.4, home_runs=0.3, pa=4.2)
    parts = (r.out, r.bb, r.single, r.double, r.triple, r.hr)
    assert all(p >= 0.0 for p in parts), parts
    assert abs(sum(parts) - 1.0) < 1e-9


def test_the_bottom_of_the_order_bats_less_than_the_top():
    """One flat plate-appearance number hands the ninth spot the leadoff
    spot's playing time, which inflates exactly the cheap props a longshot
    board is most tempted by."""
    assert G.expected_pa(1) > G.expected_pa(5) > G.expected_pa(9)
    assert 3.5 < G.expected_pa(9) < G.expected_pa(1) < 5.0


# --- the gate ---------------------------------------------------------------
def test_the_simulated_marginals_reproduce_the_projections():
    """THE GATE. Nothing downstream may read a joint off a sim that fails
    this."""
    rates = G.calibrate(_rates(), _targets())
    sim = G.simulate_lineup(rates, [], trials=20000)
    rec = G.reconcile(sim, _targets())
    assert rec["ok"], rec["offenders"]
    assert rec["worst_rel_error"] < rec["tol"]


def test_the_gate_actually_fails_when_the_sim_is_wrong():
    """A gate that cannot fail is decoration. Halve every hitter's reaching
    rate and the marginals must be reported as broken."""
    rates = [G._scale_reaching(b, 0.5) for b in _rates()]
    sim = G.simulate_lineup(rates, [], trials=6000)
    rec = G.reconcile(sim, _targets())
    assert rec["ok"] is False
    assert rec["offenders"]
    assert rec["worst_rel_error"] > rec["tol"]


#: A GOOD lineup — every hitter half again league average. The bug this
#: section pins is invisible on an average order and severe here, because
#: the feedback that causes it grows with how often the lineup reaches
#: base. Measured across seven evaluation seeds: the damped fit passes the
#: gate on all seven with no offender, the full-gain fit fails all seven
#: with six to fifteen.
STRONG = [(nm, h * 1.5, tb * 1.5, hr * 1.5) for nm, h, tb, hr in LINEUP]


def _strong():
    rates, targets = [], {}
    for i, (nm, h, tb, hr) in enumerate(STRONG, start=1):
        r = G.rates_from_means(h, tb, hr, G.expected_pa(i))
        r.name, r.spot = nm, i
        rates.append(r)
        targets[nm] = {HITS: h, TOTAL_BASES: tb, HOME_RUNS: hr}
    return rates, targets


def _mean_bias(fitted, targets, trials=40000):
    """Average relative error in simulated total bases, at enough trials
    that the sampler is not what is being measured."""
    sim = G.simulate_lineup(fitted, [], trials=trials, seed=101)
    devs = [sim.mean[nm][TOTAL_BASES] / w[TOTAL_BASES] - 1.0
            for nm, w in targets.items()]
    return sum(devs) / len(devs)


def test_the_fitting_step_is_damped_because_the_response_is_not_linear():
    """REGRESSION, and it cost a dozen live lineups.

    The obvious step is `target/simulated` — came in 10% light, scale up
    10%. It assumes the response is linear, and the entire reason this
    function exists is that it is not: reaching base lengthens the inning,
    which gives the whole lineup another turn, so the response to k is
    nearer k**(1+eps). A full-gain step therefore overshoots, and on a good
    lineup — where eps is largest — it corrected a 24.3% overshoot into a
    5.6% UNDERSHOOT and left it there.

    That is what the live gate had been reporting for weeks: real lineups
    failing with all three of a hitter's markets off by the same percentage
    in the same direction, which is one rescale applied to his whole table,
    not three bad projections."""
    rates, targets = _strong()
    assert G.FIT_DAMP < 1.0, "a full-gain step is the bug"
    damped = _mean_bias(G.calibrate(rates, targets), targets)
    full = _mean_bias(G.calibrate(rates, targets, rounds=3, damp=1.0), targets)
    assert abs(damped) < 0.02, damped
    assert full < -0.03, full          # overshot: corrected past the target
    assert abs(damped) < abs(full) / 2


def test_a_strong_lineup_reconciles_at_all():
    """The gate itself, on the order that used to fail it."""
    rates, targets = _strong()
    sim = G.simulate_lineup(G.calibrate(rates, targets), [], trials=20000)
    assert G.reconcile(sim, targets)["ok"], G.reconcile(sim, targets)


def test_damping_does_not_cost_the_ordinary_lineup_anything():
    """The control, and the reason this is the second attempt at the fix.

    A previous pass at the same failure was reverted because it repaired
    the strong lineup by breaking a balanced one. Any change to the fitting
    step has to be checked against an average order before it ships."""
    assert abs(_mean_bias(G.calibrate(_rates(), _targets()), _targets())) < 0.02


def test_calibration_pulls_a_drifted_sim_back_onto_its_targets():
    """The inversion is exact per plate appearance and that is not the same
    as exact per game: reaching base gives the whole lineup another turn, so
    a mean-1.0 shock drifts counting stats upward. Measured at 7% before the
    re-centring existed."""
    raw = _rates()
    before = G.reconcile(G.simulate_lineup(
        [G._scale_reaching(b, 1.25) for b in raw], [], trials=6000), _targets())
    after = G.reconcile(G.simulate_lineup(
        G.calibrate([G._scale_reaching(b, 1.25) for b in raw], _targets(),
                    trials=6000), [], trials=6000), _targets())
    assert before["worst_rel_error"] > after["worst_rel_error"]
    assert after["ok"], after["offenders"]


# --- the joint, which is the point ------------------------------------------
def _pairs():
    return [(("Leadoff", HITS, 0.5), ("Two", HITS, 0.5)),
            (("Leadoff", HITS, 0.5), ("Nine", HITS, 0.5)),
            (("Three", TOTAL_BASES, 1.5), ("Cleanup", TOTAL_BASES, 1.5)),
            (("Leadoff", HITS, 0.5), ("Cleanup", TOTAL_BASES, 1.5))]


def _legs():
    seen, out = set(), []
    for a, b in _pairs():
        for leg in (a, b):
            if leg not in seen:
                seen.add(leg)
                out.append(leg)
    return out


def test_two_bats_in_one_lineup_are_never_independent():
    """The floor the whole Parlay Zone rests on: nothing in one game is
    independent. Every same-lineup pair must come out positively
    correlated, and the joint must exceed the naive product."""
    rates = G.calibrate(_rates(), _targets())
    sim = G.simulate_lineup(rates, _legs(), trials=20000)
    for a, b in _pairs():
        phi = sim.correlation(a, b)
        assert phi is not None and phi > 0, (a, b, phi)
        assert sim.p_both(a, b) > sim.p_over(*a) * sim.p_over(*b)


def test_the_shared_latent_is_what_makes_the_correlation_realistic():
    """Lineup turnover alone produced phi around +0.034 against a measured
    target near +0.115 — a third of the truth. The shared game draw is the
    channel that closes it, so turning it off has to visibly shrink the
    dependence."""
    rates = G.calibrate(_rates(), _targets(), env_sd=0.0)
    off = G.simulate_lineup(rates, _legs(), trials=20000, env_sd=0.0)
    on_rates = G.calibrate(_rates(), _targets())
    on = G.simulate_lineup(on_rates, _legs(), trials=20000)
    mean_off = sum(off.correlation(a, b) for a, b in _pairs()) / 4
    mean_on = sum(on.correlation(a, b) for a, b in _pairs()) / 4
    assert mean_off > 0, "turnover alone is still a real channel"
    assert mean_on > mean_off * 1.5, (mean_off, mean_on)


def test_the_latent_width_is_anchored_to_a_measurement_not_chosen():
    """A simulation produces whatever dependence its parameters imply, so a
    correlation read off one is worth nothing unless the parameter was set
    by something outside the simulation. Here that is 27,613 real games."""
    from engine import parlays
    rho, n, _ = parlays.MEASURED["lineup_stack"]
    assert n > 20000 and rho > 0
    assert 0.0 < G.ENV_SD < 1.0
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "mlb", "gamesim.py"),
        encoding="utf-8").read()
    assert "lineup_stack" in src, "the anchor is not written down"
    assert "def calibrate_env_sd(" in src


def test_the_latent_understates_rather_than_overstates_the_measurement():
    """0.30 is closer on absolute error and 0.25 is the value, because the
    two miss in opposite directions and parlays.py has already chosen which
    direction this engine accepts: understating correlation understates the
    joint, which raises the required price and makes the screen pickier.

    Pinned as a test because the next person tuning this will find 0.30 fits
    better and needs the reason it is not the value — and because the FIRST
    reason recorded here was wrong. 0.30 was thought to fail the marginal
    gate; it failed a gate that was accidentally strict on rare markets, and
    once that was fixed the real objection turned out to be doctrine."""
    assert G.ENV_SD == 0.25
    rates = G.calibrate(_rates(), _targets())
    sim = G.simulate_lineup(rates, _legs(), trials=20000)
    assert G.reconcile(sim, _targets())["ok"]
    # And it lands BELOW the measured dependence, not above it.
    from engine import parlays
    phis = [sim.correlation(a, b) for a, b in _pairs()]
    targets = []
    for a, b in _pairs():
        p1, p2 = sim.p_over(*a), sim.p_over(*b)
        j = parlays.joint_two(p1, p2, parlays.MEASURED["lineup_stack"][0])
        targets.append((j - p1 * p2) / (p1 * (1 - p1) * p2 * (1 - p2)) ** 0.5)
    assert sum(phis) / len(phis) < sum(targets) / len(targets)


def test_pair_lookup_does_not_care_which_leg_you_name_first():
    rates = G.calibrate(_rates(), _targets())
    sim = G.simulate_lineup(rates, _legs(), trials=4000)
    a, b = _pairs()[0]
    assert sim.p_both(a, b) == sim.p_both(b, a)


def test_the_sim_is_seeded_so_the_page_does_not_jitter():
    """Same reason the season simulator is seeded: numbers that move every
    refresh read as noise even when the model is stable, and nobody can tell
    a real move from the sampler."""
    rates = G.calibrate(_rates(), _targets())
    one = G.simulate_lineup(rates, _legs(), trials=4000, seed=7)
    two = G.simulate_lineup(rates, _legs(), trials=4000, seed=7)
    assert one.mean == two.mean
    assert one.both == two.both


def test_an_empty_lineup_returns_an_empty_sim_rather_than_dividing_by_zero():
    assert G.simulate_lineup([], [], trials=100).trials == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
