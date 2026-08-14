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
    for sport in s["games"]:
        seasons = s["seasons"][sport]
        span = f"{seasons[0]}-{seasons[-1]}" if seasons else "—"
        if not s["games"][sport] and not s["player_logs"][sport]:
            # Say it rather than skip it: an absent line reads as "that board
            # isn't a thing here", which is a different fact entirely.
            print(f"  {sport.upper()}: nothing stored yet")
            continue
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
    # Player photos, which are captured DURING ingest and are therefore the
    # one thing here that a pull cannot deliver. An empty table looks
    # identical to a working board — every card falls back to the initials
    # chip, which is what it drew before faces existed — so it has to be
    # counted rather than noticed.
    try:
        faces = conn.execute(
            "SELECT sport, COUNT(*), SUM(headshot != '') FROM player_assets "
            "GROUP BY sport ORDER BY sport").fetchall()
    except Exception:                                         # noqa: BLE001
        faces = []                       # database predates the table
    if faces:
        parts = [f"{r[0].upper()} {r[2] or 0:,}/{r[1]:,}" for r in faces]
        print(f"  Player photos: {' · '.join(parts)}")
    elif s["games"].get("nba") or s["games"].get("wnba"):
        print("  Player photos: none stored — NBA/WNBA prop cards will draw "
              "initials. Re-ingest those seasons to capture them.")

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
    print_gaps(conn)


#: How many holes to list before collapsing to a count. A wall of dates is
#: not a report — the first few name the shape and the range repairs them all.
GAP_LIST_MAX = 12

#: Above this many holes, name a RANGE rather than every date. Below it,
#: name the dates: 22 holes scattered over five years became
#: "--from 2021-06-07 --to 2026-07-16", which is 1,867 days of requests to
#: fix 22. Free of credits is not free of an afternoon.
GAP_RANGE_ABOVE = 40


def repair_command(sport: str, gaps: list) -> str:
    """The narrowest command that fixes exactly these days.

    ``--dates`` when the holes are few and scattered, ``--from/--to`` when
    there are enough of them that a range is genuinely the smaller ask. The
    first version always emitted a range, which is right for a contiguous
    outage and absurd for a handful of days spread across five seasons.
    """
    days = [g["date"] for g in gaps]
    if not days:
        return ""
    if len(days) > GAP_RANGE_ABOVE:
        return f"python3 ingest.py {sport} --from {days[0]} --to {days[-1]}"
    return f"python3 ingest.py {sport} --dates {','.join(days)}"


def print_gaps(conn, sport: str = "mlb") -> None:
    """Days inside the span that are half-ingested. Free to compute and free
    to repair — statsapi.mlb.com is keyless, so nothing here spends credits.

    The span line above says 2021 to 2026 and says nothing about the holes in
    the middle, which is the failure that actually happens: a bet whose day
    was never fully ingested cannot settle, sits open forever, and — before
    the settle guards landed — could be graded against the wrong game.
    """
    try:
        gaps = db.coverage_gaps(conn, sport)
    except Exception as exc:                       # never break the summary
        print(f"  (gap scan skipped: {exc})")
        return
    if not gaps:
        print(f"  {sport.upper()} day coverage: no half-ingested days")
        return
    label = {"no_finals": "no final scores",
             "some_finals": "partial finals",
             "no_logs": "no player logs",
             "thin_logs": "thin player logs"}
    fixable = [g for g in gaps if g["repairable"]]
    stuck = [g for g in gaps if not g["repairable"]]

    # THE REPAIRABLE ONES LEAD, and the range is built from them alone.
    # Built from every gap it produced "--from 2021-03-01", a five-year walk
    # for a handful of real holes — the two kinds have to be costed apart.
    if fixable:
        kinds: dict[str, int] = {}
        for g in fixable:
            kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
        tally = " · ".join(f"{label[k]} {n}" for k, n in sorted(kinds.items()))
        print(f"\n  ⚠️  {len(fixable)} {sport.upper()} day(s) a re-ingest "
              f"would fill ({tally}):")
        for g in fixable[:GAP_LIST_MAX]:
            print(f"      {g['date']}  {label[g['kind']]:<18} {g['detail']}")
        if len(fixable) > GAP_LIST_MAX:
            print(f"      … and {len(fixable) - GAP_LIST_MAX} more")
        print(f"\n      Repair (FREE — statsapi.mlb.com needs no key, and the "
              f"walk is resumable):")
        print(f"        {repair_command(sport, fixable)}")
        print(f"      Then settle whatever those days were holding open:")
        print(f"        python3 launch.py --settle all")
    else:
        print(f"  {sport.upper()} day coverage: nothing a re-ingest would fill")

    # The rest get their own heading, because the remedy is different and
    # putting them in the list above is what made that list unreadable.
    if stuck:
        print(f"\n  {len(stuck)} day(s) hold scoreless game rows that will "
              f"NEVER resolve.")
        print(f"      parse_results stores completed, scored games only, so "
              f"these are postponed,")
        print(f"      cancelled or suspended fixtures. Re-ingesting cannot "
              f"fill them and the settle")
        print(f"      guard already refuses to grade against them — they are "
              f"inert, not urgent.")
        for g in stuck[:4]:
            print(f"      {g['date']}  {label[g['kind']]:<18} {g['detail']}")
        if len(stuck) > 4:
            print(f"      … and {len(stuck) - 4} more")



