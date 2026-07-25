#!/usr/bin/env python3
"""Harvest historical sportsbook odds into the history DB.

    python3 harvest_odds.py mlb --from 2026-07-01 --to 2026-07-20
    python3 harvest_odds.py mlb --from 2026-07-01 --to 2026-07-20 --dry-run
    python3 harvest_odds.py nfl --from 2025-09-05 --to 2025-12-29 --hour 17

This is what turns the backtest from "does the model beat a trailing average?"
into "would this have beaten the book?" — the only question that matters. Each
harvested snapshot is the price a bettor could genuinely have taken, so replaying
a slate against it measures real ROI and closing-line value.

**Historical requests cost more credits than live ones**, and a past price never
changes, so this is deliberately careful:

* it estimates the cost and asks before spending (``--yes`` to skip the prompt);
* it skips any snapshot already in the DB rather than paying for it twice;
* ``--dry-run`` shows the plan and spends nothing.

By default it takes one snapshot per day near the evening slate. Odds move most
in the hours before first pitch, so a snapshot close to game time is the most
useful single reading — use ``--hour`` to shift it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from engine import db as _db
from engine.sources import oddshistory as oh
from engine.sources.oddsapi import OddsAPIError


def daterange(start: str, end: str):
    a = _dt.date.fromisoformat(start)
    b = _dt.date.fromisoformat(end)
    if b < a:
        a, b = b, a
    day = a
    while day <= b:
        yield day
        day += _dt.timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest historical odds into the DB.")
    ap.add_argument("sport", choices=["nfl", "mlb"])
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--hour", type=int, default=23,
                    help="UTC hour to snapshot each day (default 23 ≈ evening slate)")
    ap.add_argument("--max-events", type=int, default=0,
                    help="Cap events per day (0 = no cap) to control spend")
    ap.add_argument("--db", default=str(_db.DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true", help="Plan only; spend nothing")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = ap.parse_args()

    days = list(daterange(args.start, args.end))
    print(f"Harvesting {args.sport.upper()} odds for {len(days)} day(s) "
          f"({args.start} → {args.end}), snapshot at {args.hour:02d}:00 UTC.\n")

    if args.dry_run:
        print("Dry run — no requests will be made.")
        print(f"  Plan: 1 events call per day, then 1 call per event.")
        print(f"  Rough cost: {len(days)} + (events × {len(days)}) historical credits.")
        print("  Historical calls are billed above live ones; check your plan's rate.")
        return

    if not args.yes:
        print("This spends API credits (historical calls cost more than live ones).")
        print(f"Continue harvesting {len(days)} day(s)? [y/N] ", end="")
        if input().strip().lower() not in ("y", "yes"):
            print("Aborted — nothing spent.")
            return

    conn = _db.connect(args.db)
    total_rows = calls = skipped = 0

    for day in days:
        stamp = oh.iso_utc(_dt.datetime(day.year, day.month, day.day, args.hour))
        try:
            events_snap = oh.fetch_historical_events(args.sport, stamp)
            calls += 1
        except OddsAPIError as exc:
            print(f"  {day}: events unavailable — {exc}")
            continue

        events = events_snap.data if isinstance(events_snap.data, list) else []
        if args.max_events:
            events = events[:args.max_events]
        if not events:
            print(f"  {day}: no events recorded at that time")
            continue

        day_rows = 0
        for ev in events:
            eid = str(ev.get("id", ""))
            if not eid:
                continue
            if _db.have_odds_snapshot(conn, args.sport, eid, events_snap.taken):
                skipped += 1
                continue
            try:
                snap = oh.fetch_historical_event_odds(eid, args.sport, stamp)
                calls += 1
            except OddsAPIError as exc:
                print(f"    {eid}: {exc}")
                continue
            rows = oh.to_rows(oh.parse_snapshot(snap, args.sport))
            day_rows += _db.upsert_odds_history(conn, rows)

        total_rows += day_rows
        drift = events_snap.drift_minutes
        note = f" (snapshot {drift:.0f} min from requested)" if drift and drift > 30 else ""
        print(f"  {day}: {len(events)} events → {day_rows} price rows{note}")

    _db.log_ingest(conn, args.sport, "odds_history",
                   f"{args.start}..{args.end}", total_rows)
    print(f"\nHarvested {total_rows:,} price rows in {calls} API call(s)"
          + (f", skipped {skipped} already stored" if skipped else "") + ".")
    print("Now run the backtest to price the model against these real lines:")
    print(f"  python3 mlb_backtest.py --from-db {args.db} --real-lines"
          if args.sport == "mlb" else "  (NFL backtest: see engine/backtest.py)")


if __name__ == "__main__":
    main()
