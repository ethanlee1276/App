#!/usr/bin/env python3
"""The game-sim gate, against a REAL slate.

    python3 sim_reconcile.py               # tonight
    python3 sim_reconcile.py 2026-08-05    # a named date

This is the acceptance test recorded when the per-game Monte Carlo was
built: the sim's marginals must reproduce the closed-form projections it
was inverted from, on live data, before anything downstream may read a
joint off it. Two numbers for one question on one page is a defect, and
reconciling them is also the cheapest way to find a bug in either model —
a disagreement means one of them is wrong, and which one is a question
worth being forced to answer.

Free: the slate comes from the keyless MLB stats API, the projections are
the same ones the nightly board already computes, and the sim never
touches the odds meter.

Exit codes: 0 gate passes everywhere it could run · 1 nothing to measure
(offseason, no lineups, feed down) · 2 the gate FAILED somewhere.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.mlb import gamesim as G                          # noqa: E402
from engine.mlb.models import HITS, HOME_RUNS, TOTAL_BASES   # noqa: E402
from engine.mlb.projection import build_mlb_projection       # noqa: E402

#: A lineup below this many fully-projected hitters is not evidence — the
#: sim would be reconciling against a third of a batting order, and the
#: turnover dynamics it models need the whole order to mean anything.
MIN_HITTERS = 6


def _lineups(slate):
    """{(team, game_number): {"game": MLBGame, "hitters": {name: {market: mean}}}}

    Only hitters with a confirmed/projected lineup spot and all three
    hitter markets projected — the inversion needs hits, total bases and
    home runs together or there is no outcome table to solve for.
    """
    by_game = {}
    for g in slate.games:
        gn = int(getattr(g, "game_number", 1) or 1)
        by_game[(g.home, gn)] = g
        by_game[(g.away, gn)] = g
    out = {}
    for p in slate.props:
        if p.market not in (HITS, TOTAL_BASES, HOME_RUNS):
            continue
        if not p.lineup_spot:
            continue
        gn = int(getattr(p, "game_number", 1) or 1)
        game = by_game.get((p.team, gn))
        if game is None:
            continue
        key = (p.team, gn)
        cell = out.setdefault(key, {"game": game, "hitters": {}, "spots": {}})
        try:
            proj = build_mlb_projection(p, game)
        except Exception:                          # noqa: BLE001
            continue
        cell["hitters"].setdefault(p.player, {})[p.market] = proj.mean
        cell["spots"][p.player] = p.lineup_spot
    # Reconcile the triple exactly as the BOARD does before checking it.
    #
    # This walks build_mlb_projection per market, which is the raw
    # projection engine — but run_mlb_slate prices in two phases, building
    # every projection and then running reconcile_triple over each
    # (hits, total bases, home runs) trio before anything is evaluated. So
    # the numbers that actually ship are coherent, and reading the raw
    # means here graded a model nobody runs: a hundred-odd hitters a night
    # were reported as "not valid baseball" and DROPPED, which pushed most
    # lineups under MIN_HITTERS and left two thirds of the league with no
    # verdict at all. Same reconciliation, same order, same numbers.
    from engine.mlb.projection import reconcile_triple
    for cell in out.values():
        for markets in cell["hitters"].values():
            if not all(m in markets for m in (HITS, TOTAL_BASES, HOME_RUNS)):
                continue
            hr, tb, note = reconcile_triple(markets[HITS],
                                            markets[TOTAL_BASES],
                                            markets[HOME_RUNS])
            if note:
                # Assigned EXACTLY as returned. Rounding here re-broke the
                # box: tb rounded to 4dp can land a hair below hits, and
                # "total bases below the hits projection" is precisely the
                # inconsistency reconcile_triple had just removed.
                markets[HOME_RUNS], markets[TOTAL_BASES] = hr, tb
    return out


def run(date: str, dump_path: str | None = None,
        trials: int = 20000) -> int:
    from engine.mlb.sources.statslogs import build_live_slate
    try:
        slate = build_live_slate(date)
    except Exception as exc:                       # noqa: BLE001
        print(f"no slate for {date}: {exc}")
        return 1

    lineups = _lineups(slate)
    dump = {} if dump_path else None
    ran = failed = 0
    worst_overall = 0.0
    for (team, gn), cell in sorted(lineups.items()):
        full = {nm: mk for nm, mk in cell["hitters"].items()
                if all(m in mk for m in (HITS, TOTAL_BASES, HOME_RUNS))}
        if len(full) < MIN_HITTERS:
            continue

        rates, targets, invalid = [], {}, []
        for nm, mk in full.items():
            spot = int(cell["spots"].get(nm) or 0)
            r = G.rates_from_means(mk[HITS], mk[TOTAL_BASES], mk[HOME_RUNS],
                                   G.expected_pa(spot))
            r.name, r.spot = nm, spot
            if not r.consistent:
                # The three means cannot coexist in any real game — usually
                # total bases too low for the hits and homers claimed, which
                # market-specific park/Statcast multipliers can produce.
                # That is a PROJECTION-engine finding: the sim cannot
                # reproduce a triple no table could, and gating it here
                # would blame the wrong model.
                invalid.append(nm)
                continue
            rates.append(r)
            targets[nm] = dict(mk)
        if invalid:
            print(f"  ⚠️  {team}: {len(invalid)} projected triple(s) aren't "
                  f"valid baseball ({', '.join(invalid[:3])}"
                  + ("…" if len(invalid) > 3 else "")
                  + ") — a projection-engine finding, excluded from the gate")
        if len(targets) < MIN_HITTERS:
            continue
        # A real order is nine deep. Simulating the eight we could project
        # cycles it 9/8 too fast and inflates everyone's plate appearances
        # ~12%, which fails the gate for a reason that is ours, not the
        # model's. The filler is never in `targets`, so it is never graded.
        rates = G.pad_to_nine(sorted(rates, key=lambda r: r.spot or 9))
        fitted = G.calibrate(rates, targets)
        sim = G.simulate_lineup(fitted, [], trials=trials)
        rec = G.reconcile(sim, targets)
        ran += 1
        worst_overall = max(worst_overall, rec["worst_rel_error"])
        tag = "✅" if rec["ok"] else "❌"
        label = f"{team}" + (f" (G{gn})" if gn > 1 else "")
        print(f"  {tag} {label:<10} {len(full)} hitters · worst rel error "
              f"{rec['worst_rel_error']:.3f} (tol {rec['tol']})")
        if not rec["ok"]:
            failed += 1
            for o in rec["offenders"][:4]:
                nm = o["player"]
                spot = int(cell["spots"].get(nm) or 0)
                pa_sim = (sim.pa_mean or {}).get(nm)
                pa_want = G.expected_pa(spot)
                pa_note = (f"  PA {pa_want:.2f}→{pa_sim:.2f}"
                           if pa_sim else "")
                print(f"       {nm:<22} {o['market']:<12} "
                      f"projected {o['projected']} simulated {o['simulated']}"
                      f"   (spot {spot}{pa_note})")
            if dump is not None:
                dump[f"{team}" + (f"-G{gn}" if gn > 1 else "")] = {
                    "tol": rec["tol"], "worst": rec["worst_rel_error"],
                    "hitters": {
                        nm: {"spot": int(cell["spots"].get(nm) or 0),
                             "projected": targets[nm],
                             "simulated": {m: sim.mean.get(nm, {}).get(m)
                                           for m in (HITS, TOTAL_BASES,
                                                     HOME_RUNS)},
                             "se": {m: (sim.se.get(nm) or {}).get(m)
                                    for m in (HITS, TOTAL_BASES, HOME_RUNS)},
                             "pa_expected": G.expected_pa(
                                 int(cell["spots"].get(nm) or 0)),
                             "pa_simulated": (sim.pa_mean or {}).get(nm)}
                        for nm in targets},
                }

    if not ran:
        print("nothing to reconcile — no lineup had "
              f"{MIN_HITTERS}+ fully projected hitters (lineups post "
              "~3-4h before first pitch)")
        return 1
    print(f"\n{ran} lineup(s) reconciled · worst relative error "
          f"{worst_overall:.3f}")
    if failed:
        print(f"GATE FAILED on {failed} lineup(s). One of the two models is "
              "wrong about those hitters — resolve before the sim's joints "
              "feed anything a bettor sees.")
        if dump is not None:
            import json as _json
            Path(dump_path).parent.mkdir(parents=True, exist_ok=True)
            Path(dump_path).write_text(_json.dumps(dump, indent=1))
            print(f"Wrote the {len(dump)} failing lineup(s) to {dump_path} — "
                  f"every hitter's three projected means, the sim's means and "
                  f"standard errors, the batting spot and the assumed vs "
                  f"realised plate appearances. That is the whole input to "
                  f"the disagreement, so it can be diagnosed off the slate "
                  f"instead of guessed at.")
        return 2
    print("GATE PASSES. The sim reproduces the board's own projections on "
          "live data — its joint distribution is now trustworthy input for "
          "the Parlay Zone (task #60).")
    return 0


if __name__ == "__main__":
    date = next((a for a in sys.argv[1:] if not a.startswith("-")),
                _dt.date.today().isoformat())
    _dump = next((a.split("=", 1)[1] for a in sys.argv[1:]
                  if a.startswith("--dump=")), None)
    if "--dump" in sys.argv[1:]:
        _dump = _dump or "data/sim_gate_failures.json"
    # A rare market is where a Monte Carlo is weakest: at 20,000 trials a
    # 0.06 home-run mean carries ~3% relative sampler error, which is half
    # the gate's tolerance before the model has said anything. Raising the
    # count separates a real bias from the sampler — slower, so it stays
    # opt-in rather than the nightly default.
    _trials = next((int(a.split("=", 1)[1]) for a in sys.argv[1:]
                    if a.startswith("--trials=")), 20000)
    raise SystemExit(run(date, _dump, _trials))
