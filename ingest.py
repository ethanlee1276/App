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

from engine import db
from engine import ingest


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Populate the historical database.")
    ap.add_argument("sport", choices=["nfl", "mlb", "status"])
    ap.add_argument("--seasons", default="2020-2024", help="NFL: e.g. 2020-2024")
    ap.add_argument("--dates", default="", help="MLB: comma-separated YYYY-MM-DD")
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
    else:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        if not dates:
            print("Provide --dates YYYY-MM-DD[,YYYY-MM-DD ...] for MLB.")
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
