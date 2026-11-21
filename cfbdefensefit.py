#!/usr/bin/env python3
"""Re-measure the college matchup (engine/cfb/defensefit.py) from our own logs.

    python3 cfbdefensefit.py                     # every complete stored season, each held out
    python3 cfbdefensefit.py --seasons 2022-2025 --db data/history.db

Prints, per market and position, the held-out gain of each rating (his own
position's, and overall pass defence) by season, which one the rule picks,
the transfer b it fits, and what engine/defensevs.MODEL_STAT_CFB and
TRANSFER_CFB ship. Change those only when a re-run says to.
"""
from __future__ import annotations

import argparse

from engine import db
from engine.cfb import defensefit as F


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args()
    conn = db.connect(args.db)
    if args.seasons:
        a, _, b = args.seasons.partition("-")
        years = list(range(int(a), int(b or a) + 1))
    else:
        years = [r[0] for r in conn.execute(
            "SELECT season FROM games WHERE sport='cfb' AND spread IS NOT NULL GROUP BY season "
            "HAVING COUNT(*) >= 500 ORDER BY season")]
    if len(years) < 2:
        raise SystemExit("need two seasons of college games with closing lines "
                         "(python3 ingest.py cfbhist --seasons 2022-2025)")
    by_season = {s: F.samples(conn, s) for s in years}
    for (m, g), res in F.study(by_season).items():
        stat, b = F.in_use(m, g)
        print(f"{m:<11}{g:<3} n {res['own']['n']:>6}   picks: {res['choice'] or 'nothing'}   "
              f"in use: {stat or '—'} × {b:.2f}")
        for opt in F.OPTIONS:
            r = res[opt]
            print(f"      {opt:<5} b {r['b']:+.2f}   held out " + "  ".join(f"{100 * x:+.2f}%" for x in r["per"])
                  + f"   mean {100 * r['mean']:+.2f}%")
    print("\nThe NFL's spread and total rules on college (off for college since 2026-09-23):")
    for (m, g), per in F.nfl_rules(by_season).items():
        if m != "anytime_td":
            print(f"  {m:<11}{g:<3} " + "  ".join(f"{100 * x:+.2f}%" for x in per))


if __name__ == "__main__":
    main()
