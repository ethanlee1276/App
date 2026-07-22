#!/usr/bin/env python3
"""Bet-tracking ledger + bankroll CLI — the self-evaluation loop.

    python3 ledger.py bankroll --set 1000 --unit 1   # $1000 roll, 1%/unit
    python3 ledger.py log --sport nfl                 # log today's recommended bets
    python3 ledger.py settle --sport nfl --actuals results.json
    python3 ledger.py report                          # record, ROI, bankroll, CLV
    python3 ledger.py demo                             # runnable end-to-end demo

``log`` records the model's recommended picks; ``settle`` grades open bets once
you have results (an actuals JSON of {"Player|market": value}); ``report`` shows
running performance and bankroll. ``demo`` logs the sample slate and settles it
with simulated outcomes so you can see the whole loop without live data.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from engine import ledger
from engine.pipeline import run_slate
from engine.mlb.pipeline import run_mlb_slate

ROOT = Path(__file__).parent
SLATES = {"nfl": (ROOT / "data" / "sample_slate.json", run_slate),
          "mlb": (ROOT / "data" / "mlb_sample_slate.json", run_mlb_slate)}


def _result(sport: str) -> dict:
    slate, runner = SLATES[sport]
    return runner(slate)


def cmd_bankroll(conn, args):
    if args.set is not None or args.unit is not None:
        ledger.configure_bankroll(conn, starting=args.set, unit_pct=args.unit)
    print(f"Bankroll ${ledger.bankroll(conn):.2f} · unit "
          f"{ledger.get_cfg(conn, 'unit_pct')}% of bankroll "
          f"(start ${ledger.get_cfg(conn, 'starting_bankroll')})")


def cmd_log(conn, args):
    n = ledger.log_recommendations(conn, _result(args.sport))
    print(f"Logged {n} new {args.sport.upper()} pick(s).")
    print(ledger.summary(conn, args.sport))


def cmd_settle(conn, args):
    raw = json.loads(Path(args.actuals).read_text())
    # accept {"Player|market": value} or {"player": ..., "market": ..., "value": ...}
    actuals = {tuple(k.split("|", 1)): float(v) for k, v in raw.items()} if isinstance(raw, dict) \
        else {(r["player"], r["market"]): float(r["value"]) for r in raw}
    n = ledger.settle(conn, actuals, sport=args.sport)
    print(f"Settled {n} bet(s).")
    print(ledger.summary(conn, args.sport))


def cmd_report(conn, args):
    print(ledger.summary(conn, args.sport))


def cmd_demo(conn, args):
    rng = random.Random(7)
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    print("Demo: $1000 bankroll, 1% per unit. Logging the NFL sample slate…\n")
    result = _result("nfl")
    ledger.log_recommendations(conn, result)
    # Simulate outcomes from each pick's own hit probability + a closing line.
    actuals, closing = {}, {}
    for r in result["recommendations"]:
        if not r["recommended"]:
            continue
        key = (r["player"], r["market"])
        hit = rng.random() < r["hit_prob"]
        margin = abs(rng.gauss(0, 1)) + 0.5
        actuals[key] = r["line"] + (margin if hit else -margin)
        closing[key] = r["line"] + rng.choice([-1, -0.5, 0.5, 1])   # CLV
    ledger.settle(conn, actuals, closing=closing)
    print(ledger.summary(conn, "nfl"))
    print("\n(simulated outcomes — run `log` then `settle` with real results for a live ledger)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Bet-tracking ledger + bankroll.")
    ap.add_argument("--db", default=str(ledger.DEFAULT_DB))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bankroll"); p.add_argument("--set", type=float); p.add_argument("--unit", type=float)
    p = sub.add_parser("log"); p.add_argument("--sport", choices=["nfl", "mlb"], default="nfl")
    p = sub.add_parser("settle"); p.add_argument("--sport", choices=["nfl", "mlb"], default="nfl"); p.add_argument("--actuals", required=True)
    p = sub.add_parser("report"); p.add_argument("--sport", choices=["nfl", "mlb"], default=None)
    sub.add_parser("demo")
    args = ap.parse_args()

    conn = ledger.connect(args.db)
    {"bankroll": cmd_bankroll, "log": cmd_log, "settle": cmd_settle,
     "report": cmd_report, "demo": cmd_demo}[args.cmd](conn, args)


if __name__ == "__main__":
    main()
