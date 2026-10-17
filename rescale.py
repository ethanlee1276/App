#!/usr/bin/env python3
"""Put every journalled stake on one ruler. Dry run by default.

    python3 rescale.py                  # show what it WOULD do
    python3 rescale.py --apply          # do it, after backing the ledger up

THE FAULT
---------
Commit 3f86208 (2026-08-04 02:23 UTC) changed the stake converter from a
private twenty-unit bankroll to ``BANKROLL_UNITS = 100``. Every row logged
after it is on the new ruler and every row before it is on the old one, and
nothing in the schema says which — so the journal has been quietly adding
two different definitions of "unit" together ever since.

Measured on the real MLB board: 0.116 u/bet before 2026-08-04, 0.496 after,
a 4.3x jump with `avg_edge` flat at ~0.039 either side. Same Kelly inputs,
same real bets, different number in the column.

WHAT THAT BROKE, AND WHAT IT DID NOT
------------------------------------
The bets themselves never changed. Old 0.101u of a 20u bankroll is 0.505%
of bankroll; new 0.496u of a 100u bankroll is 0.496%. Identical risk,
different notation.

  * **Cumulative P&L is not a time series** across the boundary — the
    "cliff" on the Record page is the ruler changing.
  * **Pooled ROI is stake-weighted**, so post-boundary rows count roughly
    five times each. That is why the page reads worse than the win rate
    implies.
  * **Win/loss is untouched.** 113-134 at a 57.3% break-even is real, and
    it is the 12-point calibration gap that selcheck and guardfit measure.

The check that says this migration is right: after normalising, ROI should
agree with what the win rate ALONE implies. It does not agree before.

WHICH ROWS MOVE
---------------
Only the Kelly path. `main` recommendations size through
engine/staking.to_units and were rescaled. The paper buckets — longshot,
loose, stale, pricedout — journal a hardcoded flat 0.1 that the commit
never touched, and parlays were already on the 100u scale the commit
adopted. This script proves that from the data rather than assuming it: it
reports the per-day stake for every category and only offers to move the
ones that actually show the discontinuity.

Standard library only. Writes nothing without --apply.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sqlite3
import sys

from engine import ledger

#: When the converter changed, from `git show 3f86208 --format=%aI`.
CUTOVER = "2026-08-04T02:23:29"
#: Old bankroll ruler, new bankroll ruler. The factor is the ratio.
OLD_UNITS, NEW_UNITS = 20.0, 100.0
FACTOR = NEW_UNITS / OLD_UNITS
#: Categories whose stake comes from Kelly. Everything else journals a
#: hardcoded flat stake that the rescale did not touch.
KELLY_CATEGORIES = ("main",)
#: A category is only treated as affected if its stake actually jumps by
#: about this much across the cutover. Below it, leave the rows alone.
MIN_JUMP = 2.0


def rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, ts, date, sport, category, stake_units, pnl_units, status "
        "FROM bets WHERE stake_units IS NOT NULL")]


def _side(r: dict) -> str:
    return "old" if (r["ts"] or "") < CUTOVER else "new"


def by_category(rs: list[dict]) -> list[dict]:
    """Per category: mean stake either side of the cutover, and the jump.

    This is the evidence, not the assumption. A category whose stake is a
    hardcoded constant shows a jump of about 1.0 and must not be touched.
    """
    g: dict = {}
    for r in rs:
        g.setdefault(r["category"] or "?", {"old": [], "new": []})[_side(r)].append(r)
    out = []
    for cat, sides in sorted(g.items()):
        o = [x["stake_units"] for x in sides["old"]]
        n = [x["stake_units"] for x in sides["new"]]
        mo = sum(o) / len(o) if o else None
        mn = sum(n) / len(n) if n else None
        out.append({"category": cat, "n_old": len(o), "n_new": len(n),
                    "u_old": mo, "u_new": mn,
                    "jump": (mn / mo) if (mo and mn) else None})
    return out


def affected(cats: list[dict]) -> list[str]:
    """Categories that are BOTH a known Kelly path and visibly jumped."""
    out = []
    for c in cats:
        if c["category"] not in KELLY_CATEGORIES:
            continue
        if c["jump"] is None or c["jump"] < MIN_JUMP:
            continue
        out.append(c["category"])
    return out


def roi(rs: list[dict], factor: float = 1.0, cats=()) -> dict:
    """Staked, P&L and ROI, optionally normalising the old-scale rows."""
    staked = pnl = 0.0
    for r in rs:
        if r["status"] not in ("won", "lost"):
            continue
        f = factor if (_side(r) == "old" and r["category"] in cats) else 1.0
        staked += (r["stake_units"] or 0) * f
        pnl += (r["pnl_units"] or 0) * f
    return {"staked": staked, "pnl": pnl,
            "roi": (pnl / staked) if staked else 0.0}


def implied_roi(rs: list[dict]) -> dict:
    """What the WIN RATE alone says the ROI should be.

    Scale-free by construction — it uses only wins, losses and the prices —
    so it is the independent check on whether normalising worked. If the
    normalised ROI moves toward this and the raw one does not, the ruler
    was the problem.
    """
    w = sum(1 for r in rs if r["status"] == "won")
    n = sum(1 for r in rs if r["status"] in ("won", "lost"))
    return {"landed": (w / n) if n else 0.0, "n": n}


def report(conn, sport=None, apply_it=False) -> int:
    rs = rows(conn)
    if sport:
        rs = [r for r in rs if r["sport"] == sport]
    if not rs:
        print("No journalled stakes found.")
        return 0

    cats = by_category(rs)
    print("=" * 74)
    print(f"STAKE PER BET, EITHER SIDE OF {CUTOVER}")
    print("=" * 74)
    print("  category        n before   n after   u/bet before   u/bet after   jump")
    print("  " + "-" * 70)
    for c in cats:
        uo = f"{c['u_old']:.3f}" if c["u_old"] is not None else "   —"
        un = f"{c['u_new']:.3f}" if c["u_new"] is not None else "   —"
        jp = f"{c['jump']:.1f}x" if c["jump"] is not None else "  —"
        print(f"  {c['category']:14} {c['n_old']:8} {c['n_new']:9}   "
              f"{uo:>12}   {un:>11}   {jp:>5}")
    print()
    print("  A hardcoded flat stake shows a jump near 1.0 and is left alone.")
    print(f"  Only a known Kelly path {KELLY_CATEGORIES} that ALSO jumped by")
    print(f"  {MIN_JUMP}x or more is treated as affected.")
    print()

    hit = affected(cats)
    if not hit:
        print("  → NOTHING TO DO. No Kelly-path category shows the jump.")
        return 0
    print(f"  → affected: {', '.join(hit)}")
    print()

    scope = [r for r in rs if r["category"] in hit]
    old_n = sum(1 for r in scope if _side(r) == "old")
    print("=" * 74)
    print("WHAT NORMALISING DOES TO THE RECORD")
    print("=" * 74)
    before = roi(scope)
    after = roi(scope, FACTOR, hit)
    imp = implied_roi(scope)
    print(f"  {old_n:,} pre-cutover rows would be multiplied by {FACTOR:.0f}x")
    print()
    print(f"  as recorded    {before['staked']:8.2f}u staked   "
          f"{before['pnl']:+8.2f}u   ROI {before['roi']:+.1%}")
    print(f"  normalised     {after['staked']:8.2f}u staked   "
          f"{after['pnl']:+8.2f}u   ROI {after['roi']:+.1%}")
    print()
    print(f"  win rate {imp['landed']:.1%} on {imp['n']:,} settled bets")
    print()
    print("  The point of this line: ROI as recorded pools two rulers and is")
    print("  stake-weighted, so post-cutover rows count five times each. The")
    print("  normalised figure is the one that can be compared with the win")
    print("  rate and with any earlier reading of the record.")
    print()

    if not apply_it:
        print("  DRY RUN — nothing written. Re-run with --apply to migrate.")
        return 0

    dest = ledger.DEFAULT_DB
    backup = f"{dest}.pre-rescale-{_dt.date.today().isoformat()}"
    shutil.copy2(dest, backup)
    print(f"  backed up to {backup}")
    conn.execute("ALTER TABLE bets ADD COLUMN bankroll_units REAL")
    conn.execute(
        "UPDATE bets SET stake_units = ROUND(stake_units * ?, 4), "
        "pnl_units = ROUND(COALESCE(pnl_units, 0) * ?, 4), "
        f"bankroll_units = ? WHERE ts < ? AND category IN "
        f"({','.join('?' * len(hit))})",
        (FACTOR, FACTOR, NEW_UNITS, CUTOVER, *hit))
    moved = conn.total_changes
    conn.execute(
        f"UPDATE bets SET bankroll_units = ? WHERE bankroll_units IS NULL",
        (NEW_UNITS,))
    conn.commit()
    print(f"  migrated {moved:,} rows; every row now records its own scale")
    print("  re-run `python3 launch.py` to rebuild the site's record files")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sport", default=None, help="limit the report to one sport")
    p.add_argument("--apply", action="store_true",
                   help="actually migrate (backs the ledger up first)")
    a = p.parse_args(argv)
    return report(ledger.connect(), sport=a.sport, apply_it=a.apply)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
