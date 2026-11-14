#!/usr/bin/env python3
"""Why is the MLB board blank and are the standings current? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 mlbprobe.py

Ethan, 2026-09-28: "mlb isn't showing any post season games or anything
like that. The rankings didn't even update." Prints what the site holds
and what the league says, side by side: the board's date, its `upcoming`
stamp and game count; the standings file's season, source, note and
bracket state; the last MLB final ingested; the league's season dates
and the next few days' schedule. Writes nothing.

AND THE EDGE BOOK, DAY BY DAY (Ethan, 2026-10-13: "the mlb profit
calander isn't updating, it's stuck on September"). The Record page's
calendar draws the MLB edge bets that have SETTLED, so a month with none
looks frozen. The JOURNAL lines say which step stopped: for each of the
last three weeks, the edge bets journaled that day and how they stand,
the Most Likely rows beside them, and the finals and stat lines on file
to settle them against; then the last edge bet journaled, what the record
file says, and the lines of the last MLB build that say whether it had
real prices and what it journaled.

* Edge rows stop on a day: the board stopped journaling. The BUILD lines
  say why (no real odds, the journal skipped, or nothing recommended).
* Edge rows keep coming but stay open: settling stopped. The finals and
  stat-line counts say whether the results were ever ingested.
* Edge rows settle but the calendar still stops: the record file is not
  being written. The RECORD line says when it last was.
"""

import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"_error": str(exc)}


#: How far back the journal lines look: three weeks covers the end of the
#: regular season and the whole postseason so far.
JOURNAL_DAYS = 21

#: The build lines that say whether it priced, picked and journaled.
BUILD_MARKS = ("Odds API:", "Journal:", "Bet journal skipped", "nothing on", "Analyzed",
               "Most likely:", "Most Likely board:", "Drawdown", "⚠️")


