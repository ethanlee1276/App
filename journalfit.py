#!/usr/bin/env python3
"""Show or run the every-sport journal fitter.

    python3 journalfit.py            # fit whatever the journal now supports
    python3 journalfit.py --show     # what each sport is still collecting

This is the fitter for sports with no deep-history harness (NBA, WNBA,
CFB, UFC): temperatures from the journal's claimed probabilities and
player memory from its (projection, actual) pairs, both floor-gated at
200 settled bets per market. It also runs automatically on every settle
pass — this CLI exists so the collection progress is visible on demand.
"""

from __future__ import annotations

import argparse

from engine import journalfit as jf
from engine import ledger


def _print_block(name: str, res: dict) -> None:
    print(f"\n{name}:")
    for f in res["fitted"]:
        print(f"  fitted    {f['key']:22} n={f['n']:,}  " +
              (f"T={f['temperature']}" if "temperature" in f
               else f"adopted={f['adopted']} players={f['players']}"))
    for f in res["owned"]:
        print(f"  owned     {f['key']:22} (a deeper fitter holds this key)")
    for f in res["collecting"]:
        print(f"  collecting {f['key']:21} {f['n']}/{f['need']} settled bets")
    if not any(res.values()):
        print("  nothing in the journal yet")


def main() -> None:
    ap = argparse.ArgumentParser(description="Journal fitter, every sport.")
    ap.add_argument("--show", action="store_true",
                    help="dry-run: report progress without writing stores")
    args = ap.parse_args()

    lconn = ledger.connect()
    if args.show:
        # A dry run computes against the REAL stores (so ownership and
        # collection progress read true) but writes nothing.
        t = jf.fit_temperatures(lconn, dry_run=True)
        m = jf.fit_memory(lconn, dry_run=True)
    else:
        out = jf.refresh(lconn)
        t, m = out["temperatures"], out["memory"]
    _print_block("temperatures (claimed probability vs outcome)", t)
    _print_block("player memory (projection vs actual)", m)
    print("\nBoth fits also run automatically on every settle pass.")


if __name__ == "__main__":
    main()
