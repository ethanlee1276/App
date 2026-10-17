#!/usr/bin/env python3
"""Run every walk-forward harness and publish The Lab's page data.

    python3 backtest_lab.py             # run if a week has passed
    python3 backtest_lab.py --force     # run now regardless
    python3 backtest_lab.py --no-nfl    # skip the slow NFL stats replay

Writes web/data/backtest.json, which the site's Lab page renders. This
normally runs itself weekly from the maintenance pass (see engine.lab);
the CLI is for when you want the numbers immediately.
"""

from __future__ import annotations

import argparse
import json

from engine import lab


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="run even if the last run was less than a week ago")
    ap.add_argument("--no-nfl", action="store_true",
                    help="skip the NFL prop replay (needs a weekly-stats CSV)")
    ap.add_argument("--out", default=None, help="write somewhere else")
    args = ap.parse_args()

    status = lab.run_if_due(force=args.force, nfl=not args.no_nfl,
                            path=args.out)
    if status == "already":
        print(f"Already run within {lab.LAB_EVERY_DAYS} days — pass --force "
              f"to re-run.")
        return
    if status != "ok":
        print(f"Lab did not run ({status}).")
        return

    data = json.loads((__import__("pathlib").Path(
        args.out or lab.LAB_PATH)).read_text())
    for sport, s in data["sports"].items():
        props, games = s["props"], s["game_lines"]
        print(f"\n{sport.upper()}")
        for m in props.get("markets") or []:
            sk = m.get("skill") or {}
            print(f"  props · {m['label']:<16} n={m['n']:<6} "
                  f"MAE {m['mae']}  Brier {m['brier']}  "
                  f"skill {sk.get('skill', 0):+.1%}  [{m['basis']}]")
        if props.get("unavailable"):
            print(f"  props · — {props['unavailable']}")
        for g in games.get("markets") or []:
            print(f"  lines · {g['market']:<16} "
                  f"{g['games_priced']} priced, {g['n_bets']} bets, "
                  f"ROI {(g['roi'] or 0):+.1%}")
        if games.get("unavailable"):
            print(f"  lines · — {games['unavailable']}")
    print(f"\n{data['basis_note']}")


if __name__ == "__main__":
    main()
