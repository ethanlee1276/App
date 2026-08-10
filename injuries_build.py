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
import sys
from pathlib import Path

from engine.sources.espninjuries import LEAGUES, fetch_injuries, \
    parse_injuries
from engine.sources.fetch import DataUnavailable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/injuries.json")
    args = ap.parse_args(argv)

    sports: dict = {}
    notes: list[str] = []
    for league in LEAGUES:
        try:
            rows = parse_injuries(fetch_injuries(league))
            sports[league] = rows
        except DataUnavailable as exc:
            notes.append(f"{league}: {exc}")
    board = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "status": "live" if sports else "unavailable",
        "notes": notes,
        "sports": sports,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=1))
    counts = ", ".join(f"{k} {len(v)}" for k, v in sports.items()) or "none"
    print(f"Injuries: {counts}"
          + (f"  ({len(notes)} feed(s) declined)" if notes else ""))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
