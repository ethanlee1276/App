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
    return out


def run(date: str) -> int:
    from engine.mlb.sources.statslogs import build_live_slate
    try:
        slate = build_live_slate(date)
    except Exception as exc:                       # noqa: BLE001
        print(f"no slate for {date}: {exc}")
        return 1

    lineups = _lineups(slate)
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
        rates.sort(key=lambda r: r.spot or 9)
        fitted = G.calibrate(rates, targets)
        sim = G.simulate_lineup(fitted, [], trials=20000)
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
                print(f"       {o['player']:<22} {o['market']:<12} "
                      f"projected {o['projected']} simulated {o['simulated']}")

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
        return 2
    print("GATE PASSES. The sim reproduces the board's own projections on "
          "live data — its joint distribution is now trustworthy input for "
          "the Parlay Zone (task #60).")
    return 0


if __name__ == "__main__":
    date = next((a for a in sys.argv[1:] if not a.startswith("-")),
                _dt.date.today().isoformat())
    raise SystemExit(run(date))
