#!/usr/bin/env python3
"""Which books actually came back, and what each one charges.

Ethan, 2026-09-15: "all the us books your using and shit, is that able
too be used for all sports if it makes sense and can save us api key
credits?" They can — the book list is a filter on a response already
paid for — and seven more were added on that argument the same day.

WHICH RAISES THE QUESTION THIS ANSWERS. A book key that does not resolve
on the live API is free in exactly the same way as one that does, and
worth nothing. From the board the two look identical: the price shown is
the best of whoever answered, and nobody can tell from it whether Novig
quoted and lost or was never there. This counts.

It also prints each book's MARGIN — what the two sides of its game
moneyline sum to. 1.00 is a venue taking no cut; 1.03 is the sharp
reference; 1.05 is an ordinary sportsbook. That ordering is the useful
part: it says where the thin prices live without asserting anything
about who is sharp, which is `engine/booksharp`'s separate question.

READ-ONLY, AND NOT ONE API CREDIT. It reads the payloads already on disk
under `data/cache` — the ones the builds paid for — so it is safe to run
on the production box at any time, mid-cycle included.

    python3 book_margins.py                 # every sport with cached odds
    python3 book_margins.py nfl mlb         # just these
    python3 book_margins.py --dir /srv/qellys/data/cache
    python3 book_margins.py --hours 12      # ignore payloads older than

WHAT A MISSING BOOK MEANS, before anyone acts on it: this reads CACHED
payloads, so a book absent here is a book absent from the pulls on
disk, which is not quite the same as a book the API refuses. A sport
whose newest payload predates the book being added will show every new
book as missing and be perfectly healthy. `--hours` is the guard, and
the age of each file is printed so the difference is visible rather
than inferred.

WHY IT LIVES AT THE ROOT: it is a droplet tool, the same family as
`potd_report.py`, `stale_lines.py` and `shopping_value.py`.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import bookvig                                    # noqa: E402

#: Where the builds write the payloads they bought.
DEFAULT_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "cache")


def sport_of(filename: str) -> str:
    """The league a cache file belongs to, from its own name.

    `oddsapi.event_cache_name` spells them `odds_event_{sport}_{id}_{tag}`
    and the board pulls `odds_board_{sport}[_tag]`, so the league is the
    third underscore-separated field in both. Read rather than guessed at
    because a mis-read here would file every sport under one heading and
    make the census look complete when it is one league repeated.
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    for prefix in ("odds_event_", "odds_board_"):
        if base.startswith(prefix):
            rest = base[len(prefix):]
            # THE EXTENSION COMES OFF FIRST, above. A board pull with no
            # cache tag is `odds_board_mlb.json` with nothing after the
            # league, so splitting the basename on "_" returned
            # "mlb.json" and every heading, every census key and the
            # `--sports` filter carried it. Caught by running the thing.
            return rest.split("_", 1)[0]
    return ""


def events_in(payload):
    """The event objects inside one cached payload, whatever its shape.

    A board pull is a LIST of events; an event pull is ONE event object.
    Both are stored under the same directory with the same extension, and
    a reader that assumed either shape would silently skip half the
    evidence — which for this tool means reporting a book as missing
    because its payloads happened to be the shape nobody handled.
    """
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [e for e in payload["data"] if isinstance(e, dict)]
        if payload.get("bookmakers") is not None:
            return [payload]
    return []


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:                                  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {exc}"}


def scan(cache_dir: str, sports=(), max_age_h: float = 0.0) -> dict:
    """``{sport: {"census", "files", "newest_age_h", "skipped"}}``.

    Every failure is counted rather than raised: this runs on a box whose
    cache is being rewritten underneath it, and half a census is worth
    more than a traceback.
    """
    out: dict = {}
    now = time.time()
    paths = sorted(glob.glob(os.path.join(cache_dir, "odds_*.json")))
    for path in paths:
        sport = sport_of(path)
        if not sport or (sports and sport not in sports):
            continue
        try:
            age_h = (now - os.path.getmtime(path)) / 3600.0
        except OSError:
            continue
        slot = out.setdefault(sport, {"census": bookvig.Census(), "files": 0,
                                      "newest_age_h": None, "skipped": 0,
                                      "events": 0, "unreadable": 0})
        if max_age_h and age_h > max_age_h:
            slot["skipped"] += 1
            continue
        payload = _load(path)
        if isinstance(payload, dict) and payload.get("__error__"):
            slot["unreadable"] += 1
            continue
        evs = events_in(payload)
        if not evs:
            slot["unreadable"] += 1
            continue
        slot["files"] += 1
        slot["events"] += len(evs)
        cur = slot["newest_age_h"]
        slot["newest_age_h"] = age_h if cur is None else min(cur, age_h)
        for ev in evs:
            # No team map: the census never names a side, so it does not
            # need one — see `bookvig.overrounds`. That is what lets this
            # cover college football and UFC, whose maps are runtime-built
            # and identity respectively.
            slot["census"].add_event(ev, {})
    return out


def render(found: dict, wanted) -> str:
    lines: list = []
    if not found:
        return ("No cached odds payloads found. Either no pull has run on "
                "this box, or --dir is pointing somewhere else — the builds "
                "write to data/cache beside the repo.")
    for sport in sorted(found):
        slot = found[sport]
        age = slot["newest_age_h"]
        head = (f"{sport.upper()}  {slot['files']} payload(s), "
                f"{slot['events']} event(s)")
        if age is not None:
            head += f", newest {age:.1f}h old"
        if slot["skipped"]:
            head += f"  ({slot['skipped']} too old to count)"
        if slot["unreadable"]:
            head += f"  ({slot['unreadable']} unreadable)"
        lines.append(head)
        lines.append(bookvig.report(slot["census"], sport, wanted=wanted))
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sports", nargs="*", help="leagues to report (default: all)")
    ap.add_argument("--dir", default=DEFAULT_CACHE, help="odds cache directory")
    ap.add_argument("--hours", type=float, default=0.0,
                    help="ignore payloads older than this many hours")
    args = ap.parse_args(argv)

    from engine.sources.oddsapi import DEFAULT_BOOKS
    found = scan(args.dir, tuple(s.lower() for s in args.sports), args.hours)
    print(render(found, DEFAULT_BOOKS))
    return 0


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(main())
