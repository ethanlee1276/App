#!/usr/bin/env python3
"""Pull and show the NFL preseason schedule. Writes nothing but a cache.

RETIRED FROM THE SITE 2026-08-25. Ethan: "get rid of the pre season
section for nfl. No need too have it anymore, I'd rather just be
prepared for the regular season to start." The launcher no longer calls
this, the page block is gone, and nfl_preseason.json is deregistered
from the gate (maintenance removes stale copies). This CLI and the
modules it drives (engine/sources/nflpreseason, engine/nfl/prestarters,
prelines, prefit) stay in the tree, dormant, because next July somebody
will want them again and they were measured, not guessed, the first
time they were built.

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
            # Label from `state`, not from the presence of a number: ESPN
            # supplies 0-0 for anything unplayed, so "has a score" is not
            # the same question as "has been played".
            score = ""
            if g["state"] == "post":
                score = f"   {g['away_score']}-{g['home_score']}  final"
            elif g["state"] == "in":
                score = f"   {g['away_score']}-{g['home_score']}  LIVE"
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


def write_board(season: int, out: str) -> int:
    """Write the fixture list where the website reads it.

    Separate from `report` so the terminal view and the page cannot drift:
    both call `preseason_games`, and this one hands the same list to
    `board_payload` without touching it.
    """
    import json
    import pathlib
    try:
        games = pre.preseason_games(season)
    except DataUnavailable as exc:
        print(f"  preseason      : no {season} schedule — {str(exc).splitlines()[0]}")
        return 2
    path = pathlib.Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pre.board_payload(games, season)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    span = f"{payload['first']} → {payload['last']}"
    print(f"  preseason      : {payload['total']} game(s), {span}, "
          f"{payload['complete']} final → {path}")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, default=_dt.date.today().year)
    p.add_argument("--raw", action="store_true",
                   help="say where the cached ESPN payloads landed")
    p.add_argument("--probe", action="store_true",
                   help="try several query shapes and a control year, to "
                        "tell a wrong query from an unpublished schedule")
    p.add_argument("--out", default="",
                   help="write the fixture list as JSON for the website "
                        "(e.g. web/data/nfl_preseason.json)")
    a = p.parse_args(argv)
    if a.probe:
        return probe(a.season)
    if a.out:
        return write_board(a.season, a.out)
    return report(a.season, a.raw)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
