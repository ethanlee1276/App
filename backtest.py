#!/usr/bin/env python3
"""Backtest the model over historical nflverse weeks.

    python3 backtest.py 2024 --weeks 6-17
    python3 backtest.py 2023 --weeks 8,9,10 --min-confidence 7

Needs weekly stats for the season (release-gated → drop a CSV at
data/cache/player_stats_<season>.csv; see the README). Projections for each week
are built from prior weeks only (walk-forward), then settled against that week's
actual box score.
"""

from __future__ import annotations

import argparse
import sys

from engine.backtest import backtest_from_stats
from engine.sources.fetch import DataUnavailable
from engine.rules import RuleConfig


def parse_weeks(spec: str) -> list[int]:
    weeks: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            weeks.extend(range(int(a), int(b) + 1))
        elif part:
            weeks.append(int(part))
    return sorted(set(weeks))


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest & calibration report.")
    ap.add_argument("season", type=int)
    ap.add_argument("--weeks", default="6-17", help="e.g. 6-17 or 8,9,10")
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--model", default=None, help="Path to a trained model JSON (uses learned projections).")
    ap.add_argument("--team-context", action="store_true",
                    help="NFL Phase 2: price with measured pace / PROE / "
                         "offensive EPA, rebuilt walk-forward for each week.")
    ap.add_argument("--context-mode", default="level", choices=("level", "drift"),
                    help="level = tendency vs the league; drift = the team vs "
                         "its OWN season, i.e. only what player form has not "
                         "already absorbed.")
    ap.add_argument("--real-lines", action="store_true",
                    help="price against harvested closes from the history DB "
                         "instead of the recent-form proxy. Without this every "
                         "row is basis=naive, so --gate has no market-relative "
                         "arm to read and will say so.")
    ap.add_argument("--gate", action="store_true",
                    help="score the props the gate REFUSED against the ones "
                         "it admitted. The journal cannot answer this — it "
                         "only holds bets we placed — but the walk-forward "
                         "settles every candidate either way.")
    ap.add_argument("--gate-basis", default="book", choices=("book", "naive", ""),
                    help="which pricing basis --gate reads (default book). "
                         "naive rows were priced against the recent-form "
                         "proxy at a synthetic -110, so beating them says "
                         "nothing about beating a market.")
    args = ap.parse_args()

    weeks = parse_weeks(args.weeks)
    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)

    model = None
    if args.model:
        from engine.ml.model import MultiplierModel
        model = MultiplierModel.load(args.model)

    # THE JOIN THAT MAKES `--gate` MEAN ANYTHING. Without harvested
    # closes every prop is priced at `build_slate`'s recent-form proxy on
    # a synthetic -110, and both arms of the refusal audit are the model
    # scored against itself. `engine.lab.nfl_real_lines` is the same
    # builder the lab's own replay uses — one implementation, because the
    # second one is always the one that is wrong.
    real = None
    if args.real_lines:
        from engine import db as _db
        from engine.lab import nfl_real_lines
        real = nfl_real_lines(_db.connect())
        print(f"  harvested closes: {len(real):,} (player, market, date) keys")

    try:
        report = backtest_from_stats(args.season, weeks, config, model=model,
                                     use_team_context=args.team_context,
                                     team_context_mode=args.context_mode,
                                     real_lines=real)
    except DataUnavailable as exc:
        print("⚠️  Backtest needs weekly stats.\n")
        print(exc)
        sys.exit(2)

    print(f"\n{args.season} · weeks {weeks[0]}–{weeks[-1]} · {'learned model' if model else 'hand-tuned rules'}")
    print(report.summary())
    if report.n == 0:
        print("\n(No settled props — check that the stats CSV covers these weeks.)")
    if args.gate:
        gate_report(report, basis=args.gate_basis)


def gate_report(report, basis: str = "book") -> None:
    """Did the gate's refusals cost anything?

    `report.summary()` above measures the bets the gate ADMITTED, which
    is what a P&L is. It cannot say whether the board would have done
    better taking the props it turned down, because that arm has never
    been scored anywhere — the journal holds placed bets only, and every
    row in it was admitted by construction.

    The walk-forward settles the whole candidate surface, so the arm
    exists; this prints it.
    """
    from engine.selectorder import from_settled, gate_split, gate_reading
    res = gate_split(from_settled(report.settled), basis=basis)
    print(f"\n{'='*70}\n  WHAT HAPPENED TO THE PROPS THE GATE REFUSED"
          f"\n{'='*70}")
    if not res["enough"]:
        print(f"  {res['note']}.\n")
        return
    # THE HEADER SAYS WHICH BASIS IT READ. It said "priced against a
    # real book line" whatever `--gate-basis` was, so the proxy run
    # announced 2,529 book-priced rows it did not have — a false
    # sentence printed above a true table, which is the shape of every
    # wrong number this repo has had to chase.
    priced = ("against a real harvested book line" if res["basis"] == "book"
              else "against the recent-form proxy at a synthetic -110, "
                   "NOT a book" if res["basis"] == "naive"
              else "against a mix of book and proxy lines")
    print(f"  {res['n']} settled candidates priced {priced}, at one flat\n"
          f"  unit each. Same weeks, same prices, same settling — the only\n"
          f"  difference is which side of the gate they fell.\n")
    print(f"    {'arm':<12}{'bets':>6}{'won':>6}{'hit':>9}"
          f"{'staked':>10}{'net':>10}{'ROI':>9}")
    for name, key in (("admitted", "admitted"), ("refused", "refused")):
        r = res[key]
        hit = f"{r['hit']:.1%}" if r["hit"] is not None else "—"
        roi = f"{r['roi']:+.1%}" if r["roi"] is not None else "—"
        print(f"    {name:<12}{r['bets']:>6}{r['wins']:>6}{hit:>9}"
              f"{r['staked']:>10.1f}{r['net']:>+10.1f}{roi:>9}")
    d = res["diff"]["admitted-refused"]
    lo = "—" if d["lo"] is None else f"{d['lo']:+.1%}"
    hi = "—" if d["hi"] is None else f"{d['hi']:+.1%}"
    pt = "—" if d["point"] is None else f"{d['point']:+.1%}"
    print(f"\n  DIFFERENCE IN ROI, bootstrap within each arm")
    print(f"    admitted - refused   {pt}  [{lo}, {hi}]")
    print(f"\n  {gate_reading(res)}.\n")


if __name__ == "__main__":
    main()
