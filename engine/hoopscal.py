"""Basketball's team ratings, measured against the closing line (step AEU, 25 November 2026).

Ethan, 24 November 2026: "we always want every sport posting props and bets and game reports at all times for
every games so we learn and dial in and calibrate". Every game report shows our team ratings' own chance beside
the price's, "unproven". Football's and baseball's game-line models are graded against their closes
(engine/gamecal); basketball's never were: gamecal's model is points for and against over a scoring baseline,
which no basketball league registered, and basketball's closes are on the tape (engine/lineledger), not the
schedule.

This measures the ratings each report reads, as they stood before each game:

  * college basketball: engine/cbbratings fitted on every game played before the day, each on its own floor (the
    race's kept day files carry the neutral site; the games table where no day was kept), last season's ratings
    as the prior, as engine/ncaarace fits them for the reports (step AET);
  * the NBA and the WNBA: engine/futuresdata.blended_ratings' formula on the games before the day, each team's
    average margin this season (engine/teamrates' shrink) beside last season's;

against each game's last price taken before it started: the sharp book's (engine/lineledger.SHARP_BOOK) where it
quoted, the shopped field's otherwise. The observations are gamecal's own shapes, so gamecal fits, holds and
adopts them as it does every league's: a spread's (model margin less the market's, actual margin less the
market's), a moneyline's (the log-odds gap, the market's log-odds, the home side won). Nothing of ours projects a
basketball total, so a total is refused by name.

Standard library only.
"""
from __future__ import annotations

import math

#: The leagues measured here.
LEAGUES = ("cbb", "nba", "wnba")
#: Why a basketball total is not measured, in gamecal's held words (a reason starting "no ").
NO_TOTAL = "no basketball total model of ours to measure"

_LAST_SQL = ("SELECT event_id, home, away, player, line, over_odds, MAX(taken_at) FROM odds_history{hint} "
             "WHERE sport=? AND market=? AND book=? AND commence_time IS NOT NULL AND taken_at < commence_time "
             "GROUP BY event_id, player")


def pregame_closes(conn, sport: str) -> dict:
    """``{(date, home, away): {"spread": the home side's number, "ml": (home odds, away odds)}}``: each game's
    last price taken before it started, the sharp book's where it quoted, else the shopped field's. A price with
    no start on its row is not read: nothing says it was taken before the tip."""
    import sqlite3
    from .lineledger import BEST_BOOK, SHARP_BOOK
    out: dict = {}
    for book in (BEST_BOOK, SHARP_BOOK):                  # the sharp book second: its numbers stand where it has them
        for market in ("spread", "moneyline"):
            try:
                rows = conn.execute(_LAST_SQL.format(hint=" INDEXED BY idx_odds_hist_lookup"),
                                    (sport, market, book)).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such index" not in str(exc):
                    raise
                rows = conn.execute(_LAST_SQL.format(hint=""), (sport, market, book)).fetchall()
            pairs: dict = {}
            for event_id, home, away, player, line, odds, _taken in rows:
                key = (str(event_id or "")[:10], home, away)
                if market == "spread":
                    if player == home and line is not None:
                        out.setdefault(key, {})["spread"] = float(line)
                elif odds:
                    pairs.setdefault(key, {})[player] = int(odds)
            for key, pair in pairs.items():
                h, a = pair.get(key[1]), pair.get(key[2])
                if h and a:
                    out.setdefault(key, {})["ml"] = (h, a)
    return out


def _season_of(sport: str, day: str) -> int:
    from .seasons import season_of
    return int(season_of(sport, day))


