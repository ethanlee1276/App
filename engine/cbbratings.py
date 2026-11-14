"""College basketball's team ratings, adjusted for who each team played.

The shared ratings (`engine.teamrates`) are each team's average margin, which
is right for a league whose teams play much the same schedule. College's do
not: a mid-major that beats five small schools by twenty would read as a
top-ten team, and a power-conference team that splits ten games with ranked
opponents as an average one. Every college tournament projection worth the
name adjusts for the opponent, so this one does.

THE RATING. Points better than an average Division I team on a neutral floor:
the numbers that best explain every margin played, each margin read as the
home team's rating less the visitor's plus the home court (none on a neutral
floor), by least squares, each margin capped at `CAP` so a fifty-point rout
of a small school counts as a thirty-point one. A school below Division I
is not rated from its handful of games: it plays at `NON_DI`, below an
average Division I team by what Division I teams beat such schools by.

THE PRIOR. Before a team has played enough games to say, its rating leans on
last season's (`PRIOR_DECAY` of it, `PRIOR_GAMES` games' worth); each game
this season is one more of its own.

THE CHANCE. A game's margin is drawn from a normal around the rating
difference and the home court, with the margin's spread `SD`.

EVERY NUMBER HERE IS MEASURED (docs/CBB_LAB.md, "The tournament model"):
four seasons of Division I games, 2022-23 to 2025-26, each fortnight's
ratings predicting the next fortnight's games (15,945 of them). The home
court and the small schools' level are fitted on each full season.

Pure: games in, numbers out. Standard library only.
"""
from __future__ import annotations

import math

#: Points the home team gets, off a neutral floor: 2.83, 2.93 and 2.65 on
#: 2023-24 to 2025-26 (3.20 on 2022-23, the last season before it fell).
HCA = 2.8
#: A margin counts at most this many points either way: of 20, 25, 30, 35,
#: 40 and none, 30 predicted the next fortnight best (35 a hair closer on
#: the margin, a hair worse on who won).
CAP = 30.0
#: Where a school below Division I plays, against an average Division I
#: team: -22.8, -23.7 and -23.9 on the three seasons.
NON_DI = -23.5
#: Last season's rating carries this share into the new one... (of 0.5 to
#: 1.0, all of it: a college team's level carries over more than its
#: roster turnover suggests)
PRIOR_DECAY = 1.0
#: ...weighted as this many games of the new season (of 1 to 10).
PRIOR_GAMES = 3.0
#: The margin's spread around the projection, for a game's chance: the
#: best Brier of 9.0 to 12.0 on the same games (the margins themselves miss
#: by 11.6, which includes the ratings' own error).
SD = 10.75
#: The solve stops when no rating moves more than this between passes.
TOL = 1e-4
MAX_PASSES = 200


def is_division_one(team: str) -> bool:
    return bool(team) and not str(team).startswith("espn:")


def adjusted(games, prior: dict | None = None, hca: float = HCA, cap: float = CAP,
             prior_games: float = PRIOR_GAMES, prior_decay: float = PRIOR_DECAY,
             non_di: float = NON_DI) -> dict:
    """``{team: rating}`` for every Division I team in ``games``.

    ``games`` are played games ``{home, away, home_score, away_score,
    neutral}``; ``prior`` is ``{team: last season's rating}``. Solved by
    passes over the teams (each one's rating the average of what each of its
    games says it is, with its prior as `prior_games` games more), the
    Division I average held at zero."""
    rows = []
    teams: set = set()
    for g in games or []:
        h, a = g.get("home"), g.get("away")
        hs, as_ = g.get("home_score"), g.get("away_score")
        if not h or not a or hs is None or as_ is None:
            continue
        m = max(-cap, min(cap, float(hs) - float(as_)))
        edge = 0.0 if g.get("neutral") else hca
        rows.append((h, a, m, edge))
        for t in (h, a):
            if is_division_one(t):
                teams.add(t)
    prior = prior or {}
    start = {t: prior_decay * float(prior.get(t, 0.0)) for t in teams}
    rating = dict(start)
    by_team: dict = {t: [] for t in teams}
    for h, a, m, edge in rows:
        if h in by_team:
            by_team[h].append((a, m - edge, 1.0))
        if a in by_team:
            by_team[a].append((h, -(m - edge), 1.0))
    w = {t: (prior_games if t in prior else prior_games * 0.5) for t in teams}

    def opp(t):
        return rating.get(t, non_di) if is_division_one(t) else non_di

    for _ in range(MAX_PASSES):
        moved = 0.0
        for t in teams:
            said = by_team[t]
            tot = sum(opp(o) + m for o, m, _w in said) + w[t] * start[t]
            new = tot / (len(said) + w[t])
            moved = max(moved, abs(new - rating[t]))
            rating[t] = new
        if teams:
            mean = sum(rating.values()) / len(teams)
            for t in teams:
                rating[t] -= mean
        if moved < TOL:
            break
    return {t: round(r, 3) for t, r in rating.items()}


def win_prob(home_rating: float, away_rating: float, neutral: bool = False,
             hca: float = HCA, sd: float = SD) -> float:
    """P(home wins): a normal over the margin, the home court off a neutral
    floor; clamped away from certainty as the boards clamp."""
    margin = home_rating - away_rating + (0.0 if neutral else hca)
    p = 0.5 * (1.0 + math.erf(margin / (max(sd, 1e-6) * math.sqrt(2.0))))
    return min(0.995, max(0.005, p))


def rating_of(ratings: dict, team: str, non_di: float = NON_DI) -> float:
    """A team's rating, a school below Division I's fixed one, and an average
    Division I team's (zero) for one never seen."""
    if not is_division_one(team):
        return non_di
    return float(ratings.get(team, 0.0))
