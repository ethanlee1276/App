#!/usr/bin/env python3
"""League-wide injury boards → web/data/injuries.json.

One pull per league off ESPN's keyless injuries endpoint, each league
failing independently — a dead basketball feed must not blank the NFL
board. The JSON carries flat rows per sport; grouping by team and the
"fresh this week" cut are the page's job, because they are presentation.

    python3 injuries_build.py --out web/data/injuries.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from engine.sources.espninjuries import INJURY_TTL, LEAGUES, cache_age_s, \
    current_rows, drop_stale_returns, fetch_injuries, is_return, \
    parse_injuries
from engine.sources.fetch import DataUnavailable


def _age_text(seconds: float) -> str:
    """Plain English, because "10,842s" is not a thing anyone reads."""
    mins = seconds / 60
    if mins < 90:
        return f"{round(mins)} min"
    hours = mins / 60
    if hours < 36:
        return f"{round(hours)}h"
    return f"{round(hours / 24)}d"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/injuries.json")
    args = ap.parse_args(argv)

    sports: dict = {}
    notes: list[str] = []
    ages: dict = {}
    for league in LEAGUES:
        try:
            rows = parse_injuries(fetch_injuries(league))
            # One row per player — his CURRENT status. ESPN accumulates
            # every filing, and showing them all lets an old return notice
            # sit next to a live designation. Then the age cut: a stale
            # "Active" is a standing claim of health nobody re-verifies.
            sports[league] = drop_stale_returns(current_rows(rows))
        except DataUnavailable as exc:
            notes.append(f"{league}: {exc}")
            continue
        # How old the ROWS are, not how old this file is. A declining feed
        # is answered from cache with no error raised, so without this the
        # board wears a fresh timestamp over week-old data.
        age = cache_age_s(league)
        if age is not None:
            ages[league] = round(age)
            if age > INJURY_TTL * 2:
                notes.append(
                    f"{league}: served from cache — these rows are "
                    f"{_age_text(age)} old, so the feed has been declining. "
                    f"Run `python3 launch.py --injuries` to see the error.")
    board = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "status": "live" if sports else "unavailable",
        "notes": notes,
        # Per-league age of the data itself, in seconds. The page shows a
        # staleness banner off this; `generated_at` only says when the
        # file was written, which is not the same question.
        "ages_s": ages,
        "stale_after_s": INJURY_TTL * 2,
        "sports": sports,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace — same contract as the meme board: a page fetch must
    # see the old file or the new one, never a truncated middle.
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(board, indent=1))
    os.replace(tmp, out)
    counts = ", ".join(
        f"{k} {len(v)}" + (f" [{_age_text(ages[k])} old]"
                           if ages.get(k, 0) > INJURY_TTL * 2 else "")
        for k, v in sports.items()) or "none"
    print(f"Injuries: {counts}"
          + (f"  ({len(notes)} note(s))" if notes else ""))
    designations = sum(1 for v in sports.values() for r in v
                       if not is_return(r))
    returns = sum(len(v) for v in sports.values()) - designations
    print(f"  {designations} carrying a designation, {returns} cleared-to-play")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
