"""How current football's week tables are, against the last week played.

Ethan, 2026-09-25, after the matchup tape ranked the Jets' defence on
mostly-2025 numbers: "is there any more scans or runs or anything you can
do too make sure we don't run into issue like that I have too find. We
should be getting up to date information and displaying up to date info
on the site."

Two holes it found. `doctor.check_ingest_freshness` reads `games.period`
as a date and skips anything that is not one — so the NFL, whose period
is a week, was never checked at all. And the unit ratings the tape ranks
refresh from the play-by-play file on Tuesdays only
(`maintenance`), so one failed Tuesday left them a week behind with
nothing to say so.

This answers one question per table: what is the latest week it holds
this season, against the latest week whose games have all been played.
A table behind that week is stale, and every caller — the doctor, the
nightly catch-up, the NFL build's log — asks this one function.
"""
from __future__ import annotations

import datetime

#: Days after a week's last game before its data is expected on file:
#: nflverse posts stats and play-by-play overnight, and the nightly
#: ingest runs once. A Monday-night week is due on Wednesday.
GRACE_DAYS = 2

#: The week tables, and the rows in each that say a week is in.
TABLES = {
    "results": ("SELECT MAX(CAST(period AS INTEGER)) FROM games WHERE sport=? AND season=? "
                "AND home_score IS NOT NULL"),
    "player stats": ("SELECT MAX(CAST(period AS INTEGER)) FROM player_game_logs WHERE sport=? "
                     "AND season=? AND market NOT IN ('snap_pct')"),
    "snap counts": ("SELECT MAX(CAST(period AS INTEGER)) FROM player_game_logs WHERE sport=? "
                    "AND season=? AND market='snap_pct'"),
    "unit ratings": ("SELECT MAX(CAST(period AS INTEGER)) FROM team_units WHERE sport=? "
                     "AND season=?"),
}


def last_week_played(conn, sport: str, season: int, today: datetime.date) -> int | None:
    """The latest week whose every game was dated GRACE_DAYS or more ago."""
    cutoff = (today - datetime.timedelta(days=GRACE_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT CAST(period AS INTEGER) AS wk, MAX(date) AS last FROM games "
        "WHERE sport=? AND season=? AND date IS NOT NULL GROUP BY wk", (sport, season)).fetchall()
    done = [r[0] for r in rows if r[0] and r[1] and r[1] <= cutoff]
    return max(done) if done else None


def football_weeks(conn, sport: str = "nfl", today: datetime.date | None = None) -> dict:
    """{"season", "played", "tables": {name: week or None}, "behind": [names]}.

    ``played`` None means no week of this season is due yet (preseason, or
    week 1 not two days old) and nothing is behind by definition."""
    from .seasons import season_of
    today = today or datetime.date.today()
    season = season_of(sport, today.isoformat())
    played = last_week_played(conn, sport, season, today)
    tables: dict = {}
    for name, q in TABLES.items():
        try:
            tables[name] = conn.execute(q, (sport, season)).fetchone()[0]
        except Exception:                                    # noqa: BLE001
            tables[name] = None                              # a table this box never made
    behind = [] if played is None else [
        n for n, wk in tables.items() if wk is None or int(wk) < played]
    return {"season": season, "played": played, "tables": tables, "behind": behind}


def line(rep: dict) -> str:
    """One sentence for a log."""
    if rep.get("played") is None:
        return f"Freshness: no {rep.get('season')} week is due yet."
    have = " · ".join(f"{n} {('week ' + str(w)) if w else 'none'}" for n, w in rep["tables"].items())
    head = (f"Freshness: {rep['season']} week {rep['played']} is the last played — {have}")
    return head + (f". BEHIND: {', '.join(rep['behind'])}." if rep["behind"] else ". All current.")
