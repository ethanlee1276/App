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
        print(f"  {sport.upper()}: {s['games'][sport]:,} games "
              f"({s['scored_games'][sport]:,} with final scores), "
              f"{s['player_logs'][sport]:,} player-log rows  (seasons {span})")
        if s["games"][sport] and not s["scored_games"][sport]:
            lo, hi = db.date_ranges(conn).get(f"{sport}_logs", (None, None))
            if sport == "mlb" and lo:
                print(f"  ⚠️  no game has a final score — team ratings and the "
                      f"moneyline backtest are running on nothing. Restore "
                      f"them with: python3 ingest.py mlb --from {lo} "
                      f"--to {hi} --scores-only")
    n_ump = conn.execute(
        "SELECT COUNT(*) FROM game_umpires WHERE sport='mlb'").fetchone()[0]
    n_sp = conn.execute(
        "SELECT COUNT(*) FROM game_starters WHERE sport='mlb'").fetchone()[0]
    if n_ump or n_sp:
        print(f"  MLB context rows: {n_sp:,} starting pitchers, "
              f"{n_ump:,} plate umpires")
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
    ap.add_argument("sport",
                    choices=["nfl", "mlb", "nba", "wnba", "cfb", "ufc",
                             "status"])
    ap.add_argument("--seasons", default=default_seasons(),
                    help="NFL: e.g. 2021-2025 (default: last 5 completed seasons)")
    ap.add_argument("--dates", default="", help="MLB: comma-separated YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default="",
                    help="MLB: start date YYYY-MM-DD (ingest completed results through --to)")
    ap.add_argument("--probe", action="store_true",
                    help="report what each candidate feed endpoint "
                         "actually returns, then exit")
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
    elif args.sport == "cfb":
        # College football's results come from the same keyless ESPN feed
        # the board reads, one request per day. Everything downstream needs
        # them: the team ratings, the fitted margin/total variance, and the
        # settler. Without a season in the table the board prices from a
        # prior and stays on probation.
        from engine.sources import cfbdata
        if not (args.start and args.end):
            print("Provide --from/--to YYYY-MM-DD for college football, e.g.\n"
                  "  python3 ingest.py cfb --from 2025-08-24 --to 2026-01-20")
            return
        print(f"Ingesting CFB {args.start} → {args.end} → {args.db}")
        games = cfbdata.load_results(args.start, args.end)
        rows = cfbdata.game_rows(games)
        n = db.upsert_games(conn, rows) if rows else 0
        print(f"  games: {n:,} finished")
        if not n:
            print("  Nothing stored. FBS plays late August to mid-January — "
                  "check the range, and note that ESPN is keyless so a zero "
                  "here usually means the dates, not the network.")
    elif args.sport == "ufc":
        # Two different things, both needed before the model may bet:
        # the dossiers it refuses to fight without, and the results that
        # settle what it already bet.
        from engine import ledger
        from engine.db import connect as _hist
        print("Settling any open UFC picks from ESPN MMA results…")
        try:
            lconn = ledger.connect()
            settled = ledger.settle_ufc(lconn)
            print(f"  settled: {settled}")
        except Exception as exc:                       # noqa: BLE001
            print(f"  could not settle ({exc})")
        print("\nFighter dossiers are the other half — the engine refuses to "
              "bet a fighter it has no measured record for. Draft the next "
              "card's fighters with:\n  python3 ufc_dossiers.py\n"
              "  python3 ufc_dossiers.py \"Fighter Name\"   (one fighter)")
    elif args.sport in ("nba", "wnba"):
        # One path, two leagues. Both publish the same JSON shapes on their
        # own CDN, so the only thing that differs is which day-ingester to
        # call — and the WNBA arm existing at all matters more than it
        # looks: its season runs May-September, so it is the basketball
        # board that is LIVE while the NBA's is dark.
        import datetime as _dt
        if args.sport == "wnba":
            if args.probe:
                from engine.sources.wnbadata import probe as _probe
                print("Probing every WNBA endpoint — what each one ACTUALLY "
                      "returns right now:\n")
                for row in _probe():
                    print(f"  {row['label']}")
                    print(f"    {row['url']}")
                    if row.get("error"):
                        print(f"    ✗ {row['status']}: {row['error']}")
                    elif row.get("json"):
                        print(f"    ✅ {row['status']} · {row['bytes']:,} bytes "
                              f"· JSON · top keys {row.get('top_keys')}")
                    else:
                        print(f"    ✗ {row['status']} · {row['bytes']:,} bytes "
                              f"· NOT JSON · starts {row.get('head')!r}")
                    print()
                return
            # ESPN first: it is the endpoint family that already feeds NFL
            # live scores and the whole college football board here, so it
            # is the one route in this file that is known to work rather
            # than assumed to.
            from engine.sources.wnbaespn import ingest_day
        else:
            from engine.sources.nbadata import ingest_nba_date as ingest_day
        label = args.sport.upper()
        if args.start and args.end:
            day = _dt.date.fromisoformat(args.start)
            last = _dt.date.fromisoformat(args.end)
            dates = []
            while day <= last:
                dates.append(day.isoformat())
                day += _dt.timedelta(days=1)
        else:
            dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        if not dates:
            print(f"Provide --dates or --from/--to YYYY-MM-DD for {label}.")
            return
        print(f"Ingesting {label} {dates[0]} → {dates[-1]} → {args.db}")
        total_g = total_p = 0
        seen_errors: set = set()
        for d in dates:
            res = ingest_day(conn, d)
            total_g += res["games"]
            total_p += res["player_logs"]
            for skip in res["skipped"]:
                # One line per DISTINCT problem. A feed that is down is down
                # for every date in the range, and printing the same failure
                # ninety times buries the one line that says why.
                key = skip.split(":", 1)[-1].strip()[:80]
                if key in seen_errors:
                    continue
                seen_errors.add(key)
                print(f"  skipped {skip}")
                if len(seen_errors) == 1:
                    print(f"    (further identical failures suppressed — run "
                          f"`python3 ingest.py {args.sport} --probe` to see "
                          f"what each endpoint actually returns)"
                          if args.sport == "wnba" else
                          "    (further identical failures suppressed)")
        print(f"  games: {total_g:,}   player-log rows: {total_p:,}")
        if not total_p:
            print(f"  No player logs stored. If the range is right, the "
                  f"{label} season may not cover these dates — "
                  f"{'May-September' if args.sport == 'wnba' else 'October-June'}.")
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
