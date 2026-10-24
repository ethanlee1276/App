#!/usr/bin/env python3
"""What the route chart holds — and filling it now rather than tonight. On the box.

    cd /srv/qellys && sudo -u qellys python3 routefill.py           # check: read-only
    cd /srv/qellys && sudo -u qellys python3 routefill.py --fill    # read both seasons now

Ethan, 2026-10-13, with the NFL's route chart for Sam LaPorta against the
Cardinals: "We can add route charts for wr and shit too. And if we don't
have access too this info then we should be able too make it." The
nightly fills it by itself (engine/maintenance: the NFL play-by-play
read, which also runs while a finished game has no chart; the league's
receiving tracking file; last season once, with the routes the league
charted). `--fill` does the same reads now:

* NFL, this season and last: every target off the nflverse play-by-play,
  joined to the league's charted route, coverage and shell where nflverse
  has the season's participation file (2025 and before), and to FTN's
  charting (screen, play action, contested, drop, catchable);
* the NGS receiving file (separation, cushion, yards after the catch over
  expected), every season.

The check prints, per season, how many targets are stored, how many games
and the newest date, how many carry the league's route, and how many
carry one of FTN's words (most targets are none of screen, play action,
contested, drop, created or uncatchable) — and the screenshot Ethan sent: LaPorta's 2026 week 5 at the
Cardinals, which the play-by-play has as 5 targets, 5 catches, 88 yards,
44 after the catch and a touchdown. A line that reads otherwise is the
finding.
"""

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SCREENSHOT = (5, 5, 88.0, 44.0, 1)


def check(conn) -> list:
    out = []
    rows = conn.execute(
        "SELECT season, COUNT(*), COUNT(DISTINCT game_id || period), MAX(date), SUM(route != ''), "
        "SUM(charting != '') FROM targets WHERE sport='nfl' GROUP BY season ORDER BY season DESC").fetchall()
    if not rows:
        out.append("NFL  no targets stored yet — run with --fill, or wait for the nightly")
    for season, n, games, newest, routed, charted in rows:
        out.append(f"NFL  {season}: {n:,} targets in {games:,} games · newest {newest or '?'} · "
                   f"the league's route on {routed / n:.0%} · an FTN word on {charted / n:.0%}")
    ngs = conn.execute("SELECT COUNT(*), MAX(season) FROM ngs_receiving").fetchone()
    out.append(f"NGS  {ngs[0]:,} receiving tracking rows" + (f" through {ngs[1]}" if ngs[1] else ""))
    lap = conn.execute(
        "SELECT COUNT(*), SUM(complete), SUM(yards), SUM(CASE WHEN complete THEN yac ELSE 0 END), SUM(td) "
        "FROM targets WHERE sport='nfl' AND season=2026 AND period='005' AND player='Sam LaPorta' "
        "AND opponent='ARI'").fetchone()
    if lap and lap[0]:
        got = (lap[0], lap[1], lap[2], lap[3], lap[4])
        out.append(f"CHECK Sam LaPorta 2026 week 5 at ARI: {got[0]} targets, {got[1]} catches, "
                   f"{got[2]:.0f} yards, {got[3]:.0f} after the catch, {got[4]} TD — "
                   + ("the screenshot's numbers" if got == SCREENSHOT else "NOT the screenshot's 5-5-88, 44 YAC, 1 TD"))
    return out


def fill(conn, today=None) -> list:
    from engine import db, targets as TG
    from engine.carries import nfl_names
    from engine.sources.fetch import DataUnavailable
    from engine.sources.nflpbp import load_pbp_rows
    today = today or _dt.date.today()
    season = today.year if today.month >= 8 else today.year - 1
    out = []
    for s in (season, season - 1):
        try:
            fold = TG.NflTargets(s)
            for r in load_pbp_rows(s, columns=TG.PBP_COLS):
                fold.add(r)
            routes = TG.routes_for(s)
            n = db.upsert_targets(conn, fold.rows(nfl_names(s), routes, TG.charting_for(s)))
            out.append(f"NFL {s}: {n:,} targets" + (f", {len(routes):,} charted routes on file" if routes
                                                    else ", no route charting published for it"))
        except DataUnavailable as exc:
            out.append(f"NFL {s}: not read — {exc}")
    try:
        out.append(f"NGS: {db.upsert_ngs_receiving(conn, TG.ngs_rows(TG.fetch_ngs_receiving())):,} rows")
    except DataUnavailable as exc:
        out.append(f"NGS: not read — {exc}")
    return out


def main(argv=None) -> int:
    from engine import db
    argv = list(sys.argv[1:] if argv is None else argv)
    conn = db.connect()
    try:
        if "--fill" in argv:
            for line in fill(conn):
                print(line)
        for line in check(conn):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
