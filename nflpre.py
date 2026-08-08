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


def probe(season: int) -> int:
    """Try several query shapes, and a control year, and say which answered.

    This exists because the parser was written against an API that the
    cloud container is refused by policy, so "no games came back" has two
    very different causes and no way to tell them apart from here.

    The control is what separates them. If LAST season's preseason returns
    games and this one does not, the query shape is right and the schedule
    simply is not published. If neither returns anything, the shape is
    wrong and waiting will not fix it.
    """
    import json
    import urllib.request
    from engine.sources.livescores import ESPN_NFL

    shapes = [
        (f"{ESPN_NFL}?dates={season}&seasontype=1&week=1",
         "year + seasontype + week   (what nflpre uses)"),
        (f"{ESPN_NFL}?dates={season}&seasontype=1",
         "year + seasontype, no week"),
        (f"{ESPN_NFL}?seasontype=1&week=1",
         "seasontype + week, no year"),
        (f"{ESPN_NFL}?dates={season}0801-{season}0901",
         "explicit August date range"),
        (f"{ESPN_NFL}?dates={season - 1}&seasontype=1&week=1",
         f"CONTROL — {season - 1} preseason, a season that happened"),
        (f"{ESPN_NFL}?dates={season}&seasontype=2&week=1",
         f"CONTROL — {season} REGULAR season week 1"),
    ]
    print("=" * 74)
    print(f"PROBE — which ESPN query actually returns {season} preseason?")
    print("=" * 74)
    print()
    for url, label in shapes:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            data = json.loads(body)
            events = data.get("events")
            if events is None:
                print(f"  {'NO EVENTS KEY':>14}  {label}")
                print(f"  {'':>14}  keys: {sorted(data)[:8]}")
            else:
                n = len(events)
                first = ""
                if n:
                    e = events[0]
                    first = f"  first: {e.get('date', '')[:10]} {e.get('shortName', '')}"
                print(f"  {n:>10} games  {label}{first}")
        except Exception as exc:                              # noqa: BLE001
            print(f"  {'FAILED':>14}  {label}")
            print(f"  {'':>14}  {type(exc).__name__}: {str(exc)[:80]}")
        print(f"  {'':>14}  {url}")
        print()
    print("  READ IT LIKE THIS:")
    print(f"    control {season - 1} has games, {season} does not")
    print("        -> the query is right; the schedule is not out yet.")
    print("    no control returns anything")
    print("        -> the query shape is wrong, and waiting will not help.")
    print("    a different shape above returns games")
    print("        -> that is the one nflpre should be using. Send me the line.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, default=_dt.date.today().year)
    p.add_argument("--raw", action="store_true",
                   help="say where the cached ESPN payloads landed")
    p.add_argument("--probe", action="store_true",
                   help="try several query shapes and a control year, to "
                        "tell a wrong query from an unpublished schedule")
    a = p.parse_args(argv)
    if a.probe:
        return probe(a.season)
    return report(a.season, a.raw)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
