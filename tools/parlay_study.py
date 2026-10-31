#!/usr/bin/env python3
"""What pairing our past picks into two-leg parlays would have done — the
study behind the Parlays page (engine/twoleg).

    cd /srv/qellys && sudo -u qellys python3 tools/parlay_study.py
    python3 tools/parlay_study.py --db some/copy.db      # a saved journal

Ethan, 2026-10-31: "go back and see what would have happened if we did
parlay our past picks together and record that". Every graded day of the
headline record, paired the way tonight's board pairs (twoleg.candidates,
then choose: same-game pairs that make sense and two-game pairs, a few of
each, every pick once), graded off the picks' own results at the parlay's
price, one unit a parlay, next to the same picks bet singly.

WHAT IT PRINTS:

  1. the backtest by league, pool (Edge, Most Likely) and kind (same game,
     two games), as the Record page shows it;
  2. the same with one, two and three parlays of each kind a day: if the
     best one or two do better than three, the board should post fewer;
  3. the two halves of the record, either side of 2026-10-15 (the stake
     study's split): a pool that pays in one half only is not yet a finding;
  4. the parlays the board has journaled live, graded so far.

Read-only: it reads the journal and the history database's schedule (to
tell one game's two sides from two games) and writes nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger, twoleg as T                             # noqa: E402

SPLIT = "2026-10-15"
POOL_WORD = {"edge": "Edge", "likely": "Most Likely"}
KIND_WORD = {"all": "every pair", T.SAME_GAME: "same game", T.TWO_GAME: "two games"}


def schedule(since: str | None) -> dict:
    """{(sport, day, team): opponent} from the history database, or {}."""
    try:
        from engine import db
        if not db.DEFAULT_DB.exists():
            return {}
        h = db.connect()
        try:
            return T.schedule(h, since)
        finally:
            h.close()
    except Exception:                                         # noqa: BLE001
        return {}


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:+.1f}%"


def table(bt: dict, kinds=("all", T.SAME_GAME, T.TWO_GAME)) -> list[str]:
    out = [f"  {'league':<6} {'pool':<12} {'kind':<11} {'parlays':>7} {'both hit':>8} "
           f"{'units':>8} {'ROI':>8} {'singles':>8}"]
    order = ["all"] + list(T.SPORTS)
    rows = sorted((r for r in bt.get("rows") or [] if r["kind"] in kinds),
                  key=lambda r: (order.index(r["sport"]) if r["sport"] in order else 99,
                                 r["pool"], list(KIND_WORD).index(r["kind"])))
    for r in rows:
        out.append(f"  {r['sport'].upper():<6} {POOL_WORD.get(r['pool'], r['pool']):<12} "
                   f"{KIND_WORD.get(r['kind'], r['kind']):<11} {r['parlays']:>7} "
                   f"{r['win_rate'] * 100:>7.1f}% {r['units']:>+8.2f} {_pct(r['roi']):>8} "
                   f"{_pct(r['singles_roi']):>8}")
    if len(out) == 1:
        out.append("  (no graded day pairs yet)")
    return out


def overall(bt: dict) -> dict:
    """{pool: the all-leagues, every-pair row}."""
    return {r["pool"]: r for r in bt.get("rows") or [] if r["sport"] == "all" and r["kind"] == "all"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", help="the journal to read (default: the live one)")
    ap.add_argument("--since", default=ledger.RECORD_EPOCH,
                    help=f"first day (default: the record's epoch, {ledger.RECORD_EPOCH})")
    args = ap.parse_args(argv)
    conn = ledger.connect(args.db) if args.db else ledger.connect()
    games = schedule(args.since)
    print(f"Two-leg parlays from our past picks, since {args.since}. "
          f"Schedule: {len(games) // 2 if games else 0} games "
          f"({'one game told from two' if games else 'none read: only teammates count as one game'}).")
    print("Graded at the parlay's price, one unit a parlay; 'singles' is the same picks bet singly.")

    bt = T.backtest(conn, since=args.since, games=games)
    print(f"\n1. As the Record page shows it ({bt['per_kind']} of each kind a day):")
    print("\n".join(table(bt)))

    print("\n2. How many a day (every league, every pair):")
    print(f"  {'a day':<8} {'pool':<12} {'parlays':>7} {'both hit':>8} {'units':>8} {'ROI':>8} {'singles':>8}")
    for n in (1, 2, 3):
        for pool, r in sorted(overall(T.backtest(conn, since=args.since, games=games, per_kind=n)).items()):
            print(f"  {n} each   {POOL_WORD[pool]:<12} {r['parlays']:>7} {r['win_rate'] * 100:>7.1f}% "
                  f"{r['units']:>+8.2f} {_pct(r['roi']):>8} {_pct(r['singles_roi']):>8}")

    print(f"\n3. The two halves, either side of {SPLIT}:")
    for label, since, until in ((f"before {SPLIT}", args.since, SPLIT), (f"from {SPLIT}", SPLIT, None)):
        half = T.backtest(conn, since=since, games=games, until=until)
        print(f"  {label}:")
        print("\n".join("  " + line for line in table(half, kinds=("all",))))

    print("\n4. The parlays the board has journaled live:")
    try:
        from engine import parlayledger
        rep = parlayledger.report_twoleg(conn, recent=0)
        for pool in ("edge", "likely"):
            r = rep.get(pool) or {}
            if not r.get("graded") and not r.get("open"):
                print(f"  {POOL_WORD[pool]}: none yet (they journal with each night's board).")
                continue
            print(f"  {POOL_WORD[pool]}: {r['wins']}-{r['losses']}, {r['net_units']:+.2f}u at one unit a "
                  f"ticket ({_pct(r['roi'])}), {r.get('open', 0)} open; staked {r['staked_units']:.1f}u, "
                  f"{r['staked_net']:+.2f}u")
            for k, t in sorted((r.get("by_kind") or {}).items()):
                print(f"    {KIND_WORD.get(k, k)}: {t['wins']}-{t['losses']}, {t['net_units']:+.2f}u")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  could not read them: {type(exc).__name__}: {exc}")
    print("\n" + bt["rule"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
