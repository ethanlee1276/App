#!/usr/bin/env python3
"""Pull and show the NFL preseason schedule. Writes nothing but a cache.

    python3 nflpre.py                 # this year's preseason
    python3 nflpre.py --season 2026
    python3 nflpre.py --raw           # also print where the payloads landed

The main board cannot show preseason at all: it reads nflverse's
games.csv, which carries REG, WC, DIV, CON and SB and nothing else. This
goes to ESPN, which does list it.

IT DOES NOT PRICE ANYTHING, on purpose. Preseason is where this engine's
premise breaks — a projection is volume times efficiency over prior games,
and in August a starter plays a series and a half behind a line that will
not start together again. A prop priced off last season's usage is not a
worse number, it is a number about a different event. Schedules and scores
are worth showing; props are not, and keeping them apart is what stops the
first quietly turning into the second.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from engine.sources.fetch import CACHE_DIR, DataUnavailable
from engine.sources import nflpreseason as pre


def report(season: int, show_raw: bool = False) -> int:
    try:
        games = pre.preseason_games(season)
    except DataUnavailable as exc:
        print(f"\nNo preseason schedule for {season}.\n")
        print(exc)
        print("\nThis machine needs to reach site.api.espn.com. It is refused "
              "by policy in the cloud container, so run this locally.")
        return 2

    span = pre.window(games)
    left = pre.days_until(games)
    print("=" * 70)
    print(f"NFL PRESEASON {season} — {len(games)} games, {span[0]} to {span[1]}")
    print("=" * 70)
    if left is not None:
        if left > 0:
            print(f"  First kickoff in {left} day(s).")
        elif left == 0:
            print("  First kickoff is today.")
        else:
            print(f"  Started {-left} day(s) ago.")
    print()

    by_week: dict = {}
    for g in games:
        by_week.setdefault(g["week"], []).append(g)
    for wk in sorted(by_week, key=lambda w: (w is None, w)):
        rows = by_week[wk]
        print(f"  Week {wk if wk is not None else '?'} — {len(rows)} game(s)")
        for g in rows:
            score = ""
            if g["home_score"] is not None and g["away_score"] is not None:
                score = f"   {g['away_score']}-{g['home_score']}"
                if not g["completed"]:
                    score += " (live)"
            roof = " · indoor" if g["indoor"] else ""
            print(f"    {g['date']}  {g['away']:>3} @ {g['home']:<3}"
                  f"{score}{roof}")
        print()

    done = sum(1 for g in games if g["completed"])
    print(f"  {done} of {len(games)} complete.")
    print()
    print("  Schedules and scores only. Nothing here is priced, and the")
    print("  board's projections are not valid for preseason usage — see")
    print("  this file's docstring.")
    if show_raw:
        print()
        print(f"  Raw payloads cached under {CACHE_DIR}")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, default=_dt.date.today().year)
    p.add_argument("--raw", action="store_true",
                   help="say where the cached ESPN payloads landed")
    a = p.parse_args(argv)
    return report(a.season, a.raw)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
