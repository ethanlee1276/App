#!/usr/bin/env python3
"""The prose lanes: the LLM narrates, the arithmetic decides.

    python3 prose.py --postmortem [--date 2026-08-03]  # paid: the diary
    python3 prose.py --brief                           # paid: weekly note
    python3 prose.py --triage                          # paid: watchlist → spec
    python3 prose.py --show                            # stored prose, free

The nightly postmortem and the weekly brief also run themselves from the
settle pass — one entry per night/week, skipped without a key, and
standing down once the month's LLM spend passes the cap (default $5.00;
QELLYS_LLM_CAP_USD overrides). This CLI is for running them by hand and
for the triage bench, which is manual on purpose: turning a watchlist
idea into a new miner dimension is a build decision, not a nightly chore.

No output here is ever a probability, a stake, or a gate — prose about
numbers the arithmetic already produced, on every sport we track.
"""

from __future__ import annotations

import argparse
import json

from engine import hypotheses as hyp
from engine import ledger
from engine import prose as P


def _print_entry(e: dict, label: str) -> None:
    if not e:
        print(f"  (no {label} stored yet)")
        return
    when = e.get("date") or e.get("week_of") or "?"
    print(f"\n  {label} · {when} · {e.get('model', '')}")
    print(f"  ── {e.get('headline', '')}")
    print(f"  {e.get('overall', '')}\n")
    for sp, note in sorted((e.get("by_sport") or {}).items()):
        print(f"    {sp.upper():<5} {note}")


def _spend_line() -> None:
    print(f"\nLLM spend: ${P.month_spent():.2f} of the ${P.cap_usd():.2f} "
          f"monthly cap · `python3 hypotheses.py --spend` for the ledger")


def main() -> None:
    ap = argparse.ArgumentParser(description="The prose lanes.")
    ap.add_argument("--postmortem", action="store_true")
    ap.add_argument("--date", default=None,
                    help="which night (default: latest with graded picks)")
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--triage", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if args.show:
        block = P.site_block()
        _print_entry(block.get("postmortem"), "nightly postmortem")
        _print_entry(block.get("brief"), "weekly brief")
        _spend_line()
        return

    if not (args.postmortem or args.brief or args.triage):
        print(__doc__.strip())
        return

    if not P.under_cap():
        # A human at the terminal outranks the cap, but not unknowingly.
        print(f"⚠️  the ${P.cap_usd():.2f} monthly cap is already spent "
              f"(${P.month_spent():.2f}) — this manual run bills past it.")

    lconn = ledger.connect()
    try:
        if args.postmortem:
            e = P.write_postmortem(lconn, args.date)
            _print_entry(e, "nightly postmortem")
        if args.brief:
            e = P.write_brief(lconn)
            _print_entry(e, "weekly brief")
        if args.triage:
            out = P.triage(lconn)
            print("\nTriage bench — watchlist ideas drafted into miner "
                  "dimensions:\n")
            for pr in out.get("proposals") or []:
                print(f"  ■ {pr.get('dimension', '')}")
                print(f"    bands:  {pr.get('bands', '')}")
                print(f"    needs:  {pr.get('data_needed', '')}")
                print(f"    from:   {pr.get('source', '')}")
                print(f"    why:    {pr.get('rationale', '')}\n")
            print("  Nothing here is built automatically — a spec becomes a "
                  "dimension only\n  when we decide to journal the data it "
                  "needs.")
    except P.ProseUnavailable as e:
        print(f"prose lane unavailable: {e}")
        return
    _spend_line()


if __name__ == "__main__":
    main()