def _already_have(conn, sport: str, date: str, need_logs: bool) -> bool:
    """Is this date already stored? Backfills get interrupted.

    A six-season walk is thousands of requests; if a re-run started from
    scratch every time, one dropped connection would cost the whole run.
    Days already in the table are skipped, so the command is resumable by
    simply running it again.
    """
    g = conn.execute("SELECT COUNT(*) FROM games WHERE sport=? AND period=?",
                     (sport, date)).fetchone()[0]
    if not g:
        return False
    if not need_logs:
        return True
    p = conn.execute("SELECT COUNT(*) FROM player_game_logs "
                     "WHERE sport=? AND period=?", (sport, date)).fetchone()[0]
    return bool(p)


def _held(conn, sport: str) -> tuple[int, int]:
    """What the DB holds for this sport, regardless of what this run added.

    A run that adds nothing because everything is already there and a run
    that adds nothing because the feed is dead print the same zero. The
    standing total is the number that tells them apart.
    """
    g = conn.execute("SELECT COUNT(*) FROM games WHERE sport=?",
                     (sport,)).fetchone()[0]
    p = conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                     (sport,)).fetchone()[0]
    return g, p


def _walk_days(conn, sport: str, dates: list, ingest_day, scores_only: bool,
               refresh: bool) -> tuple:
    """Ingest a list of dates with progress, resumability and one line per
    distinct failure."""
    import time as _time
    total_g = total_p = skipped = empty = 0
    seen: set = set()
    started = _time.time()
    for i, d in enumerate(dates, 1):
        if not refresh and _already_have(conn, sport, d, not scores_only):
            skipped += 1
            continue
        try:
            res = ingest_day(conn, d)
        except KeyboardInterrupt:
            print(f"\n  Stopped at {d}. Progress is saved — re-run the same "
                  f"command to pick up where it left off.")
            break
        # A date the league simply did not play. Counting these is what lets
        # the caller tell "the feed gave us nothing" apart from "there was
        # nothing to give" — a season WINDOW is not a schedule, and an NBA
        # window holds three weeks of preseason, an All-Star break, playoff
        # travel days and the fortnight after the finals.
        if not res["games"] and not res["skipped"]:
            empty += 1
        total_g += res["games"]
        total_p += res["player_logs"]
        for msg in res["skipped"]:
            key = msg.split(":", 1)[-1].strip()[:80]
            if key in seen:
                continue
            seen.add(key)
            print(f"  skipped {msg}")
        if i % 25 == 0 or i == len(dates):
            rate = i / max(1e-6, _time.time() - started)
            left = (len(dates) - i) / rate if rate else 0
            print(f"  {i:>5}/{len(dates)} days · {total_g:,} games · "
                  f"{total_p:,} log rows"
                  + (f" · ~{left / 60:.0f} min left" if left > 90 else ""))
    return total_g, total_p, skipped, empty


