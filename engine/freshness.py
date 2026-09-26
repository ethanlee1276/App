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
    unit = "day" if rep.get("unit") == "day" else "week"
    if rep.get("played") is None:
        return f"Freshness: no {rep.get('season')} {unit} is due yet."
    have = " · ".join(f"{n} {(unit + ' ' + str(w)) if w else 'none'}" for n, w in rep["tables"].items())
    head = (f"Freshness: {rep['season']} {unit} {rep['played']} is the last played — {have}")
    return head + (f". BEHIND: {', '.join(rep['behind'])}." if rep["behind"] else ". All current.")


# ── the date-keyed leagues ────────────────────────────────────────────────
#
# College football, baseball and basketball store `period` as the game's
# date, so "the last week played" is "the last day played". Ethan,
# 2026-09-25, on the NFL check reaching the page: "start working on all of
# those" — the same question for every league whose model reads the stats
# database.

#: Days after a game before its data is expected on file: the nightly
#: ingest runs once, after the late games. College's player logs come from
#: a mirror that publishes finished weeks (engine/maintenance: "Monday …
#: is when a new week is there to read"), so a Saturday is due Tuesday.
DAILY_GRACE = {"cfb": 3, "mlb": 1, "nba": 1, "wnba": 1}

#: The tables each league's model reads, and the rows in each that say a
#: day is in. MLB's player logs are keyed by the game's index in the
#: season, not its date (engine/ingest.mlb_rows_from_slate), so only its
#: finals are dated.
_RESULTS = ("SELECT MAX(period) FROM games WHERE sport=? AND home_score IS NOT NULL "
            "AND period<=?")
_LOGS = "SELECT MAX(period) FROM player_game_logs WHERE sport=? AND period<=?"
DAILY_TABLES = {
    "cfb": {"results": _RESULTS, "player stats": _LOGS},
    "nba": {"results": _RESULTS, "player stats": _LOGS},
    "wnba": {"results": _RESULTS, "player stats": _LOGS},
    "mlb": {"results": _RESULTS},
}


def daily(conn, sport: str, today: datetime.date | None = None) -> dict:
    """{"season", "played": ISO date or None, "unit": "day", "tables", "behind"}
    — `football_weeks`'s answer for a league keyed by date.

    ``played`` is the latest scheduled or final game on or before today less
    the grace; a table is behind when its latest date is earlier. None when
    the league has no games on file (nothing is behind by definition)."""
    from .seasons import season_of
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=DAILY_GRACE.get(sport, 1))).isoformat()
    try:
        played = conn.execute("SELECT MAX(period) FROM games WHERE sport=? AND period<=?",
                              (sport, cutoff)).fetchone()[0]
    except Exception:                                        # noqa: BLE001
        played = None
    tables: dict = {}
    for name, q in DAILY_TABLES.get(sport, {}).items():
        try:
            tables[name] = conn.execute(q, (sport, today.isoformat())).fetchone()[0]
        except Exception:                                    # noqa: BLE001
            tables[name] = None
    behind = [] if not played else [n for n, d in tables.items() if not d or str(d) < str(played)]
    return {"season": season_of(sport, today.isoformat()), "played": played, "unit": "day",
            "tables": tables, "behind": behind}


def stamp_board(board: dict, sport: str) -> None:
    """Put this league's check on its board as `data_freshness` (the page's
    banner, app.js dataBehindHTML; engine/boardtruth's DATA BEHIND) and its
    line on the build log. Never fatal — a check that raised costs the note,
    not the board."""
    try:
        from . import db
        conn = db.connect()
        rep = football_weeks(conn, sport) if sport == "nfl" else daily(conn, sport)
        print("  " + line(rep))
        board["data_freshness"] = rep
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ⚠️  freshness check skipped: {exc}")
