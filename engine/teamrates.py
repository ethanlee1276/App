"""Team-strength ratings from historical scores.

The game-level models in :mod:`engine.gamebets` need per-team ratings that are
*independent of the sportsbook line*. This module derives them from the games
already in the historical database:

* **net** rating — the team's average scoring margin per game. Because every
  point one team scores is one the other allows, the league-average margin is
  zero, so this is already league-relative — the unit the moneyline / spread
  margin models expect (net points/game for the NFL, net runs/game for MLB).
* **offense / defense** split — average points/runs scored and allowed relative
  to a fixed league baseline. The totals model needs this: net rating gives the
  *margin* but not the *combined* scoring.

Small samples are shrunk toward zero (an early-season 2-0 team is not a +20
juggernaut), so ratings firm up as the season accumulates games.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gamebets import SCORING_BASELINE


@dataclass
class TeamRating:
    net: float      # mean scoring margin per game (league-relative)
    off: float      # points/runs scored per game vs league baseline
    def_: float     # points/runs allowed per game vs baseline (higher = leakier)
    games: int


def compute_team_ratings(conn, sport: str, seasons: list[int] | None = None,
                         shrink: float = 6.0) -> dict[str, TeamRating]:
    """Return ``{team_abbr: TeamRating}`` from the ``games`` table.

    Offense/defense are deviations from ``SCORING_BASELINE[sport]`` (a fixed
    per-team scoring average) so they line up with the totals projection in
    gamebets. Every rating is regressed toward 0 by ``n / (n + shrink)``.
    ``seasons`` restricts the window (e.g. the current season) when given.
    """
    baseline = SCORING_BASELINE.get(sport, 0.0)
    q = ("SELECT home, away, home_score, away_score FROM games "
         "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)

    agg: dict[str, list[float]] = {}   # team -> [pf_sum, pa_sum, games]
    for home, away, hs, as_ in conn.execute(q, args).fetchall():
        hs, as_ = float(hs), float(as_)
        agg.setdefault(home, [0.0, 0.0, 0.0]); agg[home][0] += hs; agg[home][1] += as_; agg[home][2] += 1
        agg.setdefault(away, [0.0, 0.0, 0.0]); agg[away][0] += as_; agg[away][1] += hs; agg[away][2] += 1

    ratings: dict[str, TeamRating] = {}
    for team, (pf, pa, n) in agg.items():
        if not n:
            continue
        factor = n / (n + shrink)
        off = (pf / n - baseline) * factor
        def_ = (pa / n - baseline) * factor
        ratings[team] = TeamRating(net=round(off - def_, 3), off=round(off, 3),
                                   def_=round(def_, 3), games=int(n))
    return ratings


def attach_ratings(games, ratings: dict[str, TeamRating]) -> int:
    """Set net + offense/defense ratings on each game from ``ratings``.

    Returns the number of games that got at least one side's rating. Teams not
    present keep their defaults (0.0 = league average)."""
    touched = 0
    for g in games:
        hit = False
        if g.home in ratings:
            r = ratings[g.home]
            g.home_rating, g.home_off, g.home_def = r.net, r.off, r.def_
            hit = True
        if g.away in ratings:
            r = ratings[g.away]
            g.away_rating, g.away_off, g.away_def = r.net, r.off, r.def_
            hit = True
        if hit:
            touched += 1
    return touched
