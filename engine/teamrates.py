"""Team-strength ratings from historical scores.

The moneyline model in :mod:`engine.gamebets` needs a per-team rating that is
*independent of the sportsbook line*. This module derives one from the games
already in the historical database: a team's average scoring margin per game.

Because every point (or run) one team scores is one the other allows, the
league-average margin is zero by construction — so a team's mean margin is
already expressed relative to average, exactly the unit the win-probability
models expect (net points/game for the NFL, net runs/game for MLB).

Small samples are shrunk toward zero (an early-season 2-0 team is not a +20
juggernaut), so ratings firm up as the season accumulates games.

Standard library only.
"""

from __future__ import annotations


def compute_team_ratings(conn, sport: str, seasons: list[int] | None = None,
                         shrink: float = 6.0) -> dict[str, float]:
    """Return ``{team_abbr: rating}`` from the ``games`` table.

    ``rating`` is the team's mean scoring margin per game, regressed toward 0 by
    ``n / (n + shrink)`` so a handful of games can't produce an extreme number.
    ``seasons`` restricts the window (e.g. the current season) when given.
    """
    q = ("SELECT home, away, home_score, away_score FROM games "
         "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)

    agg: dict[str, list[float]] = {}   # team -> [margin_sum, games]
    for home, away, hs, as_ in conn.execute(q, args).fetchall():
        margin = float(hs) - float(as_)
        agg.setdefault(home, [0.0, 0.0]); agg[home][0] += margin; agg[home][1] += 1
        agg.setdefault(away, [0.0, 0.0]); agg[away][0] -= margin; agg[away][1] += 1

    ratings: dict[str, float] = {}
    for team, (total, n) in agg.items():
        raw = total / n if n else 0.0
        ratings[team] = round(raw * (n / (n + shrink)), 3)
    return ratings


def attach_ratings(games, ratings: dict[str, float]) -> int:
    """Set ``home_rating`` / ``away_rating`` on each game from ``ratings``.

    Returns the number of games that got at least one side's rating. Teams not
    present in ``ratings`` keep their default 0.0 (league average)."""
    touched = 0
    for g in games:
        hit = False
        if g.home in ratings:
            g.home_rating = ratings[g.home]; hit = True
        if g.away in ratings:
            g.away_rating = ratings[g.away]; hit = True
        if hit:
            touched += 1
    return touched