def main() -> None:
    ap = argparse.ArgumentParser(description="Populate the historical database.")
    ap.add_argument("sport",
                    choices=["nfl", "nflpre", "mlb", "nba", "wnba", "cfb",
                             "ufc", "status"])
    # NO default. It used to carry the NFL's "last five seasons", which
    # meant `python3 ingest.py nba` with no arguments silently launched a
    # 1,366-day backfill instead of printing usage. A command that starts
    # an afternoon of work when you typed it to see the options is a trap.
    ap.add_argument("--seasons", default="",
                    help="e.g. 2021-2026 — expanded to each sport's real "
                         "season window (NFL defaults to the last 5)")
    ap.add_argument("--dates", default="", help="MLB: comma-separated YYYY-MM-DD")
    ap.add_argument("--from", dest="start", default="",
                    help="MLB: start date YYYY-MM-DD (ingest completed results through --to)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-ingest dates already stored (default: skip them, "
                         "which makes a long backfill resumable)")
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
        seasons = parse_seasons(args.seasons or default_seasons())
        print(f"Ingesting NFL seasons {seasons[0]}-{seasons[-1]} → {args.db}")
        res = ingest.ingest_nfl(conn, seasons)
        print(f"  games: {res['games']:,}   player-log rows: {res['player_logs']:,}")
    elif args.sport == "nflpre":
        # Preseason box scores, into their own table. Prices nothing — see
        # engine/ingest.ingest_nfl_preseason and the schema note in db.py.
        seasons = parse_seasons(args.seasons or str(datetime.date.today().year))
        print(f"Ingesting NFL PRESEASON {seasons[0]}-{seasons[-1]} → {args.db}")
        print("  Nothing here is priced. This is the history that has to "
              "exist\n  before August can be modelled at all.")
        res = ingest.ingest_nfl_preseason(conn, seasons)
        print(f"  games: {res['games']:,}   preseason rows: "
              f"{res['player_logs']:,}")
        for note in res["skipped"][:5]:
            print(f"  skipped: {note}")
        if not res["player_logs"]:
            print("  Nothing stored. ESPN's summary endpoint is refused by "
                  "policy in the\n  cloud container — run this on the laptop.")
    elif args.sport == "cfb":
        # College football's results come from the same keyless ESPN feed
        # the board reads, one request per day. Everything downstream needs
        # them: the team ratings, the fitted margin/total variance, and the
        # settler. Without a season in the table the board prices from a
        # prior and stays on probation.
        from engine.sources import cfbdata
        from engine.seasons import parse_seasons as _ps, window, describe
        spans = []
        if args.seasons:
            yrs = _ps(args.seasons)
            print(describe("cfb", yrs, sum(1 for _ in yrs)))
            today = datetime.date.today().isoformat()
            for yr in yrs:
                lo, hi = window("cfb", yr)
                if lo > today:
                    print(f"  {yr}: season hasn't started yet — skipped")
                    continue
                spans.append((yr, lo, min(hi, today)))
        elif args.start and args.end:
            spans = [(None, args.start, args.end)]
        else:
            print("Provide --seasons 2021-2026 or --from/--to YYYY-MM-DD for "
                  "college football, e.g.\n"
                  "  python3 ingest.py cfb --seasons 2021-2026")
            return
        n = 0
        for yr, lo, hi in spans:
            print(f"  {yr or ''} {lo} → {hi}".rstrip())
            games = cfbdata.load_results(lo, hi)
            rows = cfbdata.game_rows(games)
            got = db.upsert_games(conn, rows) if rows else 0
            n += got
            print(f"    games: {got:,} finished")
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
            pass
        # ESPN for BOTH leagues. The NBA CDN only ever serves the CURRENT
        # season's schedule, so it cannot answer a question about 2021 —
        # which is exactly why this database had one season of basketball
        # and five of football. ESPN's scoreboard is per-date and goes back
        # as far as the sport does.
        from engine.sources import espnhoops
        league = args.sport
        label = league.upper()

        def ingest_day(c, d):
            return espnhoops.ingest_day(c, d, league=league,
                                        scores_only=args.scores_only)

        from engine.seasons import parse_seasons as _ps, dates_for, describe
        if args.seasons:
            yrs = _ps(args.seasons)
            dates = dates_for(league, yrs)
            print(describe(league, yrs, len(dates)))
        elif args.start and args.end:
            day = _dt.date.fromisoformat(args.start)
            last = _dt.date.fromisoformat(args.end)
            dates = []
            while day <= last:
                dates.append(day.isoformat())
                day += _dt.timedelta(days=1)
        else:
            dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        if not dates:
            print(f"Provide --seasons 2021-2026, --dates, or --from/--to for "
                  f"{label}.")
            return
        if args.scores_only:
            print("  scores only — no box scores, so no prop backtests, but "
                  "team ratings and settlement work and it runs many times "
                  "faster.")
        print(f"Ingesting {label} {dates[0]} → {dates[-1]} → {args.db}")
        total_g, total_p, skipped, empty = _walk_days(
            conn, league, dates, ingest_day, args.scores_only, args.refresh)
        print(f"  games: {total_g:,} new   player-log rows: {total_p:,} new")
        if skipped:
            print(f"  {skipped:,} of {len(dates):,} day(s) were already "
                  f"stored — skipped.")
        # "0 games" after a long run reads as total failure, and here it
        # usually is not: a season WINDOW is Oct 1 - Jun 30, but the league
        # does not play three weeks of that October, the All-Star break, the
        # gaps between playoff rounds, or the fortnight after the finals.
        # Naming the empty days is the difference between "your backfill is
        # done" and "something is broken", which are not close.
        if empty:
            print(f"  {empty:,} day(s) had no {label} games at all — a season "
                  f"window spans preseason, the All-Star break, playoff off "
                  f"days and the weeks after the finals.")
        if not total_g and skipped + empty == len(dates):
            held_g, held_p = _held(conn, league)
            print(f"  Nothing left to fetch — this backfill is COMPLETE. "
                  f"Holding {held_g:,} {label} games and {held_p:,} "
                  f"player-log rows.")
        elif not total_g and not skipped:
            print(f"  Nothing stored. Run `python3 ingest.py {league} --probe` "
                  f"to see what the feed actually returns.")
    elif args.sport == "mlb" and args.seasons and not (args.start and args.end):
        # Whole seasons, expanded to their real date windows so nobody has
        # to remember that baseball starts in late March.
        from engine.seasons import parse_seasons as _ps, window, describe
        yrs = _ps(args.seasons)
        print(describe("mlb", yrs, sum(1 for _ in yrs)))
        for yr in yrs:
            lo, hi = window("mlb", yr)
            today = datetime.date.today().isoformat()
            hi = min(hi, today)
            if lo > today:
                print(f"  {yr}: season hasn't started yet — skipped")
                continue
            print(f"\n  {yr} season: {lo} → {hi}")
            res = ingest.ingest_mlb_results(conn, lo, hi,
                                            with_logs=not args.scores_only)
            print(f"    games: {res['games']:,}   "
                  f"player-log rows: {res['player_logs']:,}")
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
