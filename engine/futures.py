"""Season-long futures — division, conference, title, and projected wins.

A futures price is a claim about a whole season, and the honest way to
price one is to play the season out. This module simulates every game that
has not been played yet, many thousands of times, and counts how often each
outcome happens. Nothing here reads a book price: the probability comes
from the schedule and the ratings, which is what "based on what could
genuinely happen" has to mean if it means anything.

**Why futures are worth modelling at all.** They are the market a book
prices earliest and revisits least — a division number posted in March can
sit untouched through a July injury. A model that replays the remaining
schedule every night is comparing against a quote that may be months stale.
That is the edge argument, and it is a real one.

**And why they are the market least likely to hold a sure thing.** The
horizon is months, the variance compounds across a whole season, and the
stake is locked up the entire time. A 68% division favourite loses roughly
one season in three, and it will not feel like variance when it happens.
Nothing in this file will ever return a certainty, and any page built on it
should not imply one.

WHAT IS SIMULATED, AND WHAT IS ASSUMED
--------------------------------------
Each remaining fixture is one Bernoulli draw whose probability comes from
the two teams' net ratings plus home advantage. Then:

* wins accumulate per trial, so projected wins is a distribution, not a
  point;
* division winners are the most wins in each division, ties broken at
  random — a coin flip is the honest model of a tiebreaker we do not
  simulate;
* the playoff field is filled per the league's own shape (division winners
  first where the league seeds that way, then the best remaining records);
* the bracket is re-simulated game by game with the same win probability,
  so a title number is the product of real matchups rather than a
  seeding-strength fudge.

Assumed, and stated because each one is a place the number can be wrong:
ratings are static for the rest of the season (no injuries, no trades, no
regression), every game is independent, and home advantage is one constant
per sport rather than per venue.

PRESEASON IS A PRIOR, NOT A PROJECTION
--------------------------------------
Before a season starts there are no games to rate this year's teams on, so
the ratings come from last season and the simulation is 100% prior. Those
numbers are real arithmetic on stale inputs, and ``prior_weight`` reports
exactly how much of each answer rests on them so a page can say so. By week
three of a season it is mostly this year's evidence; in August it is none
of it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .divisions import group_of, has_divisions

#: Points of scoring margin worth one home game, per sport. Measured
#: elsewhere in this repo for the game-bet models and reused rather than
#: re-derived, so a futures number and a moneyline cannot disagree about
#: what home advantage is worth.
HOME_EDGE = {"nfl": 1.8, "mlb": 0.20, "nba": 2.4, "wnba": 2.2, "cfb": 2.5}

#: Margin-to-probability slope. A rating gap of this many points is one
#: logistic unit — i.e. about 73% to win. Per sport because a run and a
#: point are not the same size of thing.
MARGIN_SCALE = {"nfl": 7.0, "mlb": 1.35, "nba": 8.5, "wnba": 8.0, "cfb": 10.0}


@dataclass(frozen=True)
class LeagueShape:
    """How a league decides who plays for the title."""
    name: str
    #: Playoff berths per conference.
    berths: int = 6
    #: Do division winners take guaranteed seeds? MLB and the NFL yes; the
    #: NBA seeds a conference purely on record and its divisions decide
    #: nothing at all, which is why its p_division is reported as trivia
    #: rather than as a market.
    divisions_seed: bool = True
    #: Seeds that skip the first round.
    byes: int = 0
    #: Games per playoff series. One means single elimination.
    series_len: int = 1


SHAPES = {
    "nfl": LeagueShape("NFL", berths=7, divisions_seed=True, byes=1),
    "mlb": LeagueShape("MLB", berths=6, divisions_seed=True, byes=2,
                       series_len=5),
    "nba": LeagueShape("NBA", berths=8, divisions_seed=False, series_len=7),
    "wnba": LeagueShape("WNBA", berths=4, divisions_seed=False, series_len=5),
}


@dataclass
class Fixture:
    home: str
    away: str


@dataclass
class TeamOutlook:
    team: str
    conference: str = ""
    division: str = ""
    wins: int = 0
    losses: int = 0
    played: int = 0
    remaining: int = 0
    rating: float = 0.0
    proj_wins: float = 0.0
    proj_wins_lo: float = 0.0      # 10th percentile of the simulated season
    proj_wins_hi: float = 0.0      # 90th
    p_division: float = 0.0
    p_playoffs: float = 0.0
    p_conference: float = 0.0
    p_title: float = 0.0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        for k in ("proj_wins", "proj_wins_lo", "proj_wins_hi"):
            d[k] = round(d[k], 1)
        for k in ("p_division", "p_playoffs", "p_conference", "p_title"):
            d[k] = round(d[k], 4)
        d["rating"] = round(d["rating"], 3)
        return d


def win_prob(sport: str, rating_home: float, rating_away: float,
             neutral: bool = False) -> float:
    """P(home wins), from the two net ratings and home advantage.

    A logistic on the margin difference. Clamped away from 0 and 1 because
    a season simulation that treats any game as certain will report a
    certainty at the end of it, and there is no such thing.
    """
    edge = 0.0 if neutral else HOME_EDGE.get(sport, 2.0)
    scale = MARGIN_SCALE.get(sport, 7.0)
    margin = (rating_home - rating_away) + edge
    p = 1.0 / (1.0 + math.exp(-margin / scale))
    return min(0.99, max(0.01, p))


def _seed_field(shape: LeagueShape, table: dict, teams: list[str],
                sport: str, rng) -> list[str]:
    """One conference's playoff field, in seed order.

    Division winners first when the league seeds that way — a 9-win
    division champion outranking a 10-win wildcard is a real feature of the
    NFL and MLB, and a model that sorted purely on record would price it
    away.
    """
    def rec(t):                       # wins, then a coin flip for ties
        return (-table[t], rng.random())

    if shape.divisions_seed and has_divisions(sport):
        by_div: dict[str, list[str]] = {}
        for t in teams:
            by_div.setdefault(group_of(sport, t)[1], []).append(t)
        champs = sorted((sorted(v, key=rec)[0] for v in by_div.values()),
                        key=rec)
        rest = sorted((t for t in teams if t not in set(champs)), key=rec)
        return (champs + rest)[:shape.berths]
    return sorted(teams, key=rec)[:shape.berths]


def _play_series(sport: str, a: str, b: str, ratings: dict, best_of: int,
                 rng) -> str:
    """Winner of a series between two teams. ``a`` holds home advantage.

    Home games alternate rather than all sitting with the higher seed,
    which is how every league here actually does it and is worth a real
    couple of points of series probability.
    """
    need = best_of // 2 + 1
    wa = wb = 0
    g = 0
    while wa < need and wb < need:
        home_is_a = g % 2 == 0 if best_of > 1 else True
        ra = ratings.get(a, 0.0)
        rb = ratings.get(b, 0.0)
        p = (win_prob(sport, ra, rb) if home_is_a
             else 1.0 - win_prob(sport, rb, ra))
        if rng.random() < p:
            wa += 1
        else:
            wb += 1
        g += 1
    return a if wa > wb else b


def _run_bracket(sport: str, shape: LeagueShape, field: list[str],
                 ratings: dict, rng) -> str:
    """Play a seeded bracket down to one team. Returns the winner."""
    alive = list(field)
    byes = min(shape.byes, max(0, len(alive) - 1))
    while len(alive) > 1:
        resting, playing = alive[:byes], alive[byes:]
        nxt = []
        # Highest surviving seed meets the lowest, as every one of these
        # leagues reseeds or brackets to.
        while len(playing) > 1:
            hi, lo = playing.pop(0), playing.pop()
            nxt.append(_play_series(sport, hi, lo, ratings,
                                    shape.series_len, rng))
        nxt += playing                       # odd field — one walks through
        alive = resting + sorted(nxt, key=lambda t: field.index(t))
        byes = 0
    return alive[0]


def simulate(sport: str, ratings: dict, records: dict,
             fixtures: list, trials: int = 20000,
             seed: int | None = 7) -> dict:
    """Play the rest of the season ``trials`` times.

    ``ratings``  {team: net rating}
    ``records``  {team: (wins, losses)} already banked this season
    ``fixtures`` remaining games, home/away

    Seeded by default so two runs of the same board agree. A futures page
    whose numbers jitter by a point every refresh reads as noise even when
    the model is stable, and nobody can tell a real move from the sampler.
    """
    rng = random.Random(seed)
    played_n = {t: sum(records.get(t, (0, 0))) for t in records}
    fixture_n: dict[str, int] = {}
    for f in fixtures:
        fixture_n[f.home] = fixture_n.get(f.home, 0) + 1
        fixture_n[f.away] = fixture_n.get(f.away, 0) + 1
    # A TEAM WITH NO SEASON IS NOT IN THE SIMULATION.
    #
    # Nothing played and nothing left is not a 0-win team, it is a team we
    # know nothing about — a stale abbreviation, a relocation, a feed that
    # named one side differently. Left in, it entered its division on level
    # terms with everyone else, took the division on the random tiebreak
    # whenever its rivals were also empty, and then won the bracket on its
    # rating. Measured on a partial fixture list: a team with zero games
    # came out FIRST by title probability.
    teams = sorted(t for t in set(records) | set(fixture_n)
                   if played_n.get(t, 0) or fixture_n.get(t, 0))
    if not teams:
        return {"teams": [], "trials": 0, "sport": sport}
    fixtures = [f for f in fixtures if f.home in set(teams) and f.away in set(teams)]
    shape = SHAPES.get(sport) or LeagueShape(sport.upper())

    base = {t: records.get(t, (0, 0))[0] for t in teams}
    rem = {t: 0 for t in teams}
    for f in fixtures:
        rem[f.home] = rem.get(f.home, 0) + 1
        rem[f.away] = rem.get(f.away, 0) + 1

    # Precompute each fixture's probability once — it does not change
    # between trials, and this loop is the whole cost of the module.
    probs = [(f.home, f.away,
              win_prob(sport, ratings.get(f.home, 0.0), ratings.get(f.away, 0.0)))
             for f in fixtures]

    conf_of = {t: (group_of(sport, t)[0] if has_divisions(sport) else "") for t in teams}
    by_conf: dict[str, list[str]] = {}
    for t in teams:
        by_conf.setdefault(conf_of[t], []).append(t)

    wins_seen: dict[str, list[int]] = {t: [] for t in teams}
    n_div = {t: 0 for t in teams}
    n_po = {t: 0 for t in teams}
    n_conf = {t: 0 for t in teams}
    n_title = {t: 0 for t in teams}

    for _ in range(trials):
        table = dict(base)
        for home, away, p in probs:
            if rng.random() < p:
                table[home] += 1
            else:
                table[away] += 1
        for t in teams:
            wins_seen[t].append(table[t])

        # Division winners — reported for every league that has divisions,
        # even where they no longer gate a playoff seed.
        if has_divisions(sport):
            by_div: dict[str, list[str]] = {}
            for t in teams:
                by_div.setdefault(group_of(sport, t), []).append(t)
            for members in by_div.values():
                best = sorted(members, key=lambda t: (-table[t], rng.random()))[0]
                n_div[best] += 1

        champs = []
        for conf, members in by_conf.items():
            field = _seed_field(shape, table, members, sport, rng)
            for t in field:
                n_po[t] += 1
            if not field:
                continue
            w = _run_bracket(sport, shape, field, ratings, rng)
            n_conf[w] += 1
            champs.append(w)
        if len(champs) >= 2:
            # The final is neutral-site in every league here that plays one.
            a, b = champs[0], champs[1]
            p = win_prob(sport, ratings.get(a, 0.0), ratings.get(b, 0.0),
                         neutral=True)
            n_title[a if rng.random() < p else b] += 1
        elif len(champs) == 1:
            n_title[champs[0]] += 1

    out = []
    for t in teams:
        w, l = records.get(t, (0, 0))
        seq = sorted(wins_seen[t])
        out.append(TeamOutlook(
            team=t,
            conference=conf_of[t],
            division=(group_of(sport, t)[1] if has_divisions(sport) else ""),
            wins=w, losses=l, played=w + l, remaining=rem.get(t, 0),
            rating=ratings.get(t, 0.0),
            proj_wins=sum(seq) / len(seq),
            proj_wins_lo=seq[int(0.10 * (len(seq) - 1))],
            proj_wins_hi=seq[int(0.90 * (len(seq) - 1))],
            p_division=n_div[t] / trials,
            p_playoffs=n_po[t] / trials,
            p_conference=n_conf[t] / trials,
            p_title=n_title[t] / trials,
        ))
    out.sort(key=lambda o: (-o.p_title, -o.p_conference, -o.proj_wins))
    return {
        "sport": sport, "trials": trials,
        "teams": [o.as_dict() for o in out],
        "divisions_seed": shape.divisions_seed,
        "berths": shape.berths,
        # How much of this rests on games that have not been played. 1.0 in
        # the preseason, falling as the year goes; a page that does not say
        # this is presenting a prior as a projection.
        "prior_weight": round(_prior_weight(records, rem), 3),
    }


def _prior_weight(records: dict, remaining: dict) -> float:
    """Share of the season still unplayed, across the league."""
    played = sum(w + l for w, l in records.values())
    left = sum(remaining.values()) / 2.0            # each fixture has two sides
    total = played + left
    return (left / total) if total else 1.0
