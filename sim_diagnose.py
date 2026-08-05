#!/usr/bin/env python3
"""Diagnose a failing sim-gate lineup, offline, from the dump it wrote.

    python3 sim_diagnose.py                      # data/sim_gate_failures.json
    python3 sim_diagnose.py path/to/dump.json

WHY THIS EXISTS

`sim_reconcile.py` needs a live slate, which means it only runs on a
machine that can reach statsapi.mlb.com. Every round of "what is wrong
with those four lineups" therefore cost a round trip: run it there, paste
the output, guess, change something, run it again. Two of those rounds
produced confident explanations that were wrong, and a third produced a
fix that had to be reverted for breaking a lineup nobody had checked.

The dump already contains everything needed to avoid that. Each failing
lineup carries every hitter's three projected means, his batting spot, the
sim's means and standard errors, and assumed versus realised plate
appearances. Projected means plus spots is a complete input to the whole
chain — inversion, fit, simulation — so the lineup can be rebuilt and
re-run anywhere, as many times as wanted, against the real numbers.

WHAT IT SEPARATES

A gate failure has four candidate causes and they call for opposite fixes,
so the useful output is which one it is:

  * THE SAMPLER — the gap is inside the noise of the trial count. Costs
    nothing but trials, and means nothing about either model.
  * THE FIT'S OWN NOISE — `calibrate` computes its step from a sampled
    mean at 8,000 trials, so it scales a hitter's whole table by that
    round's sampler error along with the correction, and the last round's
    is never re-measured. Shows up as a residual that shrinks when the fit
    is given more trials, without more rounds.
  * CONVERGENCE — the fit has not reached its fixed point. Shows up as a
    residual that shrinks with more rounds, without more trials.
  * A REAL DISAGREEMENT — the projection and the sim genuinely differ
    about a hitter, and no amount of either fixes it. This is the finding
    the gate exists to produce, and the one worth acting on.

The single-rescale signature is reported alongside, because it is the
cheapest tell available: `calibrate` scales all of a hitter's reaching
outcomes by one factor, so a fitting problem moves his hits, total bases
and home runs by the SAME percentage in the same direction. Three markets
disagreeing by different amounts is not a fitting problem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.mlb import gamesim as G                          # noqa: E402
from engine.mlb.models import HITS, HOME_RUNS, TOTAL_BASES   # noqa: E402

MARKETS = (HITS, TOTAL_BASES, HOME_RUNS)

#: Trials for the verdict run. High on purpose: this tool is deciding
#: whether a gap is real, and it should not be the thing introducing one.
VERDICT_TRIALS = 120000

#: How closely three markets must agree before the deviation is called a
#: single rescale of the whole table rather than a per-market disagreement.
SAME_RESCALE = 0.015

#: Hits per plate appearance below which a projection is not describing a
#: baseball player. League average is around 0.22 (a .240 average, since
#: roughly a tenth of plate appearances are walks); the worst regular
#: starter in a season sits near 0.15, and a pitcher hitting sits near
#: 0.10. Set below all of them, so this flags the broken rather than the
#: bad — the run that prompted this tool had a hitter at 0.014.
IMPLAUSIBLE_AVG = 0.08



def _rebuild(cell: dict):
    """The lineup, exactly as sim_reconcile built it: rates from projected
    means and batting spot, padded to nine, filler never in targets."""
    rates, targets = [], {}
    for name, h in (cell.get("hitters") or {}).items():
        proj = h.get("projected") or {}
        if not all(m in proj and proj[m] is not None for m in MARKETS):
            continue
        spot = int(h.get("spot") or 0)
        r = G.rates_from_means(proj[HITS], proj[TOTAL_BASES], proj[HOME_RUNS],
                               G.expected_pa(spot))
        r.name, r.spot = name, spot
        if not r.consistent:
            continue
        rates.append(r)
        targets[name] = {m: float(proj[m]) for m in MARKETS}
    return G.pad_to_nine(sorted(rates, key=lambda r: r.spot or 9)), targets


def _devs(sim, targets) -> dict:
    """name -> market -> relative deviation of the sim from the projection."""
    out = {}
    for name, want in targets.items():
        got = sim.mean.get(name) or {}
        out[name] = {m: (got[m] / want[m] - 1.0)
                     for m in MARKETS
                     if got.get(m) is not None and want.get(m)}
    return out


def _run(rates, targets, sim_trials=VERDICT_TRIALS, **fit):
    """``fit`` goes to calibrate (its own trial count, rounds, damping);
    ``sim_trials`` is the measurement afterwards. Two different trial
    counts with two different jobs, so they get two different names."""
    fitted = G.calibrate(rates, targets, **fit)
    sim = G.simulate_lineup(fitted, [], trials=sim_trials)
    return sim, _devs(sim, targets)


def _worst(devs: dict) -> tuple:
    """(name, market, deviation) of the largest gap in the lineup."""
    best = ("", "", 0.0)
    for name, per in devs.items():
        for market, d in per.items():
            if abs(d) > abs(best[2]):
                best = (name, market, d)
    return best


def diagnose(label: str, cell: dict) -> dict:
    rates, targets = _rebuild(cell)
    if len(targets) < 6:
        print(f"\n{label}: only {len(targets)} usable hitters in the dump — "
              f"nothing to diagnose")
        return {}

    print(f"\n=== {label} · {len(targets)} hitters ===")
    reach = [b.bb + b.single + b.double + b.triple + b.hr for b in rates]
    print(f"  lineup reach {sum(reach) / len(reach):.3f} per PA "
          f"(league is about 0.300)")

    # Before asking which model is wrong, ask whether the projection is a
    # number a hitter can have. A per-game hits mean divided by the plate
    # appearances his spot gets is his implied batting average, and a
    # lineup carrying a .014 hitter has a projection-engine problem
    # whatever the sim then does with it. This gets printed first because
    # every failing lineup on the run that prompted this tool had one.
    odd = []
    for b in rates:
        want = targets.get(b.name)
        if not want:
            continue
        avg = want[HITS] / max(G.expected_pa(b.spot), 1e-9)
        if avg < IMPLAUSIBLE_AVG:
            odd.append((b.name, b.spot, want[HITS], avg))
    for name, spot, h, avg in sorted(odd, key=lambda t: t[3]):
        print(f"  ⚠️  {name} (spot {spot}) is projected for {h:.4f} hits a "
              f"game over {G.expected_pa(spot):.2f} plate appearances — "
              f"{avg:.3f} per PA, which is not a hitter. A "
              f"PROJECTION-engine finding; the sim inherits it.")

    # The verdict run: shipping settings, enough trials that the sampler is
    # not the thing being measured.
    tol = float(cell.get("tol") or 0.06)
    sim, devs = _run(rates, targets)
    rec = G.reconcile(sim, targets, tol=tol)

    # The question is the GATE's question — would this lineup still fail if
    # it were measured properly? — so it is asked with the gate, not with a
    # second threshold invented here. An earlier version of this tool used
    # its own cutoff and disagreed with the gate on healthy lineups, which
    # is the exact failure mode it was built to prevent.
    if rec["ok"]:
        name, market, d = _worst(devs)
        print(f"  at {VERDICT_TRIALS:,} trials this lineup PASSES "
              f"(worst {name} {market} {d:+.3f}, tol {tol:.3f})")
        print("  VERDICT: does not reproduce. The run that failed was "
              "reporting its own sampler noise — the trial count is the "
              "only thing to change.")
        return {"verdict": "sampler", "worst": d}

    off = max(rec["offenders"], key=lambda o: abs(o["rel_error"]))
    name, market = off["player"], off["market"]
    d = devs[name][market]
    se = (sim.se.get(name) or {}).get(market) or 0.0
    sigma = abs(d * targets[name][market]) / se if se else float("inf")
    # Both ratios, because at this trial count they routinely disagree: a
    # 1% gap is many sigma once the sampler is this quiet, and still a
    # sixth of what the gate forgives. Significant and important are
    # different questions and the output should not conflate them.
    print(f"  still FAILS at {VERDICT_TRIALS:,} trials on {name} {market} "
          f"{d:+.3f} — {abs(d) / tol:.2f}x the {tol:.3f} tolerance, "
          f"{sigma:.1f} sigma of this run's sampler")

    # No guard is needed on whether that gap is resolvable at all. An
    # earlier version had one, and it was dead code: the gate forgives
    # 2.5 sigma at this same trial count, so anything it still reports as
    # an offender is above 2.5 sigma by construction. Worth writing down,
    # because the guard looks obviously necessary right up until you check.

    # Does the hitter's whole table move together? That is what one rescale
    # looks like, and it is the difference between a fit problem and a
    # model problem.
    per = devs[name]
    spread = max(per.values()) - min(per.values()) if len(per) == 3 else 9.9
    one_rescale = spread <= SAME_RESCALE
    print(f"  {name}'s three markets: "
          + "  ".join(f"{m[:4]} {per[m]:+.3f}" for m in MARKETS if m in per)
          + f"   (spread {spread:.3f} — "
          + ("one rescale of his whole table)" if one_rescale
             else "NOT a single rescale)"))

    # More trials in the fit, same rounds: isolates the fit's own noise.
    _, rich = _run(rates, targets, trials=60000)
    d_rich = rich.get(name, {}).get(market, 0.0)
    # More rounds, same trials: isolates convergence.
    _, longer = _run(rates, targets, rounds=18)
    d_long = longer.get(name, {}).get(market, 0.0)
    print(f"  same hitter, fit at 60,000 trials/round: {d_rich:+.3f}")
    print(f"  same hitter, fit for 18 rounds:          {d_long:+.3f}")

    # "Fixed" means inside the tolerance the gate applies, same standard as
    # everywhere else here — and materially better than shipping, so a
    # coin-flip improvement is not read as a cure.
    fixed = lambda x: abs(x) < tol and abs(x) < abs(d) / 2      # noqa: E731

    if fixed(d_rich) and not fixed(d_long):
        verdict = ("the fit's own sampler noise. calibrate computes its step "
                   "from an 8,000-trial mean and the last round's error is "
                   "never re-measured — raise its trial count, not its "
                   "rounds.")
    elif fixed(d_long) and not fixed(d_rich):
        verdict = ("convergence. The fit has not reached its fixed point on "
                   "this lineup — raise FIT_ROUNDS.")
    elif fixed(d_rich) and fixed(d_long):
        verdict = ("the fitting loop, and either knob reaches it — which "
                   "means the residual is the loop's own noise rather than "
                   "anything about this hitter. More trials per round is "
                   "the cheaper of the two.")
    elif one_rescale:
        verdict = ("a real disagreement, and it is one rescale of the whole "
                   "table — so the sim can reproduce his SHAPE but not his "
                   "LEVEL. Look at whether his projected triple is "
                   "reachable given his lineup spot's plate appearances.")
    else:
        verdict = ("a real disagreement, and his three markets disagree by "
                   "DIFFERENT amounts — so no rescale fixes it. The "
                   "projected triple and the sim genuinely describe "
                   "different hitters; this belongs at the projection "
                   "engine.")
    print(f"  VERDICT: {verdict}")
    return {"verdict": verdict, "worst": d, "one_rescale": one_rescale}


def main(argv: list[str]) -> int:
    path = Path(next((a for a in argv if not a.startswith("-")),
                     ROOT / "data" / "sim_gate_failures.json"))
    if not path.exists():
        print(f"no dump at {path} — run:\n"
              f"    python3 sim_reconcile.py --trials=80000 --dump")
        return 1
    dump = json.loads(path.read_text())
    if not dump:
        print(f"{path} is empty — the gate passed everywhere.")
        return 0
    print(f"{len(dump)} failing lineup(s) in {path}")
    for label, cell in sorted(dump.items()):
        diagnose(label, cell)
    print("\nEach verdict names the ONE thing to change. A sampler verdict "
          "means raise --trials and stop; a fit verdict means the fitting "
          "loop; a real disagreement means one of the two models is wrong "
          "about that hitter, which is what the gate is for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
