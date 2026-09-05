"""NFL team profiles from ingested play-by-play — the measured layer.

One read model over the ``team_weeks`` table: per team, the season (or
last-N-weeks) averages of the numbers that actually describe how a team
plays — EPA per play on offense and allowed on defense, the pass/rush
split, PROE (intent vs situation), neutral pace, and plays per game.

This is the spec's §5/§6 efficiency-and-coaching input, measured from the
plays themselves instead of inferred from box scores. Consumers: the
Fantasy game scripts today; the Week-1 environment/totals layer in Phase 2.

Pure reads; nothing here fetches. The Tuesday pbp refresh keeps the table
current all season.
"""

from __future__ import annotations

# A profile needs at least this many weeks before its averages mean
# anything — two games of EPA is a coin flip wearing a decimal point.
MIN_WEEKS = 4


def latest_season(conn, sport: str = "nfl") -> int | None:
    row = conn.execute("SELECT MAX(season) FROM team_weeks WHERE sport=?",
                       (sport,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def season_profiles(conn, season: int | None = None, last_n: int | None = None,
                    sport: str = "nfl", min_weeks: int = MIN_WEEKS) -> dict:
    """{team: profile} for a season — averages over its team_weeks rows.

    ``last_n`` restricts to each team's most recent N weeks (a form
    window); each stat averages only the weeks where it exists, and a
    stat with no data stays None rather than becoming a fake 0.0.
    """
    season = season if season is not None else latest_season(conn, sport)
    if season is None:
        return {}
    rows = conn.execute(
        "SELECT * FROM team_weeks WHERE sport=? AND season=? "
        "ORDER BY team, period", (sport, season)).fetchall()
    by_team: dict[str, list] = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)
    out: dict[str, dict] = {}
    stats = ("proe", "off_epa", "pass_epa", "rush_epa", "def_epa", "pace")
    for team, weeks in by_team.items():
        if last_n:
            weeks = weeks[-last_n:]
        if len(weeks) < min_weeks:
            continue
        prof: dict = {"season": season, "weeks": len(weeks)}
        plays = [r["plays"] for r in weeks if r["plays"]]
        prof["plays_per_game"] = round(sum(plays) / len(plays), 1) if plays else None
        for s in stats:
            vals = [r[s] for r in weeks if r[s] is not None]
            prof[s] = round(sum(vals) / len(vals), 4) if vals else None
        out[team] = prof
    return out


def league_baseline(profiles: dict) -> dict:
    """League-average line for the same stats — the zero point every
    profile reads against ("+0.06 EPA/play" means nothing without it)."""
    out: dict = {}
    for s in ("proe", "off_epa", "pass_epa", "rush_epa", "def_epa", "pace",
              "plays_per_game"):
        vals = [p[s] for p in profiles.values() if p.get(s) is not None]
        out[s] = round(sum(vals) / len(vals), 4) if vals else None
    return out
