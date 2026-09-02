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


#: Average played games per team below which the current season cannot
#: carry a rating on its own and the previous one is pooled in. Four is
#: about a month of an NFL season; under it, `n/(n+shrink)` is regressing
#: so hard that every team looks league-average anyway.
MIN_GAMES_PER_TEAM = 4.0


def ratings_for_season(conn, sport: str, season: int, shrink: float = 6.0,
                       exclude_prefix: str | None = None):
    """``(ratings, seasons_used)`` — the current season, widened when it is
    too thin to say anything.

    **The bug this exists for.** Every build script asked for
    ``seasons=[current]``, and ``compute_team_ratings`` requires a final
    score. On 2026-08-08 the NFL table held 1,696 games of which 1,424 were
    scored — and all 272 unscored ones were the 2026 season, because it had
    not been played. So the query returned nothing, the board printed "none
    in the DB yet — run `python3 ingest.py nfl`", and running the ingest
    could not possibly help. A message that sends someone to do the one
    thing that cannot work is worse than no message.

    It is the same fault as the prop board's: scoping to a season that by
    definition has no results at the start of a season. The repair is the
    same too — carry the previous one until this one can stand up.

    Pooled rather than swapped, so the changeover is gradual: while the
    current season is thin the prior dominates by weight of games, and each
    new week dilutes it. Above the floor the current season stands alone,
    which is a small discontinuity accepted on purpose — a rating that
    still carried last year's roster in December would be worse.
    """
    got = compute_team_ratings(conn, sport, seasons=[season], shrink=shrink,
                               exclude_prefix=exclude_prefix)
    if got:
        per_team = sum(r.games for r in got.values()) / len(got)
        if per_team >= MIN_GAMES_PER_TEAM:
            return got, [season]
    pooled = compute_team_ratings(conn, sport, seasons=[season - 1, season],
                                  shrink=shrink, exclude_prefix=exclude_prefix)
    if pooled:
        return pooled, [season - 1, season]
    # Nothing in either — say so by returning what the caller asked for
    # rather than inventing a wider window that also has nothing.
    return got, [season]


def compute_team_ratings(conn, sport: str, seasons: list[int] | None = None,
                         shrink: float = 6.0,
                         exclude_prefix: str | None = None) -> dict[str, TeamRating]:
    """Return ``{team_abbr: TeamRating}`` from the ``games`` table.

    Offense/defense are deviations from ``SCORING_BASELINE[sport]`` (a fixed
    per-team scoring average) so they line up with the totals projection in
    gamebets. Every rating is regressed toward 0 by ``n / (n + shrink)``.
    ``seasons`` restricts the window (e.g. the current season) when given.

    ``exclude_prefix`` leaves out every game in which EITHER side's key
    starts with it. College football's ESPN scoreboard lists FBS hosts
    against FCS visitors, and the visitor arrives keyed ``espn:{id}``
    because it has no FBS abbreviation; a 70–0 buy game counted at full
    weight here was the FBS team's whole rating for a fortnight (CFB
    readiness audit, 2026-09-02 — the brief's own P1). The caller passes
    the fallback prefix only when it KNOWS the FBS map loaded, because on a
    box where the teams feed never answered every key is a fallback key.
    """
    baseline = SCORING_BASELINE.get(sport, 0.0)
    q = ("SELECT home, away, home_score, away_score FROM games "
         "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    if exclude_prefix:
        q += " AND home NOT LIKE ? AND away NOT LIKE ?"
        args += [exclude_prefix + "%", exclude_prefix + "%"]

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