def _table_games(conn, sport: str, season: int) -> list:
    return [{"date": str(p)[:10], "home": h, "away": a, "home_score": float(hs), "away_score": float(as_),
             "neutral": False}
            for p, h, a, hs, as_ in conn.execute(
                "SELECT period, home, away, home_score, away_score FROM games WHERE sport=? AND season=? "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL", (sport, season))]


def college_games(conn, season: int, days=None) -> list:
    """The season's played college games, each on its own floor: the race's kept day where it kept one (it
    carries the neutral site), the games table's for a day it never kept (read at the home team's floor).
    ``days`` are the dates to read, the games table's own by default."""
    from . import ncaarace as NR
    table = _table_games(conn, "cbb", season)
    by_day: dict = {}
    for g in table:
        by_day.setdefault(g["date"], []).append(g)
    out = []
    for day in sorted(set(days) if days is not None else by_day):
        kept = NR._kept_day(day)
        rows = [r for r in (kept or []) if NR._played(r)]
        if rows:
            out += [{"date": day, "home": r["home"], "away": r["away"], "home_score": float(r["home_score"]),
                     "away_score": float(r["away_score"]), "neutral": bool(r.get("neutral"))} for r in rows]
        else:
            out += by_day.get(day, [])
    return out


def _college_walk(conn, season: int, closes: dict) -> list:
    """``[(game, close, margin, p_home)]`` for every game with a close, the ratings fitted on the days before."""
    from . import cbbratings as CR
    from .ncaarace import prior_ratings
    games = college_games(conn, season)
    prior = prior_ratings(conn, season)
    out, ratings, before = [], None, []
    for day in sorted({g["date"] for g in games}):
        todays = [g for g in games if g["date"] == day]
        quoted = [(g, closes.get((day, g["home"], g["away"]))) for g in todays]
        quoted = [(g, q) for g, q in quoted if q]
        if quoted and before:
            ratings = CR.adjusted(before, prior=prior, init=ratings)
            for g, q in quoted:
                h, a = g["home"], g["away"]
                if any(CR.is_division_one(t) and t not in ratings for t in (h, a)):
                    continue
                rh, ra = CR.rating_of(ratings, h), CR.rating_of(ratings, a)
                margin = rh - ra + (0.0 if g["neutral"] else CR.HCA)
                out.append((g, q, margin, CR.win_prob(rh, ra, g["neutral"])))
        before += todays
    return out


def _blend(games: list, prior: dict, sport: str) -> dict:
    """engine/futuresdata.blended_ratings' numbers on ``games``: each team's average margin (engine/teamrates'
    shrink, n / (n + 6)) weighted by the season's games against PRIOR_GAMES, last season's, decayed, beside it."""
    from .futuresdata import PRIOR_DECAY, PRIOR_GAMES
    agg: dict = {}
    for g in games:
        m = g["home_score"] - g["away_score"]
        for t, s in ((g["home"], m), (g["away"], -m)):
            a = agg.setdefault(t, [0.0, 0])
            a[0] += s
            a[1] += 1
    this = {t: (tot / n) * (n / (n + 6.0)) for t, (tot, n) in agg.items() if n}
    played = sum(n for _t, n in agg.values()) // 2
    k = PRIOR_GAMES.get(sport, 10)
    w = played / (played + k) if (played + k) else 0.0
    return {t: w * this.get(t, 0.0) + (1.0 - w) * prior.get(t, 0.0) * PRIOR_DECAY for t in set(this) | set(prior)}


def _pro_walk(conn, sport: str, season: int, closes: dict) -> list:
    """The NBA's or the WNBA's, as `_college_walk`."""
    from . import futures as F
    from .teamrates import compute_team_ratings
    games = _table_games(conn, sport, season)
    prior = {t: r.net for t, r in compute_team_ratings(conn, sport, seasons=[season - 1]).items()}
    out, before = [], []
    for day in sorted({g["date"] for g in games}):
        todays = [g for g in games if g["date"] == day]
        quoted = [(g, closes.get((day, g["home"], g["away"]))) for g in todays]
        quoted = [(g, q) for g, q in quoted if q]
        if quoted:
            ratings = _blend(before, prior, sport)
            for g, q in quoted:
                rh, ra = ratings.get(g["home"]), ratings.get(g["away"])
                if rh is None or ra is None:
                    continue
                out.append((g, q, rh - ra + F.HOME_EDGE.get(sport, 2.0), F.win_prob(sport, rh, ra, False)))
        before += todays
    return out


#: The last walk, by what it read (`_fingerprint`): gamecal asks for the spread's and the moneyline's in turn.
_LAST: dict = {}


def _fingerprint(conn, sport: str) -> tuple:
    """What a walk reads, counted: the connection, the league's game-line prices on the tape and its finals."""
    tape = conn.execute("SELECT COUNT(*), MAX(taken_at) FROM odds_history WHERE sport=? "
                        "AND market IN ('spread','moneyline')", (sport,)).fetchone()
    games = conn.execute("SELECT COUNT(*), MAX(period) FROM games WHERE sport=? AND home_score IS NOT NULL",
                         (sport,)).fetchone()
    return (id(conn), sport, tuple(tape), tuple(games))


def walk(conn, sport: str) -> list:
    """``[(game, close, model margin, model's home chance)]``: every played game of every season the tape
    has a close for, our ratings as they stood the morning of it."""
    key = _fingerprint(conn, sport)
    if _LAST.get("key") == key:
        return _LAST["rows"]
    closes = pregame_closes(conn, sport)
    seasons = sorted({_season_of(sport, d) for d, _h, _a in closes})
    out = []
    for season in seasons:
        out += (_college_walk(conn, season, closes) if sport == "cbb" else _pro_walk(conn, sport, season, closes))
    _LAST.clear()
    _LAST.update(key=key, rows=out)
    return out


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def observations(conn, sport: str, market: str) -> list:
    """gamecal's shapes for one basketball market: a spread's ``[(model − market, actual − market)]`` in
    points of the home margin, a moneyline's ``[(log-odds gap, market log-odds, home won)]``. A total raises
    (NO_TOTAL): nothing of ours projects one."""
    from .odds import devig_two_way
    if market == "total":
        raise ValueError(NO_TOTAL)
    out = []
    for g, q, margin, p_home in walk(conn, sport):
        actual = g["home_score"] - g["away_score"]
        if market == "spread":
            if q.get("spread") is None:
                continue
            s = float(q["spread"])
            out.append((margin + s, actual + s))
        elif q.get("ml") and actual != 0:
            fair_home, _ = devig_two_way(int(q["ml"][0]), int(q["ml"][1]))
            if 0.0 < fair_home < 1.0:
                out.append((_logit(p_home) - _logit(fair_home), _logit(fair_home), 1.0 if actual > 0 else 0.0))
    return out