def _ro(path):
    """Read-only, never created: a missing file is an error, not an empty
    database the probe made."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def journal_report(ledger_path, history_path, record_path, log_path, today: str,
                   days: int = JOURNAL_DAYS) -> list:
    """The JOURNAL, RECORD and BUILD lines (see the module docstring)."""
    from engine import ledger as L
    out = []
    day = L.day_expr()
    edge = tuple(L.EDGE_BOOKS)      # the edge calendar's own book
    likely = tuple(L.LIKELY_HALF)   # the Most Likely calendar's (rows, not deduped)
    first = (_dt.date.fromisoformat(today) - _dt.timedelta(days=days - 1)).isoformat()
    try:
        lc = _ro(ledger_path)
    except sqlite3.Error as exc:
        return [f"JOURNAL  unreadable: {exc}"]
    try:
        hc = _ro(history_path)
    except sqlite3.Error:
        hc = None
    try:
        e_marks = ",".join("?" * len(edge))
        l_marks = ",".join("?" * len(likely))
        rows = lc.execute(
            f"SELECT {day} AS d, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0) AS edge, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0 AND status='open') AS open, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0 AND status='won') AS won, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0 AND status='lost') AS lost, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0 AND status='push') AS push, "
            f"SUM(category IN ({e_marks}) AND stake_units > 0 AND status='void') AS void, "
            f"SUM(category IN ({e_marks}) AND NOT stake_units > 0) AS unstaked, "
            f"SUM(category IN ({l_marks})) AS likely, "
            f"SUM(category NOT IN ({e_marks}) AND category NOT IN ({l_marks})) AS other "
            f"FROM bets WHERE sport='mlb' AND {day} >= ? AND {day} <= ? GROUP BY {day}",
            edge * 7 + likely + edge + likely + (first, today)).fetchall()
        by_day = {r[0]: r for r in rows}
        out.append(f"JOURNAL  MLB, {first} to {today}. edge = {' + '.join(edge)} with a stake "
                   f"(the calendar draws these once settled)")
        d = _dt.date.fromisoformat(first)
        while d.isoformat() <= today:
            iso = d.isoformat()
            r = by_day.get(iso)
            fin = lines = "?"
            if hc is not None:
                try:
                    g = hc.execute("SELECT COALESCE(SUM(home_score IS NOT NULL), 0), COUNT(*) FROM games "
                                   "WHERE sport='mlb' AND period=?", (iso,)).fetchone()
                    fin = f"{g[0]}/{g[1]}"
                    lines = hc.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='mlb' AND period=?",
                                       (iso,)).fetchone()[0]
                except sqlite3.Error:
                    pass
            if r:
                n = [int(x or 0) for x in r[1:]]
                out.append(f"  {iso}  edge {n[0]:>3} (open {n[1]} · won {n[2]} · lost {n[3]} · push {n[4]}"
                           f" · void {n[5]}) · unstaked {n[6]} · Most Likely {n[7]} · other {n[8]}"
                           f" · finals {fin} · stat lines {lines}")
            else:
                out.append(f"  {iso}  nothing journaled · finals {fin} · stat lines {lines}")
            d += _dt.timedelta(days=1)
        last = lc.execute(
            f"SELECT {day}, ts, category, status FROM bets WHERE sport='mlb' "
            f"AND category IN ({e_marks}) AND stake_units > 0 ORDER BY ts DESC LIMIT 1", edge).fetchone()
        out.append("JOURNAL  last edge bet: " + (f"day {last[0]}, journaled {last[1]}, {last[2]}, {last[3]}"
                                                 if last else "none"))
        stuck = lc.execute(
            f"SELECT COUNT(*), MIN({day}) FROM bets WHERE sport='mlb' AND status='open' "
            f"AND category IN ({e_marks}) AND stake_units > 0 AND {day} < ?", edge + (today,)).fetchone()
        out.append(f"JOURNAL  open edge bets from before today: {stuck[0]}"
                   + (f", the oldest from {stuck[1]}" if stuck[0] else ""))
    except sqlite3.Error as exc:
        out.append(f"JOURNAL  unreadable: {exc}")
    finally:
        lc.close()
        if hc is not None:
            hc.close()
    rec = _load(record_path)
    mlb = ((rec.get("by_sport") or {}).get("mlb") or {})
    curve = mlb.get("curve") or []
    out.append(f"RECORD   record.json written {rec.get('generated_at')} · MLB curve's last day "
               f"{curve[-1].get('date') if curve else None} · {mlb.get('edge_state')}")
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        out.append(f"BUILD    no MLB build log: {exc}")
        return out
    out.append(f"BUILD    {text[0][:200] if text else '(empty log)'}")
    hits = [ln.strip() for ln in text[1:] if any(m in ln for m in BUILD_MARKS)]
    out += [f"BUILD      {ln[:200]}" for ln in hits[-15:]]
    if not hits:
        out.append("BUILD      no line about odds or the journal: the build stopped before it priced")
    return out


def main() -> int:
    today = _dt.date.today().isoformat()
    b = _load(ROOT / "web" / "data" / "mlb_recommendations.json")
    print(f"BOARD  built_at {b.get('built_at')}  date {b.get('date')}  games {len(b.get('games') or [])}  "
          f"status {b.get('status')}  upcoming {b.get('upcoming')}")
    s = _load(ROOT / "web" / "data" / "standings_mlb.json")
    br = s.get("bracket") or {}
    print(f"STANDINGS  season {s.get('season')}  source {s.get('source')}  teams {s.get('team_count')}  "
          f"season_wait {s.get('season_wait')}  bracket started {br.get('started')} rounds {len(br.get('rounds') or [])}")
    if s.get("note"):
        print(f"  note: {s['note'][:200]}")
    for g in (s.get("groups") or [])[:6]:
        top = (g.get("teams") or [{}])[0]
        print(f"  {str(g.get('label') or g.get('conference'))[:22]:22} leader {top.get('team')} {top.get('record')}")
    try:
        c = sqlite3.connect(f"file:{ROOT / 'data' / 'history.db'}?mode=ro", uri=True)
        r = c.execute("SELECT MAX(period), COUNT(*) FROM games WHERE sport='mlb' AND season=? "
                      "AND home_score IS NOT NULL", (int(today[:4]),)).fetchone()
        print(f"INGEST  last MLB final {r[0]}  finals this season {r[1]}")
    except sqlite3.Error as exc:
        print(f"INGEST  unreadable: {exc}")
    try:
        from engine.mlb.sources.mlbstats import season_dates, next_game_day
        print(f"LEAGUE  {season_dates(int(today[:4]))}")
        print(f"LEAGUE  next game day after {today}: {next_game_day(today, 7)}")
    except Exception as exc:                                    # noqa: BLE001
        print(f"LEAGUE  unreachable: {exc}")
    for line in journal_report(ROOT / "data" / "ledger.db", ROOT / "data" / "history.db",
                               ROOT / "web" / "data" / "record.json",
                               ROOT / "data" / "logs" / "mlb_build.log", today):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
