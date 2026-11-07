#!/usr/bin/env python3
"""What the carry chart holds — and filling it now rather than tonight. On the box.

    cd /srv/qellys && sudo -u qellys python3 carryfill.py           # check: read-only
    cd /srv/qellys && sudo -u qellys python3 carryfill.py --fill    # read both seasons now

Ethan, 2026-10-13: "a carry chart exactly in the screenshot for every
player ... for past games and ... an 'average' carry chart showing where
they run." The nightly fills it by itself (engine/maintenance: the NFL
play-by-play read, which now also runs while a finished game has no
chart; the college play file every night in season; the league's rushing
tracking file; last season once). `--fill` does the same reads now:

* NFL, this season and last: every run off the nflverse play-by-play;
* the NGS rushing file (rushing yards over expected), every season;
* college, this season and last: every run off the cfbfastR play file,
  for the games the database already has.

The check prints, per league and season, how many carries are stored, how
many games and the newest date, and — the screenshot Ethan sent — Josh
Allen's 2026 week 5 at the Rams, which the play-by-play has as 10 carries,
121 yards and a touchdown. A line that reads otherwise is the finding.
"""

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def check(conn) -> list:
    out = []
    for sport in ("nfl", "cfb"):
        rows = conn.execute(
            "SELECT season, COUNT(*), COUNT(DISTINCT game_id || period), MAX(date), "
            "SUM(hole != '') FROM carries WHERE sport=? GROUP BY season ORDER BY season DESC",
            (sport,)).fetchall()
        if not rows:
            out.append(f"{sport.upper():4} no carries stored yet — run with --fill, or wait for the nightly")
        for season, n, games, newest, holes in rows:
            out.append(f"{sport.upper():4} {season}: {n:,} carries in {games:,} games · newest {newest or '?'}"
                       + (f" · hole recorded on {holes / n:.0%}" if sport == "nfl" and n else ""))
    ngs = conn.execute("SELECT COUNT(*), MAX(season) FROM ngs_rushing").fetchone()
    out.append(f"NGS  {ngs[0]:,} rushing tracking rows" + (f" through {ngs[1]}" if ngs[1] else ""))
    allen = conn.execute(
        "SELECT COUNT(*), SUM(yards), SUM(td) FROM carries WHERE sport='nfl' AND season=2026 "
        "AND period='005' AND player='Josh Allen' AND opponent='LA'").fetchone()
    if allen and allen[0]:
        ok = (allen[0], allen[1], allen[2]) == (10, 121.0, 1)
        out.append(f"CHECK Josh Allen 2026 week 5 at LA: {allen[0]} carries, {allen[1]:.0f} yards, "
                   f"{allen[2]} TD — " + ("the screenshot's numbers" if ok else "NOT the screenshot's 10-121-1"))
    return out


def fill(conn, today=None) -> list:
    from engine import carries as CR, db
    from engine.sources.fetch import DataUnavailable
    from engine.sources.nflpbp import load_pbp_rows
    today = today or _dt.date.today()
    season = today.year if today.month >= 8 else today.year - 1
    out = []
    for s in (season, season - 1):
        try:
            fold = CR.NflCarries(s)
            for r in load_pbp_rows(s, columns=CR.PBP_COLS):
                fold.add(r)
            out.append(f"NFL {s}: {db.upsert_carries(conn, fold.rows(CR.nfl_names(s))):,} carries")
        except DataUnavailable as exc:
            out.append(f"NFL {s}: not read — {exc}")
    try:
        out.append(f"NGS: {db.upsert_ngs_rushing(conn, CR.ngs_rows(CR.fetch_ngs_rushing())):,} rows")
    except DataUnavailable as exc:
        out.append(f"NGS: not read — {exc}")
    for s in (season, season - 1):
        try:
            out.append(f"CFB {s}: {CR.backfill_cfb(conn, s):,} carries")
        except DataUnavailable as exc:
            out.append(f"CFB {s}: not read — {exc}")
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
