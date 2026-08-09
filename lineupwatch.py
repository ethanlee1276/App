#!/usr/bin/env python3
"""Rebuild the MLB board when the lineup cards actually post.

    python3 lineupwatch.py                  # check once, rebuild if warranted
    python3 lineupwatch.py --check          # report only, never build
    python3 lineupwatch.py --watch          # poll until the slate is set
    python3 lineupwatch.py --watch --every 10 --min-gap 25

WHY

§5 holds every MLB hitter prop until its lineup is posted, and the parlay
screen fails closed on it. So a board built in the early afternoon carries
one leg per game — the starting pitcher — and no same-game pair exists
anywhere on the slate, however many props are recommended. The Parlay Zone
then has nothing to offer but cross-game constructions, which §0.3 proves
singles beat. That is not the model failing; it is the clock. A build at
1pm and a build at 5pm are different boards from the same data.

Remembering to rebuild is exactly the kind of chore that should not
depend on remembering. This watches for the cards and rebuilds when they
land.

WHAT IT COSTS

Nothing, until it rebuilds. Lineups come from statsapi.mlb.com, which is
free and unmetered; only the rebuild spends Odds API credits. That
asymmetry is the whole design: poll as often as is useful, build as
rarely as is useful.

    --min-gap    minutes a rebuild must wait behind the previous one
    --max-builds ceiling for one run, so a pathological night cannot
                 drain the day's credits

A rebuild is triggered by cards that POSTED SINCE the board was built —
never by an absolute count, or every poll after the first would rebuild
forever.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

BOARD = Path("web/data/mlb_recommendations.json")
REBUILD = ["python3", "launch.py"]

#: Poll gap. The boxscore cache holds 300s, so anything under five minutes
#: re-reads the same file and learns nothing.
EVERY_MIN = 10
#: Minutes a rebuild waits behind the one before it. Cards trickle out over
#: an hour or more; rebuilding on each one would spend a day's credits to
#: learn what one build at the end would have said.
MIN_GAP_MIN = 25
#: Ceiling on rebuilds in a single run.
MAX_BUILDS = 3


def today() -> str:
    return dt.date.today().isoformat()


# --- reading the two sides ---------------------------------------------------
def posted_in_build(path: Path = BOARD) -> tuple[int, int, str]:
    """(posted, total, date) as the LAST BUILD saw it.

    Prefers the parlay screen's own census and falls back to counting the
    games array, so a board written before that field existed still reads.
    """
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (0, 0, "")
    games = d.get("games") or []
    pz = d.get("parlays") or {}
    if isinstance(pz.get("lineups_posted"), int) and pz.get("games_total"):
        return (pz["lineups_posted"], pz["games_total"], d.get("date", ""))
    return (sum(1 for g in games if g.get("lineups_confirmed")),
            len(games), d.get("date", ""))


def posted_live(date: str) -> tuple[int, int]:
    """(posted, total) from the free MLB Stats API, right now.

    Reads the same boxscore field the builder reads — an empty
    ``battingOrder`` IS the pre-lineup state — so this cannot disagree with
    what the next build will conclude. A game whose boxscore will not load
    counts as not posted: failing closed matches §5.
    """
    from engine.mlb import lineuptimes
    from engine.mlb.sources.mlbstats import STATS_BASE, _get_json
    from engine.mlb.sources.statslogs import fetch_boxscore

    sched = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&startDate={date}&endDate={date}",
        f"mlb_schedule_{date}.json", ttl=600)
    posted = total = 0
    for day in sched.get("dates", []) or []:
        for g in day.get("games", []) or []:
            total += 1
            pk = g.get("gamePk")
            if not pk:
                continue
            try:
                box = fetch_boxscore(pk)
            except Exception:
                continue
            up = bool(box.get("teams", {}).get("home", {}).get("battingOrder")
                      and box.get("teams", {}).get("away", {}).get("battingOrder"))
            # RECORD THE BOUNDARY WHILE WE ARE HERE. This loop already
            # knows which game and what its state is; it threw both away
            # and returned a count. §4's lineup-release move needs the
            # moment, and there was nowhere to get one.
            #
            # Noted on every look, not only the posted ones: a first
            # sighting with no previous observation has an unbounded
            # window, which is indistinguishable from a stale guess.
            try:
                lineuptimes.note_look(date, pk, up)
            except Exception:                               # noqa: BLE001
                pass        # bookkeeping must never break the poller
            if up:
                posted += 1
    return (posted, total)


# --- the decision, kept pure so it can be tested without a network ----------
def decide(live_posted: int, live_total: int, built_posted: int,
           built_date: str, date: str, builds_done: int,
           since_last_build_min: float | None,
           min_gap: int = MIN_GAP_MIN,
           max_builds: int = MAX_BUILDS) -> tuple[bool, str]:
    """Rebuild or not, and the reason either way."""
    if built_date and built_date != date:
        return True, (f"the board on disk is {built_date} and today is "
                      f"{date} — that is a stale slate, not a lineup gap")
    if not live_total:
        return False, "no MLB games scheduled today"
    if live_posted <= built_posted:
        return False, (f"{live_posted}/{live_total} posted; the board already "
                       f"has {built_posted} — nothing new to build on")
    if builds_done >= max_builds:
        return False, (f"{live_posted - built_posted} new card(s), but this "
                       f"run has already rebuilt {builds_done} time(s) — "
                       f"stopping rather than spending more credits")
    if since_last_build_min is not None and since_last_build_min < min_gap:
        return False, (f"{live_posted - built_posted} new card(s), but the "
                       f"last rebuild was {since_last_build_min:.0f}m ago and "
                       f"the floor is {min_gap}m — cards trickle out, and one "
                       f"build at the end beats six along the way")
    return True, (f"{live_posted - built_posted} lineup(s) posted since the "
                  f"board was built ({built_posted} → {live_posted} of "
                  f"{live_total})")


def settled(live_posted: int, live_total: int) -> bool:
    """Every card is out — there is nothing further to wait for."""
    return bool(live_total) and live_posted >= live_total


def rebuild(cmd: list, dry_run: bool = False) -> int:
    print(f"  → {' '.join(cmd)}")
    if dry_run:
        print("    (--dry-run: not executed)")
        return 0
    return subprocess.call(cmd)


def run_once(date: str, board: Path, builds_done: int,
             last_build: float | None, args) -> tuple[bool, bool]:
    """(rebuilt, slate_is_settled)."""
    built_posted, built_total, built_date = posted_in_build(board)
    try:
        live_posted, live_total = posted_live(date)
    except Exception as exc:
        print(f"  could not reach the MLB Stats API: {exc}")
        return (False, False)
    gap = None if last_build is None else (time.time() - last_build) / 60.0
    go, why = decide(live_posted, live_total, built_posted, built_date, date,
                     builds_done, gap, args.min_gap, args.max_builds)
    stamp = dt.datetime.now().strftime("%H:%M")
    print(f"[{stamp}] lineups {live_posted}/{live_total} live · "
          f"{built_posted}/{built_total or '?'} on the board")
    print(f"          {why}")
    if go and not args.check:
        code = rebuild(REBUILD, args.dry_run)
        if code != 0:
            print(f"          rebuild exited {code}")
            return (False, settled(live_posted, live_total))
        return (True, settled(live_posted, live_total))
    return (False, settled(live_posted, live_total))


def main(argv: list) -> int:
    p = argparse.ArgumentParser(
        description="Rebuild the MLB board when lineup cards post.")
    p.add_argument("--check", action="store_true",
                   help="report only; never rebuild")
    p.add_argument("--watch", action="store_true",
                   help="keep polling until every card is out")
    p.add_argument("--every", type=int, default=EVERY_MIN,
                   help=f"minutes between polls (default {EVERY_MIN}; the "
                        f"boxscore cache is 5m, so less learns nothing)")
    p.add_argument("--min-gap", type=int, default=MIN_GAP_MIN,
                   help=f"minutes between rebuilds (default {MIN_GAP_MIN})")
    p.add_argument("--max-builds", type=int, default=MAX_BUILDS,
                   help=f"rebuild ceiling for this run (default {MAX_BUILDS})")
    p.add_argument("--date", default=today(), help="slate date (default today)")
    p.add_argument("--board", default=str(BOARD), help="built board JSON")
    p.add_argument("--dry-run", action="store_true",
                   help="say what it would run, and do not run it")
    args = p.parse_args(argv)

    board = Path(args.board)
    builds = 0
    last_build: float | None = None

    while True:
        did, done = run_once(args.date, board, builds, last_build, args)
        if did:
            builds += 1
            last_build = time.time()
        if not args.watch:
            return 0
        if done:
            print("          every card is out — nothing left to wait for.")
            return 0
        if builds >= args.max_builds:
            print(f"          hit the {args.max_builds}-rebuild ceiling; "
                  f"stopping. Re-run to keep watching.")
            return 0
        try:
            time.sleep(max(60, args.every * 60))
        except KeyboardInterrupt:
            print("\nstopped.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
