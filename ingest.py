#!/usr/bin/env python3
"""Populate the historical database (data/history.db).

    python3 ingest.py nfl --seasons 2020-2024      # 5 years of NFL
    python3 ingest.py mlb --dates 2024-06-18,2024-06-19
    python3 ingest.py status                        # what's in the DB

NFL games ingest from the nflverse git tree (works anywhere); NFL player logs
and all MLB data need release / API access (blocked in some sandboxes) and are
reported as skipped when unreachable. Ingestion is idempotent — re-run a season
to refresh it. The persisted DB then feeds real training and backtests
(``mlb_backtest.py --from-db``).
"""

from __future__ import annotations

import argparse

import datetime

from engine import db
from engine import ingest


def default_seasons() -> str:
    """The five most recent completed seasons. A season is labelled by its
    starting year; the current calendar year's season isn't complete until the
    following winter, so the latest *completed* season is last year."""
    end = datetime.date.today().year - 1
    return f"{end - 4}-{end}"


def parse_seasons(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def print_summary(conn) -> None:
    s = db.summary(conn)
    print("\nHistory DB contents:")
    for sport in ("nfl", "mlb"):
        seasons = s["seasons"][sport]
        span = f"{seasons[0]}-{seasons[-1]}" if seasons else "—"
        print(f"  {sport.upper()}: {s['games'][sport]:,} games, "
              f"{s['player_logs'][sport]:,} player-log rows  (seasons {span})")
    r = db.date_ranges(conn)
    lo, hi = r["mlb_logs"]
    if lo:
        print(f"  MLB player logs span   {lo} → {hi}")
    lo, hi, n = r["mlb_odds"]
    if n:
        print(f"  MLB harvested odds span {lo} → {hi}  ({n:,} rows)")
        # Odds only pay off where a settled game exists to join them to.
        logs_lo = r["mlb_logs"][0]
        if logs_lo and lo < logs_lo:
            print(f"  ⚠️  odds start {lo} but player logs start {logs_lo} — "
                  f"run: python3 ingest.py mlb --from {lo} --to {logs_lo} "
                  f"(free) so those purchased lines join to settled games")


def main() -> None:
    ap = argparse.ArgumentParser(description="Populate the historical database.")
    ap.add_argument("sport", choices=["nfl", "mlb", "status"])
    ap.add_argument("--seasons", default=default_seasons(),
                    help="NFL: e.g. 2021-2025 (default: last 5 completed seasons)")
    ap.add_argument("--dates", default="", help="MLB: comma-separated YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default="",
                    help="MLB: start date YYYY-MM-DD (ingest completed results through --to)")
    ap.add_argument("--scores-only", action="store_true",
                    help="MLB range: game scores only, skip per-player logs")
    ap.add_argument("--to", dest="end", default="",
                    help="MLB: end date YYYY-MM-DD")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args()

    conn = db.connect(args.db)

    if args.sport == "status":
        print_summary(conn)
        return

    if args.sport == "nfl":
        seasons = parse_seasons(args.seasons)
        print(f"Ingesting NFL seasons {seasons[0]}-{seasons[-1]} → {args.db}")
        res = ingest.ingest_nfl(conn, seasons)
        print(f"  games: {res['games']:,}   player-log rows: {res['player_logs']:,}")
    elif args.start and args.end:
        # Historical results: real final scores, the basis for team ratings.
        print(f"Ingesting MLB {args.start} → {args.end} → {args.db}")
        if args.scores_only:
            print("  (scores only — player logs skipped, so prop backtests "
                  "will have nothing to replay)")
        def _tick(day, n):
            print(f"    {day}: {n:,} player-log rows")
        res = ingest.ingest_mlb_results(conn, args.start, args.end,
                                        with_logs=not args.scores_only,
                                        progress=None if args.scores_only else _tick)
        print(f"  completed games: {res['games']:,}   "
              f"player-log rows: {res['player_logs']:,}")
        for skip in res["skipped"]:
            print(f"  ⚠️  {skip}")
    else:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        if not dates:
            print("Provide --dates YYYY-MM-DD[,...] or --from/--to YYYY-MM-DD for MLB.")
            return
        total_g = total_p = 0
        for d in dates:
            res = ingest.ingest_mlb_date(conn, d)
            total_g += res["games"]
            total_p += res["player_logs"]
            for skip in res["skipped"]:
                print(f"  skipped {skip}")
        print(f"  games: {total_g:,}   player-log rows: {total_p:,}")

    # Report anything skipped (blocked feeds).
    for skip in locals().get("res", {}).get("skipped", []):
        print(f"  ⚠️  {skip}")

    print_summary(conn)


if __name__ == "__main__":
    main()
