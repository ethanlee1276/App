"""The carry and route charts, filled the day a table is missing — not the next night.

Ethan, 2026-10-13, about an hour after both charts shipped: "Also the
charts aren't working for any players." The charts were fine; their
tables were empty. Every row in `carries` and `targets` comes from reads
that ride the daily chores (engine/maintenance), which run once a
calendar day; the box had already run that day's before the charts'
code landed (16:55 and 17:20 UTC), so every player's chart said "No
carries on file" and would have until the next day's. A deploy was
waiting on the calendar.

`owed` asks the question the once-a-day chores cannot ask between
nights: is a chart table EMPTY for a season this box has played games
of? A few indexed lookups, cheap enough for every cycle: once the
day's chores are done, each cycle's `maintenance.run_if_due` asks it
through `maintenance.fill_charts_if_owed`, which starts this module as a
detached child when the answer is yes:

    python3 -m engine.chartfill

and `fill` does the reads for what is owed and nothing more:

* NFL: one pass over each owed season's play-by-play feeds every fold —
  carries, targets and the passer's throws (the nightly's own single
  read), joined to the names, the league's charted routes and FTN's
  charting;
* the NGS rushing, receiving and passing files, when an NFL season was
  owed;
* college: the season's play file, for the games the database has —
  its carries and, from 2025, the targets it names, both kept to the
  games the college logs keep.

EMPTY, NOT BEHIND. A table a game behind is the nightly's job: it reads
the play-by-play while a finished game has no chart
(engine/carries.nfl_behind), and nflverse publishes a game overnight, so
a midday pass would have nothing new to fetch. A season with no rows at
all is the case that waits on nothing but us.
"""

import datetime as _dt
import sys

#: The chart tables, and the leagues each one draws. The passing chart
#: (`passes`, 2026-10-13) rides the NFL read the other two make.
TABLES = (("nfl", "carries"), ("nfl", "targets"), ("nfl", "passes"), ("cfb", "carries"),
          ("cfb", "targets"))


def season_of(today) -> int:
    """The football season a day belongs to: August onward is that
    year's; January to July the year before's."""
    return today.year if today.month >= 8 else today.year - 1


def owed(conn, today=None) -> list:
    """``[(sport, season, table)]``: every chart table with no rows for a
    season — this one or last — that the box has a finished game of.

    The finished game is the condition, not decoration: a database with
    no games (a clone, a test's) owes nothing, and a season that has not
    kicked off has no plays to read. Never raises; a database that cannot
    answer owes nothing."""
    today = today or _dt.date.today()
    season = season_of(today)
    out = []
    try:
        for s in (season, season - 1):
            for sport in dict.fromkeys(sp for sp, _ in TABLES):
                played = conn.execute(
                    "SELECT 1 FROM games WHERE sport=? AND season=? AND home_score IS NOT NULL "
                    "LIMIT 1", (sport, s)).fetchone()
                if not played:
                    continue
                for sp, table in TABLES:
                    if sp != sport:
                        continue
                    have = conn.execute(f"SELECT 1 FROM {table} WHERE sport=? AND season=? LIMIT 1",
                                        (sport, s)).fetchone()
                    if not have:
                        out.append((sport, s, table))
    except Exception:                                              # noqa: BLE001
        return []
    return out


def fill(conn, want, log=print) -> list:
    """Do the reads for ``want`` (`owed`'s list). Returns the lines it
    logged. One failed read is a line, not the end of the others."""
    from . import carries as CR, db, passes as PS, targets as TG
    from .sources.nflpbp import load_pbp_rows
    out = []

    def say(line):
        out.append(line)
        log(line)

    nfl = sorted({s for sp, s, _t in want if sp == "nfl"}, reverse=True)
    for s in nfl:
        try:
            runs, catches, throws = CR.NflCarries(s), TG.NflTargets(s), PS.NflPasses(s)
            for r in load_pbp_rows(s, columns=CR.PBP_COLS + TG.PBP_COLS + PS.PBP_COLS):
                runs.add(r)
                catches.add(r)
                throws.add(r)
            names = CR.nfl_names(s)
            n_c = db.upsert_carries(conn, runs.rows(names))
            routes = TG.routes_for(s)
            n_t = db.upsert_targets(conn, catches.rows(names, routes, TG.charting_for(s)))
            n_p = db.upsert_passes(conn, throws.rows(names, PS.charting_for(s)))
            say(f"NFL {s}: {n_c:,} carries, {n_t:,} targets, {n_p:,} throws"
                + (f", the league's route charting on {len(routes):,} plays" if routes
                   else ", no route charting published for it yet"))
        except Exception as exc:                                   # noqa: BLE001
            say(f"NFL {s}: not read — {exc}")
    if nfl:
        for label, fetch, rows, upsert in (
                ("rushing", CR.fetch_ngs_rushing, CR.ngs_rows, db.upsert_ngs_rushing),
                ("receiving", TG.fetch_ngs_receiving, TG.ngs_rows, db.upsert_ngs_receiving),
                ("passing", PS.fetch_ngs_passing, PS.ngs_rows, db.upsert_ngs_passing)):
            try:
                say(f"NGS {label}: {upsert(conn, rows(fetch())):,} rows")
            except Exception as exc:                               # noqa: BLE001
                say(f"NGS {label}: not read — {exc}")
    for s in sorted({s for sp, s, _t in want if sp == "cfb"}, reverse=True):
        try:
            n_c = CR.backfill_cfb(conn, s)
            n_t = conn.execute("SELECT COUNT(*) FROM targets WHERE sport='cfb' AND season=?",
                               (s,)).fetchone()[0]
            say(f"CFB {s}: {n_c:,} carries, {n_t:,} targets"
                + ("" if s >= TG.CFB_FROM else " (college targets are drawn from 2025)"))
        except Exception as exc:                                   # noqa: BLE001
            say(f"CFB {s}: not read — {exc}")
    return out


def named(want) -> str:
    return ", ".join(f"{sp.upper()} {s} {t}" for sp, s, t in want)


def main(argv=None) -> int:
    from . import db
    conn = db.connect()
    try:
        want = owed(conn)
        if not want:
            print("charts: nothing owed — every chart table has rows for each season played")
            return 0
        print(f"charts: empty — {named(want)}; reading them now")
        fill(conn, want)
        left = owed(conn)
        print("charts: filled" if not left else f"charts: still empty after the read — {named(left)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
