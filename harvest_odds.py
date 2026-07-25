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
    ap.add_argument("--markets", default="",
                    help="Comma-separated markets to harvest (e.g. total_bases,h2h). "
                         "Credits scale with markets, so harvesting only what you "
                         "backtest cuts the cost several-fold. Default: everything.")
    ap.add_argument("--books", default="",
                    help="Comma-separated Odds-API book keys (e.g. pinnacle) to "
                         "harvest INSTEAD of the defaults. Bypasses the "
                         "already-stored skip (those rows lack these books) and "
                         "never overwrites the stored shopped-best price.")
    ap.add_argument("--budget", type=int, default=0,
                    help="Hard stop after roughly this many credits are spent "
                         "(measured from the API's own remaining-count; 0 = no cap).")
    ap.add_argument("--db", default=str(_db.DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true", help="Plan only; spend nothing")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = ap.parse_args()

    days = list(daterange(args.start, args.end))
    market_keys = (oh.resolve_market_keys(args.sport, args.markets.split(","))
                   if args.markets else None)
    book_keys = [b.strip() for b in args.books.split(",") if b.strip()] or None
    market_note = (f"markets: {', '.join(market_keys)}" if market_keys
                   else "markets: ALL (costly — use --markets to harvest only "
                        "what you backtest)")
    print(f"Harvesting {args.sport.upper()} odds for {len(days)} day(s) "
          f"({args.start} → {args.end}), snapshot at {args.hour:02d}:00 UTC.")
    print(f"  {market_note}\n")

    if args.dry_run:
        print("Dry run — no requests will be made.")
        print(f"  Plan: 1 events call per day, then 1 call per event.")
        print(f"  Credits scale with markets requested — a full-market event call "
              f"has measured ~35-40 credits; a 2-market call is several times cheaper.")
        print("  Add --budget N for a hard spend cap measured from the API's counter.")
        return

    if not args.yes:
        print("This spends API credits (historical calls cost more than live ones).")
        print(f"Continue harvesting {len(days)} day(s)? [y/N] ", end="")
        if input().strip().lower() not in ("y", "yes"):
            print("Aborted — nothing spent.")
            return

    conn = _db.connect(args.db)
    total_rows = calls = skipped = 0

    # Spend is measured from the API's own remaining-count (recorded on every
    # response), so the cap reflects what the account is actually being billed
    # rather than a guess at per-call cost.
    from engine.oddsbudget import load as _budget_load
    start_state = _budget_load()
    start_remaining = start_state.remaining if start_state.last_seen_iso else None

    def spent_so_far():
        if start_remaining is None:
            return None
        cur = _budget_load()
        return (start_remaining - cur.remaining) if cur.last_seen_iso else None

    over_budget = False
    for day in days:
        if over_budget:
            break
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
            # A custom-books harvest re-visits stored snapshots on purpose:
            # the stored rows don't have these books' prices yet.
            if book_keys is None and _db.have_odds_snapshot(
                    conn, args.sport, eid, events_snap.taken):
                skipped += 1
                continue
            try:
                snap = oh.fetch_historical_event_odds(eid, args.sport, stamp,
                                                      markets=market_keys,
                                                      books=book_keys)
                calls += 1
            except OddsAPIError as exc:
                print(f"    {eid}: {exc}")
                continue
            rows = oh.to_rows(oh.parse_snapshot(snap, args.sport),
                              include_best=book_keys is None)
            day_rows += _db.upsert_odds_history(conn, rows)
            if args.budget:
                spent = spent_so_far()
                if spent is not None and spent >= args.budget:
                    print(f"    ⏹  budget reached (~{spent} credits) — stopping; "
                          f"everything harvested so far is kept")
                    over_budget = True
                    break

        total_rows += day_rows
        drift = events_snap.drift_minutes
        note = f" (snapshot {drift:.0f} min from requested)" if drift and drift > 30 else ""
        print(f"  {day}: {len(events)} events → {day_rows} price rows{note}")

    _db.log_ingest(conn, args.sport, "odds_history",
                   f"{args.start}..{args.end}", total_rows)
    print(f"\nHarvested {total_rows:,} price rows in {calls} API call(s)"
          + (f", skipped {skipped} already stored" if skipped else "") + ".")
    spent = spent_so_far()
    if spent is not None and spent > 0:
        print(f"Credits spent this run: ~{spent} "
              f"(~{spent / max(calls, 1):.0f} per call at these markets)")
    print("Now run the backtest to price the model against these real lines:")
    print(f"  python3 mlb_backtest.py --from-db {args.db} --real-lines"
          if args.sport == "mlb" else "  (NFL backtest: see engine/backtest.py)")


if __name__ == "__main__":
    main()
